import json
import subprocess
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

from .config import Settings
from .script_gen import generate_script
from .subtitles import whisper_to_srt
from .timeline import create_timeline_manifest
from .tts_edge import tts_to_mp3_edge
from .tts_elevenlabs import tts_to_mp3_elevenlabs
from .tts_gtts import tts_to_mp3_gtts
from .tts_local import tts_to_wav_local
from .timeline import load_timeline, save_timeline
from .utils import probe_duration_seconds
from .video_edit import build_video


def _is_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def create_app(workspace_root: Path, timeline_path: Path):
    workspace_root = Path(workspace_root).resolve()
    timeline_path = Path(timeline_path).resolve()
    settings = Settings.load()
    work_dir = workspace_root / "work"
    clips_dir = work_dir / "clips"
    out_dir = workspace_root / "output"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    fonts_dir = workspace_root / "assets" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    fonts_index_path = fonts_dir / "fonts_index.json"

    app = Flask(__name__)

    def _load_fonts_index() -> dict:
        if not fonts_index_path.exists():
            return {"fonts": []}
        try:
            return json.loads(fonts_index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"fonts": []}

    def _save_fonts_index(data: dict) -> None:
        fonts_index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _list_local_fonts() -> list:
        data = _load_fonts_index()
        fonts = []
        for item in data.get("fonts", []):
            file_path = Path(item.get("file_path", ""))
            if file_path.exists():
                fonts.append(
                    {
                        "family": item.get("family"),
                        "variant": item.get("variant", "regular"),
                        "file_name": file_path.name,
                        "file_path": str(file_path.resolve()),
                        "url": f"/fonts/{quote(file_path.name)}",
                    }
                )
        return fonts

    def _fetch_google_fonts_catalog(limit: int = 120) -> list:
        # Public API (no key required). Provides modern Google Fonts metadata.
        r = requests.get(
            "https://gwfh.mranftl.com/api/fonts",
            params={"subsets": "latin", "sort": "popularity"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        items = data if isinstance(data, list) else []
        result = []
        for item in items[: max(1, min(limit, 300))]:
            result.append(
                {
                    "id": item.get("id"),
                    "family": item.get("family"),
                    "category": item.get("category", ""),
                    "variants": item.get("variants", []),
                }
            )
        return result

    def _install_google_font(font_id: str, family: str, variant: str = "regular") -> dict:
        r = requests.get(
            f"https://gwfh.mranftl.com/api/fonts/{font_id}",
            params={"subsets": "latin"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        variants = data.get("variants", []) or []
        chosen = None
        if isinstance(variants, list):
            chosen = next((v for v in variants if str(v.get("id", "")).lower() == variant.lower()), None)
            if chosen is None:
                chosen = next((v for v in variants if str(v.get("id", "")).lower() == "regular"), None)
            if chosen is None and variants:
                chosen = variants[0]
        elif isinstance(variants, dict):
            # Backward compatibility if API format changes
            chosen = variants.get(variant) or variants.get("regular")
        if not chosen:
            raise RuntimeError("No downloadable variant found for this font")

        ttf_url = chosen.get("ttf")
        if not ttf_url:
            # fallback to latin entry if available
            latin = chosen.get("latin", {}) if isinstance(chosen.get("latin"), dict) else {}
            ttf_url = latin.get("ttf")
        if not ttf_url:
            raise RuntimeError("No TTF URL available for selected font variant")

        safe_family = "".join(ch for ch in (family or font_id) if ch.isalnum() or ch in ("-", "_", " ")).strip().replace(" ", "_")
        safe_variant = "".join(ch for ch in (variant or "regular") if ch.isalnum() or ch in ("-", "_")).strip() or "regular"
        file_name = f"{safe_family}-{safe_variant}.ttf"
        out_path = fonts_dir / file_name

        if not out_path.exists():
            rr = requests.get(ttf_url, timeout=60)
            rr.raise_for_status()
            out_path.write_bytes(rr.content)

        index = _load_fonts_index()
        fonts = index.get("fonts", [])
        existing = next((f for f in fonts if Path(f.get("file_path", "")).name == file_name), None)
        if existing is None:
            fonts.append(
                {
                    "family": family,
                    "variant": safe_variant,
                    "font_id": font_id,
                    "file_path": str(out_path.resolve()),
                }
            )
            index["fonts"] = fonts
            _save_fonts_index(index)

        return {
            "family": family,
            "variant": safe_variant,
            "file_name": out_path.name,
            "file_path": str(out_path.resolve()),
            "url": f"/fonts/{quote(out_path.name)}",
        }

    def _to_editor_payload(data: dict) -> dict:
        clips = []
        for seg in data.get("segments", []):
            clips.append(
                {
                    "id": seg.get("id"),
                    "name": seg.get("name") or Path(seg.get("clip_path", "")).name,
                    "path": seg.get("clip_path", ""),
                    "start": float(seg.get("start", 0.0)),
                    "duration": float(seg.get("duration", 4.0)),
                    "enabled": bool(seg.get("enabled", True)),
                }
            )

        return {
            "topic": data.get("topic", ""),
            "target_minutes": float(data.get("target_minutes", 10.0)),
            "desired_seconds": float(data.get("desired_seconds", 0.0)),
            "library": data.get("library", []),
            "clips": clips,
            "audio": {
                "path": data.get("voice_path", ""),
                "name": Path(data.get("voice_path", "")).name if data.get("voice_path") else "",
            },
            "subtitles": {
                "path": data.get("srt_path", ""),
                "name": Path(data.get("srt_path", "")).name if data.get("srt_path") else "",
            },
            "out_path": data.get("out_path", ""),
            "max_clip_segment_seconds": float(data.get("max_clip_segment_seconds", 6.0)),
            "subtitle_style": data.get("subtitle_style", {}),
            "overlays": data.get("overlays", []),
        }

    def _search_pexels(
        query: str,
        media_type: str,
        per_page: int = 24,
        page: int = 1,
        orientation: str = "any",
        min_duration: float = 0.0,
        max_duration: float = 0.0,
    ) -> dict:
        if not settings.PEXELS_API_KEY:
            return {"items": [], "has_more": False}

        headers = {"Authorization": settings.PEXELS_API_KEY}
        pexels_orientation = "landscape"
        if orientation in {"landscape", "portrait", "square"}:
            pexels_orientation = orientation

        if media_type == "image":
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params={"query": query, "per_page": per_page, "page": page, "orientation": pexels_orientation},
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()
            out = []
            for photo in payload.get("photos", []):
                src = photo.get("src", {}) or {}
                out.append(
                    {
                        "provider": "pexels",
                        "media_type": "image",
                        "id": str(photo.get("id")),
                        "thumb_url": src.get("medium") or src.get("small") or "",
                        "preview_url": src.get("large") or src.get("medium") or "",
                        "download_url": src.get("original") or src.get("large") or src.get("medium") or "",
                        "width": int(photo.get("width", 0) or 0),
                        "height": int(photo.get("height", 0) or 0),
                    }
                )
            total_results = int(payload.get("total_results", 0) or 0)
            has_more = (page * per_page) < total_results if total_results > 0 else len(out) >= per_page
            return {"items": out, "has_more": has_more}

        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": per_page, "page": page, "orientation": pexels_orientation},
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
        out = []
        for video in payload.get("videos", []):
            duration_val = float(video.get("duration", 0.0) or 0.0)
            if min_duration > 0 and duration_val < min_duration:
                continue
            if max_duration > 0 and duration_val > max_duration:
                continue

            files = [f for f in (video.get("video_files") or []) if f.get("file_type") == "video/mp4"]
            if not files:
                continue
            best = sorted(files, key=lambda x: (x.get("width", 0) * x.get("height", 0)), reverse=True)[0]
            out.append(
                {
                    "provider": "pexels",
                    "media_type": "video",
                    "id": str(video.get("id")),
                    "thumb_url": video.get("image", ""),
                    "preview_url": best.get("link", ""),
                    "download_url": best.get("link", ""),
                    "width": int(best.get("width", 0) or 0),
                    "height": int(best.get("height", 0) or 0),
                    "duration": duration_val,
                }
            )
        total_results = int(payload.get("total_results", 0) or 0)
        has_more = (page * per_page) < total_results if total_results > 0 else len(out) >= per_page
        return {"items": out, "has_more": has_more}

    def _search_pixabay(
        query: str,
        media_type: str,
        per_page: int = 24,
        page: int = 1,
        orientation: str = "any",
        min_duration: float = 0.0,
        max_duration: float = 0.0,
    ) -> dict:
        if not settings.PIXABAY_API_KEY:
            return {"items": [], "has_more": False}

        pixabay_orientation = "all"
        if orientation == "landscape":
            pixabay_orientation = "horizontal"
        elif orientation == "portrait":
            pixabay_orientation = "vertical"

        if media_type == "image":
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": settings.PIXABAY_API_KEY,
                    "q": query,
                    "image_type": "photo",
                    "orientation": pixabay_orientation,
                    "per_page": per_page,
                    "page": page,
                },
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()
            out = []
            for item in payload.get("hits", []):
                width_val = int(item.get("imageWidth", 0) or 0)
                height_val = int(item.get("imageHeight", 0) or 0)
                if orientation == "landscape" and width_val < height_val:
                    continue
                if orientation == "portrait" and height_val < width_val:
                    continue
                if orientation == "square" and abs(width_val - height_val) > max(80, int(0.15 * max(width_val, height_val, 1))):
                    continue
                out.append(
                    {
                        "provider": "pixabay",
                        "media_type": "image",
                        "id": str(item.get("id")),
                        "thumb_url": item.get("previewURL", ""),
                        "preview_url": item.get("webformatURL", ""),
                        "download_url": item.get("largeImageURL") or item.get("webformatURL") or "",
                        "width": width_val,
                        "height": height_val,
                    }
                )
            total_hits = int(payload.get("totalHits", 0) or 0)
            has_more = (page * per_page) < total_hits if total_hits > 0 else len(out) >= per_page
            return {"items": out, "has_more": has_more}

        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": settings.PIXABAY_API_KEY,
                "q": query,
                "per_page": per_page,
                "page": page,
            },
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()
        out = []
        for item in payload.get("hits", []):
            videos = item.get("videos", {}) or {}
            chosen = videos.get("large") or videos.get("medium") or videos.get("small") or {}
            download_url = chosen.get("url", "")
            if not download_url:
                continue

            width_val = int(chosen.get("width", 0) or 0)
            height_val = int(chosen.get("height", 0) or 0)
            if orientation == "landscape" and width_val < height_val:
                continue
            if orientation == "portrait" and height_val < width_val:
                continue

            duration_val = float(item.get("duration", 0.0) or 0.0)
            if min_duration > 0 and duration_val < min_duration:
                continue
            if max_duration > 0 and duration_val > max_duration:
                continue

            out.append(
                {
                    "provider": "pixabay",
                    "media_type": "video",
                    "id": str(item.get("id")),
                    "thumb_url": item.get("videos", {}).get("tiny", {}).get("thumbnail", "")
                    or item.get("userImageURL", ""),
                    "preview_url": download_url,
                    "download_url": download_url,
                    "width": width_val,
                    "height": height_val,
                    "duration": duration_val,
                }
            )
        total_hits = int(payload.get("totalHits", 0) or 0)
        has_more = (page * per_page) < total_hits if total_hits > 0 else len(out) >= per_page
        return {"items": out, "has_more": has_more}

    def _create_voice_from_text(text: str, tts_provider: str, voice: str, speech_rate: str) -> Path:
        tts_provider = (tts_provider or "gtts").lower()
        if tts_provider == "elevenlabs":
            if not settings.ELEVENLABS_API_KEY or not settings.ELEVENLABS_VOICE_ID:
                raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID missing in .env")
            voice_path = out_dir / "voice.mp3"
            tts_to_mp3_elevenlabs(
                text=text,
                out_path=voice_path,
                api_key=settings.ELEVENLABS_API_KEY,
                voice_id=settings.ELEVENLABS_VOICE_ID,
                model_id=settings.ELEVENLABS_MODEL,
            )
            return voice_path

        if tts_provider == "local":
            lang = (voice or "en").split("-")[0].split("_")[0].lower() or "en"
            voice_path = out_dir / "voice.wav"
            tts_to_wav_local(text=text, out_path=voice_path, lang=lang)
            return voice_path

        if tts_provider == "edge":
            voice_path = out_dir / "voice.mp3"
            try:
                tts_to_mp3_edge(text=text, out_path=voice_path, voice=voice or "en-US-EmmaNeural", rate=speech_rate or "+0%")
                return voice_path
            except Exception:
                pass

        lang = (voice or "en").split("-")[0].split("_")[0].lower() or "en"
        voice_path = out_dir / "voice.mp3"
        tts_to_mp3_gtts(text=text, out_path=voice_path, lang=lang)
        return voice_path

    def _save_from_editor(payload: dict) -> dict:
        data = load_timeline(timeline_path)

        cleaned_clips = []
        for clip in payload.get("clips", []):
            clip_path = Path(clip.get("path", "")).resolve()
            if not _is_inside(workspace_root, clip_path):
                continue
            cleaned_clips.append(
                {
                    "id": clip.get("id"),
                    "name": clip.get("name") or clip_path.name,
                    "clip_path": str(clip_path),
                    "start": max(0.0, float(clip.get("start", 0.0))),
                    "duration": max(1.0, float(clip.get("duration", 4.0))),
                    "enabled": bool(clip.get("enabled", True)),
                }
            )

        library = []
        for item in payload.get("library", data.get("library", [])):
            p = Path(item.get("path", "")).resolve() if isinstance(item, dict) else Path(str(item)).resolve()
            if not _is_inside(workspace_root, p):
                continue
            library.append(
                {
                    "id": item.get("id") if isinstance(item, dict) else None,
                    "path": str(p),
                    "name": item.get("name") if isinstance(item, dict) and item.get("name") else p.name,
                    "duration": float(item.get("duration", 0.0)) if isinstance(item, dict) else 0.0,
                }
            )

        data["segments"] = cleaned_clips
        data["library"] = library

        style = payload.get("subtitle_style", data.get("subtitle_style", {}))
        data["subtitle_style"] = {
            "font_family": str(style.get("font_family", "Arial")),
            "font_file": str(style.get("font_file", "")),
            "font_size": int(style.get("font_size", 18)),
            "primary_color": str(style.get("primary_color", "&H00FFFFFF")),
            "outline_color": str(style.get("outline_color", "&H00000000")),
            "outline": int(style.get("outline", 2)),
        }

        overlays = []
        valid_clip_ids = {c.get("id") for c in cleaned_clips}
        for ov in payload.get("overlays", data.get("overlays", [])):
            text = str(ov.get("text", "")).strip()
            if not text:
                continue

            clip_id = ov.get("clip_id")
            if clip_id and clip_id not in valid_clip_ids:
                continue

            start = float(ov.get("start", 0.0))
            end = float(ov.get("end", 0.0))
            if end <= start:
                continue

            overlays.append(
                {
                    "id": ov.get("id"),
                    "clip_id": clip_id,
                    "text": text,
                    "start": max(0.0, start),
                    "end": max(0.01, end),
                    "x": str(ov.get("x", "(w-text_w)/2")),
                    "y": str(ov.get("y", "h-160")),
                    "font_size": int(ov.get("font_size", 44)),
                    "font_color": str(ov.get("font_color", "white")),
                    "box": int(ov.get("box", 1)),
                    "box_color": str(ov.get("box_color", "black@0.45")),
                    "relative": bool(ov.get("relative", False)),
                }
            )

        data["overlays"] = overlays
        save_timeline(timeline_path, data)
        return data

    @app.get("/")
    def index():
        html_path = workspace_root / "web" / "editor.html"
        return Response(html_path.read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/api/timeline")
    def api_timeline():
        return jsonify(_to_editor_payload(load_timeline(timeline_path)))

    @app.post("/api/timeline")
    @app.put("/api/timeline")
    def api_timeline_save():
        payload = request.get_json(force=True, silent=False)
        data = _save_from_editor(payload)
        return jsonify({"ok": True, "clips": len(data.get("segments", []))})

    @app.get("/api/library")
    def api_library():
        data = load_timeline(timeline_path)
        library = data.get("library", [])
        return jsonify({"library": library})

    @app.get("/api/clip")
    def api_clip():
        clip = Path(request.args.get("path", "")).resolve()
        if not _is_inside(workspace_root, clip) or not clip.exists():
            return Response("Not found", status=404)
        return Response(clip.read_bytes(), mimetype="video/mp4")

    @app.post("/api/add")
    def api_add():
        payload = request.get_json(force=True, silent=False)
        data = load_timeline(timeline_path)
        clip = Path(payload.get("clip_path", "")).resolve()
        if not _is_inside(workspace_root, clip):
            return Response("Invalid clip path", status=400)

        data.setdefault("segments", []).append(
            {
                "clip_path": str(clip),
                "start": max(0.0, float(payload.get("start", 0))),
                "duration": max(1.0, float(payload.get("duration", 4))),
                "enabled": True,
            }
        )
        save_timeline(timeline_path, data)
        return jsonify({"ok": True})

    @app.post("/api/render")
    def api_render():
        data = load_timeline(timeline_path)
        segments = data.get("segments", [])
        if not segments:
            return Response("Timeline vacío: añade clips antes de renderizar", status=400)
        if not data.get("voice_path") or not Path(data["voice_path"]).exists():
            return Response("Falta audio: usa 'Generar guion+voz+subs'", status=400)
        if not data.get("srt_path") or not Path(data["srt_path"]).exists():
            return Response("Faltan subtítulos: usa 'Generar guion+voz+subs'", status=400)

        build_video(
            clip_paths=[],
            voice_path=Path(data["voice_path"]),
            srt_path=Path(data["srt_path"]),
            out_path=Path(data["out_path"]),
            target_minutes=float(data.get("target_minutes", 10)),
            max_clip_segment_seconds=float(data.get("max_clip_segment_seconds", 6.0)),
            timeline_segments=segments,
            subtitle_style=data.get("subtitle_style", {}),
            overlays=data.get("overlays", []),
        )
        return jsonify({"ok": True, "out_path": data["out_path"]})

    @app.get("/api/media/search")
    def api_media_search():
        query = str(request.args.get("q", "")).strip()
        media_type = str(request.args.get("type", "video")).strip().lower()
        providers = [p.strip().lower() for p in str(request.args.get("providers", "pexels,pixabay")).split(",") if p.strip()]
        page = max(1, int(request.args.get("page", "1") or 1))
        per_page = max(1, min(60, int(request.args.get("per_page", "18") or 18)))
        orientation = str(request.args.get("orientation", "any")).strip().lower()
        min_duration = max(0.0, float(request.args.get("min_duration", "0") or 0.0))
        max_duration = max(0.0, float(request.args.get("max_duration", "0") or 0.0))
        if not query:
            return jsonify({"items": [], "page": page, "per_page": per_page, "has_more": False})

        if media_type not in {"video", "image"}:
            return Response("Invalid media type", status=400)

        items = []
        has_more = False
        try:
            if "pexels" in providers:
                pexels_result = _search_pexels(
                    query=query,
                    media_type=media_type,
                    per_page=per_page,
                    page=page,
                    orientation=orientation,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )
                items.extend(pexels_result.get("items", []))
                has_more = has_more or bool(pexels_result.get("has_more", False))
            if "pixabay" in providers:
                pixabay_result = _search_pixabay(
                    query=query,
                    media_type=media_type,
                    per_page=per_page,
                    page=page,
                    orientation=orientation,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )
                items.extend(pixabay_result.get("items", []))
                has_more = has_more or bool(pixabay_result.get("has_more", False))
        except Exception as exc:
            return Response(f"Search failed: {exc}", status=502)

        return jsonify({"items": items[:120], "page": page, "per_page": per_page, "has_more": has_more})

    @app.post("/api/media/import")
    def api_media_import():
        payload = request.get_json(force=True, silent=False)
        item = payload.get("item", {}) or {}
        url = str(item.get("download_url", "")).strip()
        media_type = str(item.get("media_type", "video")).strip().lower()
        if not url:
            return Response("download_url required", status=400)

        media_id = str(item.get("id") or uuid.uuid4())
        if media_type == "image":
            image_seconds = max(1.0, float(payload.get("image_seconds", 5.0)))
            img_path = clips_dir / f"img_{media_id}.jpg"
            rr = requests.get(url, timeout=60)
            rr.raise_for_status()
            img_path.write_bytes(rr.content)

            clip_path = clips_dir / f"img_{media_id}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    f"{image_seconds:.2f}",
                    "-i",
                    str(img_path),
                    "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "30",
                    str(clip_path),
                ],
                check=True,
            )
        else:
            clip_path = clips_dir / f"clip_{media_id}.mp4"
            rr = requests.get(url, timeout=90)
            rr.raise_for_status()
            clip_path.write_bytes(rr.content)

        clip_duration = 0.0
        try:
            clip_duration = float(probe_duration_seconds(clip_path))
        except Exception:
            pass

        data = load_timeline(timeline_path)
        data.setdefault("library", []).append(
            {
                "id": str(uuid.uuid4()),
                "path": str(clip_path.resolve()),
                "name": clip_path.name,
                "duration": round(clip_duration, 3),
            }
        )

        if bool(payload.get("add_to_timeline", True)):
            data.setdefault("segments", []).append(
                {
                    "id": str(uuid.uuid4()),
                    "name": clip_path.name,
                    "clip_path": str(clip_path.resolve()),
                    "start": 0.0,
                    "duration": max(1.0, min(6.0, clip_duration if clip_duration > 0 else 6.0)),
                    "enabled": True,
                }
            )

        save_timeline(timeline_path, data)
        return jsonify({"ok": True, "path": str(clip_path.resolve())})

    @app.post("/api/project/generate")
    def api_project_generate():
        payload = request.get_json(force=True, silent=False)
        topic = str(payload.get("topic", "")).strip()
        if not topic:
            return Response("topic is required", status=400)

        minutes = float(payload.get("minutes", 8.0))
        script_provider = str(payload.get("script_provider", "auto"))
        tts_provider = str(payload.get("tts_provider", "gtts"))
        voice = str(payload.get("voice", "en-US-EmmaNeural"))
        speech_rate = str(payload.get("speech_rate", "+0%"))

        script_text = generate_script(
            topic=topic,
            target_minutes=int(max(1, round(minutes))),
            ollama_base_url=settings.OLLAMA_BASE_URL,
            ollama_model=settings.OLLAMA_MODEL,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_model=settings.OPENAI_MODEL,
            provider=script_provider,
        )

        script_path = out_dir / "script.txt"
        script_path.write_text(script_text, encoding="utf-8")

        voice_path = _create_voice_from_text(script_text, tts_provider, voice, speech_rate)
        srt_path = out_dir / "subtitles.srt"
        whisper_to_srt(audio_path=voice_path, srt_path=srt_path)

        # NO recrear timeline con segmentos automáticos.
        current = load_timeline(timeline_path)
        current["topic"] = topic
        current["target_minutes"] = float(minutes)
        current["desired_seconds"] = float(max(0.0, minutes * 60.0))
        current["voice_path"] = str(Path(voice_path).resolve())
        current["srt_path"] = str(Path(srt_path).resolve())
        current["out_path"] = str(Path(current.get("out_path") or (out_dir / "final.mp4")).resolve())
        current.setdefault("library", [])
        current.setdefault("segments", [])
        current.setdefault("overlays", [])
        save_timeline(timeline_path, current)

        return jsonify(
            {
                "ok": True,
                "topic": topic,
                "script_path": str(script_path),
                "voice_path": str(voice_path),
                "srt_path": str(srt_path),
            }
        )

    @app.get("/api/fonts/local")
    def api_fonts_local():
        return jsonify({"fonts": _list_local_fonts()})

    @app.get("/api/fonts/catalog")
    def api_fonts_catalog():
        limit = int(request.args.get("limit", "120"))
        try:
            items = _fetch_google_fonts_catalog(limit=limit)
        except Exception as exc:
            return Response(f"Failed to fetch font catalog: {exc}", status=502)
        return jsonify({"fonts": items})

    @app.post("/api/fonts/install")
    def api_fonts_install():
        payload = request.get_json(force=True, silent=False)
        font_id = str(payload.get("id", "")).strip()
        family = str(payload.get("family", "")).strip()
        variant = str(payload.get("variant", "regular")).strip() or "regular"
        if not font_id or not family:
            return Response("'id' and 'family' are required", status=400)
        try:
            font = _install_google_font(font_id=font_id, family=family, variant=variant)
        except Exception as exc:
            return Response(f"Failed to install font: {exc}", status=502)
        return jsonify({"ok": True, "font": font})

    @app.get("/fonts/<path:filename>")
    def api_font_file(filename: str):
        return send_from_directory(fonts_dir, filename, mimetype="font/ttf")

    return app


def run_editor(workspace_root: Path, timeline_path: Path, host: str = "127.0.0.1", port: int = 8765):
    app = create_app(workspace_root=workspace_root, timeline_path=timeline_path)
    url = f"http://{host}:{port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"Editor running at {url}")
    print("Use the web UI to remove/add clips, then click Render.")
    app.run(host=host, port=port, debug=False)

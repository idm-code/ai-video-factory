import json
import subprocess
import uuid
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse

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
    web_dist = workspace_root / "web" / "dist"

    app = Flask(__name__)

    def _clip_signature(items: list[dict]) -> list[tuple]:
        sig = []
        for clip in items or []:
            clip_path = str(clip.get("clip_path") or clip.get("path") or "")
            sig.append(
                (
                    str(clip.get("id") or ""),
                    str(clip.get("name") or Path(clip_path).name),
                    clip_path,
                    round(float(clip.get("start", 0.0) or 0.0), 3),
                    round(float(clip.get("duration", 4.0) or 4.0), 3),
                    bool(clip.get("enabled", True)),
                )
            )
        return sig

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
        for seg in data.get("segments", []) + data.get("clips", []):
            clips.append(
                {
                    "id": seg.get("id") or str(uuid.uuid4()),
                    "name": seg.get("name") or Path(str(seg.get("clip_path", seg.get("path", "")))).name,
                    "path": str(seg.get("path") or seg.get("clip_path", "")),
                    "start": float(seg.get("start", 0.0)),
                    "duration": float(seg.get("duration", 4.0)),
                    "enabled": bool(seg.get("enabled", True)),
                }
            )

        # Deduplicar por id
        seen = set()
        unique_clips = []
        for c in clips:
            if c["id"] not in seen:
                seen.add(c["id"])
                unique_clips.append(c)

        return {
            "topic": data.get("topic", ""),
            "target_minutes": float(data.get("target_minutes", 10.0)),
            "desired_seconds": float(data.get("desired_seconds", 0.0)),
            "script_text": data.get("script_text", "") or _read_script_text(),
            "audio_dirty": bool(data.get("audio_dirty", False)),
            "library": data.get("library", []),
            "clips": unique_clips,
            "audio": {"name": Path(data["voice_path"]).name} if data.get("voice_path") and Path(data["voice_path"]).exists() else None,
            "subtitles": {"name": Path(data["srt_path"]).name} if data.get("srt_path") and Path(data["srt_path"]).exists() else None,
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

        # Pixabay orientation params
        pixabay_orientation = "all"
        if orientation == "landscape":
            pixabay_orientation = "horizontal"
        elif orientation == "portrait":
            pixabay_orientation = "vertical"

        if media_type == "image":
            params = {
                "key": settings.PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": min(per_page, 200),
                "page": page,
                "safesearch": "true",
            }
            # orientation "all" no es válido para Pixabay images; solo horizontal/vertical
            if pixabay_orientation in ("horizontal", "vertical"):
                params["orientation"] = pixabay_orientation

            r = requests.get(
                "https://pixabay.com/api/",
                params=params,
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()
            out = []
            for item in payload.get("hits", []):
                width_val = int(item.get("imageWidth", 0) or 0)
                height_val = int(item.get("imageHeight", 0) or 0)
                # Filtro orientación en cliente para "square" y "any"
                if orientation == "square" and abs(width_val - height_val) > max(80, int(0.15 * max(width_val, height_val, 1))):
                    continue
                out.append({
                    "provider": "pixabay",
                    "media_type": "image",
                    "id": str(item.get("id")),
                    "thumb_url": item.get("previewURL", ""),
                    "preview_url": item.get("webformatURL", ""),
                    "download_url": item.get("largeImageURL") or item.get("webformatURL") or "",
                    "width": width_val,
                    "height": height_val,
                    "duration": 0,
                })
            total_hits = int(payload.get("totalHits", 0) or 0)
            has_more = (page * per_page) < total_hits if total_hits > 0 else len(out) >= per_page
            return {"items": out, "has_more": has_more}

        # ── VIDEO ──
        # La API de vídeos de Pixabay NO acepta orientation
        params = {
            "key": settings.PIXABAY_API_KEY,
            "q": query,
            "video_type": "all",
            "per_page": min(per_page, 200),
            "page": page,
            "safesearch": "true",
        }

        r = requests.get(
            "https://pixabay.com/api/videos/",
            params=params,
            timeout=20,
        )

        # Log para debug
        print(f"[Pixabay video] status={r.status_code} url={r.url}")
        if not r.ok:
            print(f"[Pixabay video] error body: {r.text[:300]}")
            r.raise_for_status()

        payload = r.json()
        print(f"[Pixabay video] totalHits={payload.get('totalHits')} hits={len(payload.get('hits', []))}")

        out = []
        for item in payload.get("hits", []):
            videos = item.get("videos", {}) or {}
            # Intentar calidades en orden descendente
            chosen = (
                videos.get("large")
                or videos.get("medium")
                or videos.get("small")
                or videos.get("tiny")
                or {}
            )
            download_url = chosen.get("url", "")
            if not download_url:
                continue

            width_val = int(chosen.get("width", 0) or 0)
            height_val = int(chosen.get("height", 0) or 0)

            # Filtro orientación manual (la API no lo soporta)
            if orientation == "landscape" and width_val > 0 and height_val > 0 and width_val < height_val:
                continue
            if orientation == "portrait" and width_val > 0 and height_val > 0 and height_val < width_val:
                continue
            if orientation == "square" and width_val > 0 and height_val > 0 and abs(width_val - height_val) > max(80, int(0.15 * max(width_val, height_val, 1))):
                continue

            duration_val = float(item.get("duration", 0.0) or 0.0)
            if min_duration > 0 and duration_val < min_duration:
                continue
            if max_duration > 0 and duration_val > max_duration:
                continue

            # Thumbnail: pixabay vídeos tiene userImageURL o videos.tiny.thumbnail
            thumb = (
                videos.get("tiny", {}).get("thumbnail", "")
                or item.get("userImageURL", "")
                or item.get("picture_id", "")
            )

            out.append({
                "provider": "pixabay",
                "media_type": "video",
                "id": str(item.get("id")),
                "thumb_url": thumb,
                "preview_url": download_url,
                "download_url": download_url,
                "width": width_val,
                "height": height_val,
                "duration": duration_val,
            })

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

        old_segments = [
            {
                "id": seg.get("id") or str(uuid.uuid4()),
                "name": seg.get("name") or Path(str(seg.get("clip_path", ""))).name,
                "clip_path": str(seg.get("clip_path", "")),
                "start": max(0.0, float(seg.get("start", 0.0))),
                "duration": max(1.0, float(seg.get("duration", 4.0))),
                "enabled": bool(seg.get("enabled", True)),
            }
            for seg in (data.get("segments", []) or [])
        ]

        cleaned_clips = old_segments
        has_clips = "clips" in payload

        if has_clips:
            cleaned_clips = []
            for clip in payload.get("clips", []):
                normalized = _normalize_editor_clip(clip)
                if normalized:
                    cleaned_clips.append(normalized)

            data["segments"] = cleaned_clips
            data["clips"] = []
            data["editor_touched"] = True

        clips_changed = _clip_signature(old_segments) != _clip_signature(cleaned_clips)
        if clips_changed:
            data["audio_dirty"] = True

        if "script_text" in payload:
            data["script_text"] = str(payload.get("script_text", "") or "")

        save_timeline(timeline_path, data)
        return data
    def _generate_script_only(payload: dict) -> dict:
        if any(k in payload for k in ("clips", "library", "overlays", "subtitle_style", "script_text")):
            _save_from_editor(payload)

        current = load_timeline(timeline_path)
        topic = str(payload.get("topic", current.get("topic", ""))).strip()
        if not topic:
            raise ValueError("topic is required")

        requested_minutes = float(payload.get("minutes", current.get("target_minutes", 8.0) or 8.0))
        script_provider = str(payload.get("script_provider", "auto")).strip() or "auto"
        script_text = str(payload.get("script_text", "")).strip()

        if not script_text:
            script_text = generate_script(
                topic=topic,
                target_minutes=max(1, int(round(requested_minutes))),
                ollama_base_url=settings.OLLAMA_BASE_URL,
                ollama_model=settings.OLLAMA_MODEL,
                openai_api_key=settings.OPENAI_API_KEY,
                openai_model=settings.OPENAI_MODEL,
                provider=script_provider,
            )

        script_path = _write_script_text(script_text)
        current["topic"] = topic
        current["target_minutes"] = float(requested_minutes)
        current["script_text"] = script_text
        current["audio_dirty"] = True
        save_timeline(timeline_path, current)

        return {
            "ok": True,
            "topic": topic,
            "script_path": str(script_path),
            "script_text": script_text,
        }

    def _generate_audio_only(payload: dict) -> dict:
        if any(k in payload for k in ("clips", "library", "overlays", "subtitle_style", "script_text")):
            _save_from_editor(payload)

        current = load_timeline(timeline_path)
        topic = str(payload.get("topic", current.get("topic", ""))).strip()
        if not topic:
            raise ValueError("topic is required")

        script_text = (
            str(payload.get("script_text", "")).strip()
            or str(current.get("script_text", "")).strip()
            or _read_script_text().strip()
        )
        if not script_text:
            raise ValueError("No hay script. Genera o pega un guion primero.")

        tts_provider = str(payload.get("tts_provider", "gtts")).strip() or "gtts"
        voice = str(payload.get("voice", "en")).strip() or "en"
        speech_rate = str(payload.get("speech_rate", "+0%")).strip() or "+0%"

        voice_path = _create_voice_from_text(script_text, tts_provider, voice, speech_rate)

        current["topic"] = topic
        current["script_text"] = script_text
        current["voice_path"] = str(Path(voice_path).resolve())
        current["audio_dirty"] = True
        save_timeline(timeline_path, current)

        return {
            "ok": True,
            "topic": topic,
            "voice_path": str(Path(voice_path).resolve()),
        }

    def _generate_subtitles_only(payload: dict) -> dict:
        if any(k in payload for k in ("clips", "library", "overlays", "subtitle_style", "script_text")):
            _save_from_editor(payload)

        current = load_timeline(timeline_path)
        voice_path = Path(str(current.get("voice_path", "") or "")).resolve()
        if not voice_path.exists():
            raise ValueError("Falta audio. Genera audio primero.")

        srt_path = out_dir / "subtitles.srt"
        whisper_to_srt(audio_path=voice_path, srt_path=srt_path)

        current["srt_path"] = str(srt_path.resolve())
        current["audio_dirty"] = False
        save_timeline(timeline_path, current)

        return {
            "ok": True,
            "voice_path": str(voice_path),
            "srt_path": str(srt_path.resolve()),
        }


    def _enabled_timeline_seconds(data: dict) -> float:
        total = 0.0
        for seg in data.get("segments", []):
            if seg.get("enabled", True):
                total += max(0.0, float(seg.get("duration", 0.0)))
        return total

    def _read_script_text() -> str:
        script_path = out_dir / "script.txt"
        if not script_path.exists():
            return ""
        try:
            return script_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _write_script_text(text: str) -> Path:
        script_path = out_dir / "script.txt"
        script_path.write_text(text, encoding="utf-8")
        return script_path

    def _is_image_file(path: Path) -> bool:
        return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    def _actual_media_duration(path: Path, fallback: float = 0.0) -> float:
        path = Path(path)
        if _is_image_file(path):
            return max(1.0, float(fallback or 6.0))
        try:
            probed = float(probe_duration_seconds(path))
            if probed > 0.05:
                return probed
        except Exception:
            pass
        return max(0.0, float(fallback or 0.0))

    def _normalize_editor_clip(raw: dict) -> Optional[dict]:
        clip_path = Path(str(raw.get("path") or raw.get("clip_path") or "")).resolve()
        if not clip_path.exists() or not _is_inside(workspace_root, clip_path):
            return None

        req_start = max(0.0, float(raw.get("start", 0.0) or 0.0))
        req_duration = max(1.0, float(raw.get("duration", 4.0) or 4.0))

        if _is_image_file(clip_path):
            start = 0.0
            duration = req_duration
        else:
            real_duration = _actual_media_duration(clip_path, req_duration)
            if real_duration <= 0.05:
                real_duration = req_duration

            start = min(req_start, max(0.0, real_duration - 0.05))
            available = max(0.05, real_duration - start)
            duration = min(req_duration, max(1.0, available))

        return {
            "id": raw.get("id") or str(uuid.uuid4()),
            "name": raw.get("name") or clip_path.name,
            "clip_path": str(clip_path),
            "start": round(float(start), 3),
            "duration": round(float(duration), 3),
            "enabled": bool(raw.get("enabled", True)),
        }

    @app.get("/")
    def index():
        html_path = workspace_root / "web" / "editor.html"
        if not html_path.exists():
            return Response("web/editor.html not found", status=500)
        resp = Response(html_path.read_text(encoding="utf-8"), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/react")
    def react_index():
        dist_index = web_dist / "index.html"
        if not dist_index.exists():
            return Response("React build not found. Run: npm --prefix web run build", status=404)
        resp = Response(dist_index.read_text(encoding="utf-8"), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.get("/assets/<path:filename>")
    def static_assets(filename: str):
        assets_dir = web_dist / "assets"
        if not assets_dir.exists():
            return Response("web/dist/assets not found", status=404)
        return send_from_directory(assets_dir, filename)

    @app.get("/api/timeline")
    def api_timeline():
        data = load_timeline(timeline_path)
        clips = []
        for seg in data.get("segments", []):
            clips.append(
                {
                    "id": seg.get("id") or str(uuid.uuid4()),
                    "name": seg.get("name") or Path(str(seg.get("clip_path", ""))).name,
                    "path": str(seg.get("clip_path", "")),
                    "start": float(seg.get("start", 0.0)),
                    "duration": float(seg.get("duration", 4.0)),
                    "enabled": bool(seg.get("enabled", True)),
                }
            )

        return jsonify(
            {
                "clips": clips,
                "script_text": data.get("script_text", ""),
                "target_minutes": data.get("target_minutes", 8),
                "topic": data.get("topic", ""),
                "voice_path": data.get("voice_path", ""),
                "srt_path": data.get("srt_path", ""),
                "audio": {"name": Path(data["voice_path"]).name} if data.get("voice_path") and Path(data["voice_path"]).exists() else None,
                "subtitles": {"name": Path(data["srt_path"]).name} if data.get("srt_path") and Path(data["srt_path"]).exists() else None,
            }
        )

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
        ext = clip.suffix.lower()
        mime_map = {
            ".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
            ".webm": "video/webm", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
        }
        mime = mime_map.get(ext, "application/octet-stream")
        return Response(clip.read_bytes(), mimetype=mime)

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
        if bool(data.get("audio_dirty", False)):
            return Response("El audio está desactualizado: genera audio+subtítulos otra vez", status=400)
        if not data.get("voice_path") or not Path(data["voice_path"]).exists():
            return Response("Falta audio", status=400)
        if not data.get("srt_path") or not Path(data["srt_path"]).exists():
            return Response("Faltan subtítulos", status=400)

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
        warnings = []

        if "pexels" in providers:
            try:
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
            except Exception as exc:
                warnings.append(f"pexels: {exc}")

        if "pixabay" in providers:
            try:
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
                warnings.append(f"pixabay: {exc}")

        if not items and warnings:
            return Response("Search failed: " + " | ".join(warnings), status=502)

        return jsonify({"items": items[:120], "page": page, "per_page": per_page, "has_more": has_more, "warnings": warnings})

    @app.post("/api/media/import")
    def api_media_import():
        import traceback
        try:
            payload = request.get_json(force=True, silent=False) or {}
            item = payload.get("item") or {}
            add_to_timeline = bool(payload.get("add_to_timeline", False))
            image_seconds = max(1.0, float(payload.get("image_seconds", 6)))
            media_type = str(item.get("media_type", "video")).lower().strip()

            source_url = (
                item.get("download_url")
                or item.get("source_url")
                or item.get("video_url")
                or item.get("image_url")
                or item.get("url")
            )
            if not source_url:
                return Response(f"missing source URL. Keys: {list(item.keys())}", status=400)

            clips_dir = workspace_root / "work" / "clips"
            clips_dir.mkdir(parents=True, exist_ok=True)

            parsed = urlparse(str(source_url))
            ext = Path(parsed.path).suffix.lower()
            if ext not in {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png"}:
                ext = ".mp4" if media_type == "video" else ".jpg"

            base_id = str(item.get("id") or uuid.uuid4())
            safe_id = "".join(c for c in base_id if c.isalnum() or c in "-_")[:60]
            clip_path = (clips_dir / f"clip_{safe_id}{ext}").resolve()

            # Descargar solo si no existe ya
            if not clip_path.exists() or clip_path.stat().st_size < 1024:
                r = requests.get(str(source_url), timeout=90, stream=True,
                                 headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                with open(clip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)

            if clip_path.stat().st_size < 1024:
                clip_path.unlink(missing_ok=True)
                return Response("downloaded file too small", status=502)

            # Duración
            if media_type == "image":
                clip_duration = max(1.0, float(image_seconds))
            else:
                fallback_duration = 0.0
                try:
                    fallback_duration = float(item.get("duration") or 0.0)
                except Exception:
                    fallback_duration = 0.0

                clip_duration = _actual_media_duration(clip_path, fallback_duration)
                if clip_duration <= 0:
                    clip_duration = max(1.0, fallback_duration or 4.0)

            clip_duration = max(1.0, round(float(clip_duration), 3))

            data = load_timeline(timeline_path)

            created_clip = None
            if add_to_timeline:
                created_clip = {
                    "id": str(uuid.uuid4()),
                    "name": clip_path.name,
                    "clip_path": str(clip_path),
                    "start": 0.0,
                    "duration": clip_duration,
                    "enabled": True,
                }
                data.setdefault("segments", []).append(created_clip)
                data["clips"] = []
                data["editor_touched"] = True
                data["audio_dirty"] = True
                save_timeline(timeline_path, data)

            return jsonify(
                {
                    "ok": True,
                    "path": str(clip_path),
                    "clip": {
                        "id": created_clip["id"],
                        "name": created_clip["name"],
                        "path": created_clip["clip_path"],
                        "start": created_clip["start"],
                        "duration": created_clip["duration"],
                        "enabled": created_clip["enabled"],
                    } if created_clip else None,
                }
            )

        except requests.RequestException as exc:
            traceback.print_exc()
            return Response(f"download failed: {exc}", status=502)
        except Exception as exc:
            traceback.print_exc()
            return Response(f"media import failed: {type(exc).__name__}: {exc}", status=500)

    @app.post("/api/script/generate")
    def api_script_generate():
        payload = request.get_json(force=True, silent=False)
        try:
            return jsonify(_generate_script_only(payload))
        except ValueError as exc:
            return Response(str(exc), status=400)
        except Exception as exc:
            return Response(f"Script generation failed: {exc}", status=500)

    @app.post("/api/audio/generate")
    def api_audio_generate():
        payload = request.get_json(force=True, silent=False)
        try:
            return jsonify(_generate_audio_only(payload))
        except ValueError as exc:
            return Response(str(exc), status=400)
        except Exception as exc:
            return Response(f"Audio generation failed: {exc}", status=500)

    @app.post("/api/subtitles/generate")
    def api_subtitles_generate():
        payload = request.get_json(force=True, silent=False)
        try:
            return jsonify(_generate_subtitles_only(payload))
        except ValueError as exc:
            return Response(str(exc), status=400)
        except Exception as exc:
            return Response(f"Subtitles generation failed: {exc}", status=500)

    @app.post("/api/project/generate")
    def api_project_generate():
        payload = request.get_json(force=True, silent=False)
        try:
            return jsonify(_generate_audio_bundle(payload))
        except ValueError as exc:
            return Response(str(exc), status=400)
        except Exception as exc:
            return Response(f"Project generation failed: {exc}", status=500)

    def _generate_audio_bundle(payload: dict) -> dict:
        # Si el cliente manda el timeline actual, persistirlo antes de calcular audio
        if any(k in payload for k in ("clips", "library", "overlays", "subtitle_style", "script_text")):
            _save_from_editor(payload)

        current = load_timeline(timeline_path)

        topic = str(payload.get("topic", current.get("topic", ""))).strip()
        if not topic:
            raise ValueError("topic is required")

        requested_minutes = float(payload.get("minutes", current.get("target_minutes", 8.0) or 8.0))
        timeline_seconds = _enabled_timeline_seconds(current)

        if timeline_seconds <= 0:
            raise ValueError("Añade clips al timeline antes de generar audio")

        effective_minutes = max(1.0, timeline_seconds / 60.0)

        script_text = str(payload.get("script_text", "")).strip()
        script_provider = str(payload.get("script_provider", "auto")).strip() or "auto"
        tts_provider = str(payload.get("tts_provider", "gtts")).strip() or "gtts"
        voice = str(payload.get("voice", "en")).strip() or "en"
        speech_rate = str(payload.get("speech_rate", "+0%")).strip() or "+0%"

        if not script_text:
            script_text = generate_script(
                topic=topic,
                target_minutes=max(1, int(round(effective_minutes))),
                ollama_base_url=settings.OLLAMA_BASE_URL,
                ollama_model=settings.OLLAMA_MODEL,
                openai_api_key=settings.OPENAI_API_KEY,
                openai_model=settings.OPENAI_MODEL,
                provider=script_provider,
            )

        script_path = _write_script_text(script_text)
        voice_path = _create_voice_from_text(script_text, tts_provider, voice, speech_rate)

        srt_path = out_dir / "subtitles.srt"
        whisper_to_srt(audio_path=voice_path, srt_path=srt_path)

        current["topic"] = topic
        current["target_minutes"] = float(requested_minutes)
        current["desired_seconds"] = float(timeline_seconds)
        current["script_text"] = script_text
        current["voice_path"] = str(Path(voice_path).resolve())
        current["srt_path"] = str(Path(srt_path).resolve())
        current["audio_dirty"] = False

        current.setdefault("library", [])
        current.setdefault("segments", [])
        current.setdefault("overlays", [])
        current.setdefault("subtitle_style", {
            "font_family": "Arial",
            "font_file": "",
            "font_size": 18,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 2,
        })

        save_timeline(timeline_path, current)

        return {
            "ok": True,
            "topic": topic,
            "script_path": str(script_path),
            "voice_path": str(Path(voice_path).resolve()),
            "srt_path": str(Path(srt_path).resolve()),
            "script_text": script_text,
            "timeline_seconds": float(timeline_seconds),
        }

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

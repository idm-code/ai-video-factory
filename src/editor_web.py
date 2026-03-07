import json
import webbrowser
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, Response, jsonify, request, send_from_directory

from .timeline import load_timeline, save_timeline
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
        build_video(
            clip_paths=[],
            voice_path=Path(data["voice_path"]),
            srt_path=Path(data["srt_path"]),
            out_path=Path(data["out_path"]),
            target_minutes=float(data.get("target_minutes", 10)),
            max_clip_segment_seconds=float(data.get("max_clip_segment_seconds", 6.0)),
            timeline_segments=data.get("segments", []),
            subtitle_style=data.get("subtitle_style", {}),
            overlays=data.get("overlays", []),
        )
        return jsonify({"ok": True, "out_path": data["out_path"]})

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

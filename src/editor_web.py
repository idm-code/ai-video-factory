import json
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request

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

    app = Flask(__name__)

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
        )
        return jsonify({"ok": True, "out_path": data["out_path"]})

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

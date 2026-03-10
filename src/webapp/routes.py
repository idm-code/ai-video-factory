from flask import Response, jsonify, request, send_from_directory

from ..timeline import load_timeline
from .fonts_service import FontsService
from .media_service import MediaService
from .project_service import ProjectService


def register_routes(app, ctx, project_service: ProjectService, media_service: MediaService, fonts_service: FontsService) -> None:
    _register_root_routes(app, ctx, project_service)
    _register_timeline_routes(app, ctx, project_service, media_service)
    _register_media_routes(app, media_service)
    _register_generation_routes(app, project_service)
    _register_font_routes(app, ctx, fonts_service)


def _register_root_routes(app, ctx, project_service: ProjectService) -> None:
    @app.get("/")
    def index():
        return project_service.serve_react_index()

    @app.get("/assets/<path:filename>")
    def static_assets(filename: str):
        assets_dir = ctx.web_dist / "assets"
        if not assets_dir.exists():
            return Response("web/dist/assets not found", status=404)
        return send_from_directory(assets_dir, filename)


def _register_timeline_routes(app, ctx, project_service: ProjectService, media_service: MediaService) -> None:
    @app.get("/api/timeline")
    def api_timeline():
        return jsonify(project_service.get_timeline_payload())

    @app.post("/api/timeline")
    @app.put("/api/timeline")
    def api_timeline_save():
        payload = request.get_json(force=True, silent=False)
        data = project_service.save_from_editor(payload)
        return jsonify({"ok": True, "clips": len(data.get("segments", []))})

    @app.get("/api/library")
    def api_library():
        data = load_timeline(ctx.timeline_path)
        return jsonify({"library": data.get("library", [])})

    @app.get("/api/clip")
    def api_clip():
        return media_service.send_clip(request.args.get("path", ""))

    @app.post("/api/render")
    def api_render():
        result = project_service.render()
        if isinstance(result, Response):
            return result
        return jsonify(result)


def _register_media_routes(app, media_service: MediaService) -> None:
    @app.get("/api/media/search")
    def api_media_search():
        params = _read_media_query_args()
        if not params["query"]:
            return jsonify({"items": [], "page": params["page"], "per_page": params["per_page"], "has_more": False})
        if params["media_type"] not in {"video", "image"}:
            return Response("Invalid media type", status=400)
        return _perform_media_search(media_service, params)

    @app.post("/api/media/import")
    def api_media_import():
        payload = request.get_json(force=True, silent=False) or {}
        return media_service.import_media_from_request(payload)


def _register_generation_routes(app, project_service: ProjectService) -> None:
    @app.post("/api/script/generate")
    def api_script_generate():
        return _handle_safe_generation(project_service.safe_generate_script)

    @app.post("/api/audio/generate")
    def api_audio_generate():
        return _handle_safe_generation(project_service.safe_generate_audio)

    @app.post("/api/subtitles/generate")
    def api_subtitles_generate():
        return _handle_safe_generation(project_service.safe_generate_subtitles)

    @app.post("/api/project/generate")
    def api_project_generate():
        return _handle_safe_generation(project_service.safe_generate_project)


def _register_font_routes(app, ctx, fonts_service: FontsService) -> None:
    @app.get("/api/fonts/local")
    def api_fonts_local():
        return jsonify({"fonts": fonts_service.list_local_fonts()})

    @app.get("/api/fonts/catalog")
    def api_fonts_catalog():
        limit = int(request.args.get("limit", "120"))
        try:
            items = fonts_service.fetch_google_fonts_catalog(limit=limit)
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
            font = fonts_service.install_google_font(font_id=font_id, family=family, variant=variant)
        except Exception as exc:
            return Response(f"Failed to install font: {exc}", status=502)
        return jsonify({"ok": True, "font": font})

    @app.get("/fonts/<path:filename>")
    def api_font_file(filename: str):
        return send_from_directory(ctx.fonts_dir, filename, mimetype="font/ttf")


def _read_media_query_args() -> dict:
    return {
        "query": str(request.args.get("q", "")).strip(),
        "media_type": str(request.args.get("type", "video")).strip().lower(),
        "providers": [p.strip().lower() for p in str(request.args.get("providers", "pexels,pixabay")).split(",") if p.strip()],
        "page": max(1, int(request.args.get("page", "1") or 1)),
        "per_page": max(1, min(60, int(request.args.get("per_page", "18") or 18))),
        "orientation": str(request.args.get("orientation", "any")).strip().lower(),
        "min_duration": max(0.0, float(request.args.get("min_duration", "0") or 0.0)),
        "max_duration": max(0.0, float(request.args.get("max_duration", "0") or 0.0)),
    }


def _perform_media_search(media_service: MediaService, params: dict):
    items = []
    has_more = False
    warnings = []
    for provider in params["providers"]:
        try:
            result = _search_provider(media_service, provider, params)
            if result is None:
                continue
            items.extend(result.get("items", []))
            has_more = has_more or bool(result.get("has_more", False))
        except Exception as exc:
            warnings.append(f"{provider}: {exc}")
    if not items and warnings:
        return Response("Search failed: " + " | ".join(warnings), status=502)
    return jsonify({
        "items": items[:120],
        "page": params["page"],
        "per_page": params["per_page"],
        "has_more": has_more,
        "warnings": warnings,
    })


def _search_provider(media_service: MediaService, provider: str, params: dict):
    args = (
        params["query"],
        params["media_type"],
        params["per_page"],
        params["page"],
        params["orientation"],
        params["min_duration"],
        params["max_duration"],
    )
    if provider == "pexels":
        return media_service.search_pexels(*args)
    if provider == "pixabay":
        return media_service.search_pixabay(*args)
    return None


def _handle_safe_generation(handler):
    payload = request.get_json(force=True, silent=False)
    result, error = handler(payload)
    return jsonify(result) if error is None else error

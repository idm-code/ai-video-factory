import webbrowser

from flask import Flask

from .context import EditorContext
from .fonts_service import FontsService
from .media_service import MediaService
from .project_service import ProjectService
from .routes import register_routes


def create_app(workspace_root, timeline_path):
    ctx = EditorContext(workspace_root=workspace_root, timeline_path=timeline_path)
    app = Flask(__name__)
    register_routes(
        app=app,
        ctx=ctx,
        project_service=ProjectService(ctx),
        media_service=MediaService(ctx),
        fonts_service=FontsService(ctx),
    )
    return app


def run_editor(workspace_root, timeline_path, host: str = "127.0.0.1", port: int = 8765):
    app = create_app(workspace_root=workspace_root, timeline_path=timeline_path)
    url = f"http://{host}:{port}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"Editor running at {url}")
    print("Use the web UI to remove/add clips, then click Render.")
    app.run(host=host, port=port, debug=False)

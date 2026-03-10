from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings


@dataclass
class EditorContext:
    workspace_root: Path
    timeline_path: Path
    settings: Settings = field(default_factory=Settings.load)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        self.timeline_path = Path(self.timeline_path).resolve()
        self.work_dir = self.workspace_root / "work"
        self.clips_dir = self.work_dir / "clips"
        self.out_dir = self.workspace_root / "output"
        self.fonts_dir = self.workspace_root / "assets" / "fonts"
        self.fonts_index_path = self.fonts_dir / "fonts_index.json"
        self.web_dist = self.workspace_root / "web" / "dist"

        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.fonts_dir.mkdir(parents=True, exist_ok=True)

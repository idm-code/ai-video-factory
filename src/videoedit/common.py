import subprocess
from pathlib import Path
from typing import Iterable

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_FILTER = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p"


def run_command(cmd: Iterable[str]) -> None:
    subprocess.run(list(cmd), check=True)


def escape_ffmpeg(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")


def is_image_path(path: Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS

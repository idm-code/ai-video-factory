from pathlib import Path

from ..utils import probe_duration_seconds


def is_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except Exception:
        return False


def is_image_file(path: Path) -> bool:
    return Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def actual_media_duration(path: Path, fallback: float = 0.0) -> float:
    path = Path(path)
    if is_image_file(path):
        return max(1.0, float(fallback or 6.0))
    try:
        probed = float(probe_duration_seconds(path))
        if probed > 0.05:
            return probed
    except Exception:
        pass
    return max(0.0, float(fallback or 0.0))


def clip_signature(items: list[dict]) -> list[tuple]:
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

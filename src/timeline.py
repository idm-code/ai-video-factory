import json
import random
from pathlib import Path

from .utils import probe_duration_seconds


def _make_segments(clip_paths, desired_seconds: float, max_clip_segment_seconds: float = 6.0):
    segments = []
    acc = 0.0
    i = 0
    while acc < desired_seconds and clip_paths:
        clip = Path(clip_paths[i % len(clip_paths)])
        dur = probe_duration_seconds(clip)
        segment_seconds = max(1.0, min(float(dur), float(max_clip_segment_seconds)))
        max_start = max(0.0, float(dur) - segment_seconds - 0.1)
        start_at = random.uniform(0.0, max_start) if max_start > 0 else 0.0
        segments.append(
            {
                "clip_path": str(clip.resolve()),
                "start": round(start_at, 3),
                "duration": round(segment_seconds, 3),
                "enabled": True,
            }
        )
        acc += segment_seconds
        i += 1
    return segments


def create_timeline_manifest(
    clip_paths,
    topic: str,
    target_minutes: float,
    voice_path: Path,
    srt_path: Path,
    out_path: Path,
    timeline_path: Path,
    max_clip_segment_seconds: float = 6.0,
):
    timeline_path = Path(timeline_path)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)

    desired_seconds = max(float(target_minutes) * 60.0, probe_duration_seconds(Path(voice_path)))
    library = [str(Path(p).resolve()) for p in clip_paths]

    data = {
        "topic": topic,
        "target_minutes": float(target_minutes),
        "voice_path": str(Path(voice_path).resolve()),
        "srt_path": str(Path(srt_path).resolve()),
        "out_path": str(Path(out_path).resolve()),
        "desired_seconds": round(desired_seconds, 3),
        "max_clip_segment_seconds": float(max_clip_segment_seconds),
        "library": library,
        "segments": _make_segments(clip_paths, desired_seconds, max_clip_segment_seconds),
    }
    timeline_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_timeline(timeline_path: Path):
    return json.loads(Path(timeline_path).read_text(encoding="utf-8"))


def save_timeline(timeline_path: Path, data):
    Path(timeline_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

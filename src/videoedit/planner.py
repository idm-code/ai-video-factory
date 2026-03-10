import random
from pathlib import Path
from typing import List, Optional, Tuple

from ..utils import probe_duration_seconds
from .common import is_image_path

UsedSegment = Tuple[Path, float, float, Optional[str]]


def desired_duration_seconds(target_minutes: float, audio_seconds: float, timeline_segments, max_clip_segment_seconds: float) -> float:
    if timeline_segments:
        return max(
            1.0,
            sum(
                max(1.0, float(segment.get("duration", max_clip_segment_seconds)))
                for segment in timeline_segments
                if segment.get("enabled", True)
            ),
        )
    return max(float(target_minutes) * 60.0, audio_seconds)


def plan_segments(clip_paths, timeline_segments, desired_seconds: float, max_clip_segment_seconds: float) -> List[UsedSegment]:
    if timeline_segments:
        used = _plan_timeline_segments(timeline_segments, max_clip_segment_seconds)
        if not used:
            raise RuntimeError("Timeline has no enabled segments.")
        return used
    return _plan_auto_segments(clip_paths, desired_seconds, max_clip_segment_seconds)


def _plan_timeline_segments(timeline_segments, max_clip_segment_seconds: float) -> List[UsedSegment]:
    used = []
    for segment in timeline_segments:
        if not segment.get("enabled", True):
            continue
        clip, segment_seconds, start_at = _timeline_segment_values(segment, max_clip_segment_seconds)
        used.append((clip, segment_seconds, start_at, segment.get("id")))
    return used


def _timeline_segment_values(segment: dict, max_clip_segment_seconds: float):
    clip = Path(segment["clip_path"])
    start_at = max(0.0, float(segment.get("start", 0.0)))
    segment_seconds = max(1.0, float(segment.get("duration", max_clip_segment_seconds)))
    if is_image_path(clip):
        return clip, segment_seconds, start_at

    real_duration = float(probe_duration_seconds(clip) or 0.0)
    if real_duration > 0.05:
        start_at = min(start_at, max(0.0, real_duration - 0.05))
        available = max(0.05, real_duration - start_at)
        segment_seconds = min(segment_seconds, max(1.0, available))
    return clip, segment_seconds, start_at


def _plan_auto_segments(clip_paths, desired_seconds: float, max_clip_segment_seconds: float) -> List[UsedSegment]:
    used = []
    accumulated = 0.0
    index = 0
    while accumulated < desired_seconds and clip_paths:
        clip = Path(clip_paths[index % len(clip_paths)])
        duration = probe_duration_seconds(clip)
        segment_seconds = max(1.0, min(float(duration), float(max_clip_segment_seconds)))
        max_start = max(0.0, float(duration) - segment_seconds - 0.1)
        start_at = random.uniform(0.0, max_start) if max_start > 0 else 0.0
        used.append((clip, segment_seconds, start_at, None))
        accumulated += segment_seconds
        index += 1
    return used


def build_used_metadata(used_segments: List[UsedSegment]) -> List[dict]:
    metadata = []
    timeline_acc = 0.0
    for clip, segment_seconds, start_at, seg_id in used_segments:
        metadata.append(
            {
                "id": seg_id,
                "duration": float(segment_seconds),
                "clip_path": str(clip),
                "start": float(start_at),
                "timeline_start": float(timeline_acc),
            }
        )
        timeline_acc += float(segment_seconds)
    return metadata

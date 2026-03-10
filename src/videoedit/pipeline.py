import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import probe_duration_seconds
from .planner import build_used_metadata, desired_duration_seconds, plan_segments
from .renderer import concat_segments, finalize_output, mux_audio, normalize_voice, output_duration, render_segments


def build_video(
    clip_paths,
    voice_path: Path,
    srt_path: Path,
    out_path: Path,
    target_minutes: float = 10,
    max_clip_segment_seconds: float = 6.0,
    timeline_segments=None,
    subtitle_style: Optional[Dict[str, Any]] = None,
    overlays: Optional[List[Dict[str, Any]]] = None,
):
    voice_path = Path(voice_path)
    srt_path = Path(srt_path)
    out_path = Path(out_path)

    _validate_inputs(clip_paths, timeline_segments)
    normalized_voice = normalize_voice(voice_path, out_path)
    audio_seconds = probe_duration_seconds(normalized_voice)
    desired_seconds = desired_duration_seconds(target_minutes, audio_seconds, timeline_segments, max_clip_segment_seconds)
    used_segments = plan_segments(clip_paths, timeline_segments, desired_seconds, max_clip_segment_seconds)
    normalized_segments = render_segments(used_segments, out_path)
    used_meta = build_used_metadata(used_segments)
    tmp_video = concat_segments(normalized_segments, out_path)
    total_seconds = _total_seconds(tmp_video, desired_seconds, bool(timeline_segments))
    tmp_av = mux_audio(tmp_video, normalized_voice, out_path, total_seconds)
    finalize_output(tmp_av, out_path, srt_path, subtitle_style, overlays, used_meta)


def _validate_inputs(clip_paths, timeline_segments) -> None:
    if not clip_paths and not timeline_segments:
        raise RuntimeError("No clips were downloaded from Pexels.")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg/ffprobe are not available in PATH.")



def _total_seconds(tmp_video: Path, desired_seconds: float, has_timeline_segments: bool) -> float:
    video_seconds = output_duration(tmp_video)
    if has_timeline_segments:
        return video_seconds
    return max(desired_seconds, video_seconds)

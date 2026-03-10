from pathlib import Path
from typing import List, Tuple

from ..utils import probe_duration_seconds
from .common import VIDEO_FILTER, is_image_path, run_command
from .filters import overlay_filters, resolve_overlays, subtitle_filter

UsedSegment = Tuple[Path, float, float, str]
VIDEO_STREAM = "0:v:0"
AUDIO_STREAM = "0:a:0"
MUX_AUDIO_STREAM = "1:a:0"


def normalize_voice(voice_path: Path, out_path: Path) -> Path:
    normalized = out_path.parent / "voice_norm.wav"
    run_command(
        [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-ac", "1",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            str(normalized),
        ]
    )
    return normalized


def render_segments(used_segments, out_path: Path) -> List[Path]:
    seg_dir = out_path.parent / "tmp_segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    normalized_segments = []

    for idx, (clip, segment_seconds, start_at, _seg_id) in enumerate(used_segments):
        seg_path = seg_dir / f"seg_{idx:04d}.mp4"

        if is_image_path(clip):
            run_command(
                [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-t", f"{segment_seconds:.3f}",
                    "-i", str(clip),
                    "-an",
                    "-vf", VIDEO_FILTER,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
                    "-pix_fmt", "yuv420p",
                    "-r", "30",
                    str(seg_path),
                ]
            )
        else:
            run_command(
                [
                    "ffmpeg", "-y",
                    "-ss", f"{start_at:.3f}",
                    "-t", f"{segment_seconds:.3f}",
                    "-i", str(clip),
                    "-an",
                    "-vf", VIDEO_FILTER,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
                    "-pix_fmt", "yuv420p",
                    "-r", "30",
                    str(seg_path),
                ]
            )

        normalized_segments.append(seg_path)

    return normalized_segments


def concat_segments(normalized_segments: List[Path], out_path: Path) -> Path:
    concat_list = out_path.parent / "concat_list.txt"
    concat_list.write_text("\n".join([f"file '{seg.as_posix()}'" for seg in normalized_segments]), encoding="utf-8")
    tmp_video = out_path.parent / "tmp_video.mp4"
    run_command(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-an",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-r", "30",
            "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            str(tmp_video),
        ]
    )
    return tmp_video


def mux_audio(tmp_video: Path, normalized_voice: Path, out_path: Path, total_seconds: float) -> Path:
    tmp_av = out_path.parent / "tmp_av.mp4"
    run_command(
        [
            "ffmpeg", "-y",
            "-i", str(tmp_video),
            "-i", str(normalized_voice),
            "-map", VIDEO_STREAM, "-map", MUX_AUDIO_STREAM,
            "-t", f"{total_seconds:.3f}",
            "-af", "apad,aresample=async=1:first_pts=0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
            "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(tmp_av),
        ]
    )
    return tmp_av


def finalize_output(tmp_av: Path, out_path: Path, srt_path: Path, subtitle_style, overlays, used_meta) -> None:
    if srt_path.exists():
        vf = ",".join([subtitle_filter(srt_path, subtitle_style)] + overlay_filters(resolve_overlays(overlays or [], used_meta), subtitle_style=subtitle_style))
        run_command(
            [
                "ffmpeg", "-y", "-i", str(tmp_av),
                "-vf", vf,
                "-map", VIDEO_STREAM, "-map", AUDIO_STREAM,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
                "-preset", "medium", "-crf", "20",
                "-c:a", "copy",
                str(out_path),
            ]
        )
        return
    run_command(
        [
            "ffmpeg", "-y", "-i", str(tmp_av),
            "-map", VIDEO_STREAM, "-map", AUDIO_STREAM,
            "-c:v", "copy",
            "-c:a", "copy",
            str(out_path),
        ]
    )


def output_duration(tmp_video: Path) -> float:
    return probe_duration_seconds(tmp_video)

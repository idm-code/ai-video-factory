import subprocess
import random
import shutil
from pathlib import Path
from .utils import probe_duration_seconds

def _run(cmd):
    subprocess.run(cmd, check=True)

def build_video(
    clip_paths,
    voice_path: Path,
    srt_path: Path,
    out_path: Path,
    target_minutes: float = 10,
    max_clip_segment_seconds: float = 6.0,
    timeline_segments=None,
):
    voice_path = Path(voice_path)
    srt_path = Path(srt_path)
    out_path = Path(out_path)

    if not clip_paths and not timeline_segments:
        raise RuntimeError("No clips were downloaded from Pexels.")

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg/ffprobe are not available in PATH.")

    target_seconds = float(target_minutes) * 60.0

    # Normalize voice to a stable format and sample rate before probing duration.
    norm_voice = out_path.parent / "voice_norm.wav"
    _run([
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-ac", "1",
        "-ar", "48000",
        "-c:a", "pcm_s16le",
        str(norm_voice),
    ])
    audio_seconds = probe_duration_seconds(norm_voice)
    desired_seconds = max(target_seconds, audio_seconds)

    # Build segment plan until the desired timeline length is covered.
    used = []
    if timeline_segments:
        for seg in timeline_segments:
            if not seg.get("enabled", True):
                continue
            clip = Path(seg["clip_path"])
            segment_seconds = max(1.0, float(seg.get("duration", max_clip_segment_seconds)))
            start_at = max(0.0, float(seg.get("start", 0.0)))
            used.append((clip, segment_seconds, start_at))

        if not used:
            raise RuntimeError("Timeline has no enabled segments.")

        acc = sum(item[1] for item in used)
        i = 0
        while acc < desired_seconds and used:
            clip, segment_seconds, start_at = used[i % len(used)]
            used.append((clip, segment_seconds, start_at))
            acc += segment_seconds
            i += 1
    else:
        acc = 0.0
        i = 0
        while acc < desired_seconds and clip_paths:
            clip = Path(clip_paths[i % len(clip_paths)])
            dur = probe_duration_seconds(clip)
            segment_seconds = max(1.0, min(float(dur), float(max_clip_segment_seconds)))
            max_start = max(0.0, float(dur) - segment_seconds - 0.1)
            start_at = random.uniform(0.0, max_start) if max_start > 0 else 0.0
            used.append((clip, segment_seconds, start_at))
            acc += segment_seconds
            i += 1

    seg_dir = out_path.parent / "tmp_segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    normalized_segments = []
    for idx, (clip, segment_seconds, start_at) in enumerate(used):
        seg_path = seg_dir / f"seg_{idx:04d}.mp4"
        _run([
            "ffmpeg", "-y",
            "-ss", f"{start_at:.3f}",
            "-t", f"{segment_seconds:.3f}",
            "-i", str(clip),
            "-an",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
            "-pix_fmt", "yuv420p",
            str(seg_path),
        ])
        normalized_segments.append(seg_path)

    concat_list = out_path.parent / "concat_list.txt"
    concat_lines = []
    for seg in normalized_segments:
        concat_lines.append(f"file '{seg.as_posix()}'")
    concat_list.write_text("\n".join(concat_lines), encoding="utf-8")

    tmp_video = out_path.parent / "tmp_video.mp4"

    # 1) concat normalized segments to CFR video
    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-r", "30",
        "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
        "-pix_fmt", "yuv420p",
        str(tmp_video)
    ])

    video_seconds = probe_duration_seconds(tmp_video)
    total_seconds = max(desired_seconds, video_seconds)

    # 3) mux video + audio
    tmp_av = out_path.parent / "tmp_av.mp4"
    _run([
        "ffmpeg", "-y",
        "-i", str(tmp_video),
        "-i", str(norm_voice),
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{total_seconds:.3f}",
        "-af", "apad,aresample=async=1:first_pts=0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
        "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(tmp_av)
    ])

    if srt_path.exists():
        # Burn subtitles (Windows-safe path escaping)
        sub = srt_path.resolve().as_posix().replace(":", r"\:").replace("'", r"\\'")
        _run([
            "ffmpeg", "-y", "-i", str(tmp_av),
            "-vf", f"subtitles='{sub}'",
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-g", "60",
            "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_path)
        ])
    else:
        _run([
            "ffmpeg", "-y", "-i", str(tmp_av),
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "copy",
            "-c:a", "copy",
            str(out_path)
        ])
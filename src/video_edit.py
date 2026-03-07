import subprocess
import random
import shutil
from pathlib import Path
from .utils import probe_duration_seconds
from typing import Optional, List, Dict, Any

def _run(cmd):
    subprocess.run(cmd, check=True)

def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")

def _subtitle_filter(srt_path: Path, style: Optional[dict]) -> str:
    srt = _esc(srt_path.resolve().as_posix())
    if not style:
        return f"subtitles='{srt}'"

    font_file = str(style.get("font_file", "")).strip()
    fonts_dir = ""
    if font_file:
        try:
            fonts_dir = _esc(str(Path(font_file).resolve().parent.as_posix()))
        except Exception:
            fonts_dir = ""

    force_style = ",".join([
        f"FontName={style.get('font_family','Montserrat')}",
        f"FontSize={style.get('font_size',18)}",
        f"PrimaryColour={style.get('primary_color','&H00FFFFFF')}",
        f"OutlineColour={style.get('outline_color','&H00000000')}",
        f"Outline={style.get('outline',2)}",
    ])

    if fonts_dir:
        return f"subtitles='{srt}':fontsdir='{fonts_dir}':force_style='{_esc(force_style)}'"
    return f"subtitles='{srt}':force_style='{_esc(force_style)}'"

def _overlay_filters(overlays: list[dict], subtitle_style: Optional[dict] = None) -> list[str]:
    out = []
    default_font_file = ""
    if subtitle_style:
        default_font_file = str(subtitle_style.get("font_file", "")).strip()

    for ov in overlays or []:
        txt = _esc(ov.get("text",""))
        start = float(ov.get("start", 0))
        end = float(ov.get("end", 0))
        if not txt or end <= start:
            continue

        font_file = str(ov.get("font_file", "") or default_font_file).strip()
        font_file_part = ""
        if font_file:
            try:
                font_file_part = f"fontfile='{_esc(Path(font_file).resolve().as_posix())}':"
            except Exception:
                font_file_part = ""

        out.append(
            "drawtext="
            f"text='{txt}':"
            f"{font_file_part}"
            f"x={ov.get('x','(w-text_w)/2')}:y={ov.get('y','h-160')}:"
            f"fontsize={int(ov.get('font_size',44))}:"
            f"fontcolor={ov.get('font_color','white')}:"
            f"box={int(ov.get('box',1))}:"
            f"boxcolor={ov.get('box_color','black@0.45')}:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    return out


def _resolve_overlays(overlays: list[dict], used_segments: list[dict]) -> list[dict]:
    if not overlays:
        return []

    resolved = []
    for ov in overlays:
        text = str(ov.get("text", "")).strip()
        if not text:
            continue

        clip_id = ov.get("clip_id")
        relative = bool(ov.get("relative", False))

        if clip_id:
            match = next((seg for seg in used_segments if seg.get("id") == clip_id), None)
            if not match:
                continue

            seg_t0 = float(match.get("timeline_start", 0.0))
            seg_len = float(match.get("duration", 0.0))
            if relative or clip_id:
                rel_start = max(0.0, float(ov.get("start", 0.0)))
                rel_end = max(rel_start + 0.01, float(ov.get("end", rel_start + 1.0)))
                abs_start = seg_t0 + min(rel_start, max(seg_len - 0.01, 0.0))
                abs_end = seg_t0 + min(rel_end, seg_len)
            else:
                abs_start = max(0.0, float(ov.get("start", 0.0)))
                abs_end = max(abs_start + 0.01, float(ov.get("end", abs_start + 1.0)))
        else:
            abs_start = max(0.0, float(ov.get("start", 0.0)))
            abs_end = max(abs_start + 0.01, float(ov.get("end", abs_start + 1.0)))

        if abs_end <= abs_start:
            continue

        resolved.append({
            "text": text,
            "start": abs_start,
            "end": abs_end,
            "x": ov.get("x", "(w-text_w)/2"),
            "y": ov.get("y", "h-160"),
            "font_size": ov.get("font_size", 44),
            "font_color": ov.get("font_color", "white"),
            "box": ov.get("box", 1),
            "box_color": ov.get("box_color", "black@0.45"),
        })

    return resolved

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
            used.append((clip, segment_seconds, start_at, seg.get("id")))

        if not used:
            raise RuntimeError("Timeline has no enabled segments.")

        acc = sum(item[1] for item in used)
        i = 0
        while acc < desired_seconds and used:
            clip, segment_seconds, start_at, seg_id = used[i % len(used)]
            used.append((clip, segment_seconds, start_at, seg_id))
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
            used.append((clip, segment_seconds, start_at, None))
            acc += segment_seconds
            i += 1

    seg_dir = out_path.parent / "tmp_segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    normalized_segments = []
    used_meta = []
    timeline_acc = 0.0
    for idx, (clip, segment_seconds, start_at, seg_id) in enumerate(used):
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
        used_meta.append(
            {
                "id": seg_id,
                "duration": float(segment_seconds),
                "timeline_start": float(timeline_acc),
            }
        )
        timeline_acc += float(segment_seconds)

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
        overlay_filters = _overlay_filters(_resolve_overlays(overlays or [], used_meta), subtitle_style=subtitle_style)
        vf_parts = [_subtitle_filter(srt_path, subtitle_style)] + overlay_filters
        vf = ",".join(vf_parts)
        _run([
            "ffmpeg", "-y", "-i", str(tmp_av),
            "-vf", vf,
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
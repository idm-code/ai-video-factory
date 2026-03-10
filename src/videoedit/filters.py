from pathlib import Path
from typing import Dict, List, Optional

from .common import escape_ffmpeg


def subtitle_filter(srt_path: Path, style: Optional[dict]) -> str:
    srt = escape_ffmpeg(srt_path.resolve().as_posix())
    if not style:
        return f"subtitles='{srt}'"

    font_file = str(style.get("font_file", "")).strip()
    fonts_dir = ""
    if font_file:
        try:
            fonts_dir = escape_ffmpeg(str(Path(font_file).resolve().parent.as_posix()))
        except Exception:
            fonts_dir = ""

    force_style = ",".join(
        [
            f"FontName={style.get('font_family', 'Montserrat')}",
            f"FontSize={style.get('font_size', 18)}",
            f"PrimaryColour={style.get('primary_color', '&H00FFFFFF')}",
            f"OutlineColour={style.get('outline_color', '&H00000000')}",
            f"Outline={style.get('outline', 2)}",
        ]
    )
    if fonts_dir:
        return f"subtitles='{srt}':fontsdir='{fonts_dir}':force_style='{escape_ffmpeg(force_style)}'"
    return f"subtitles='{srt}':force_style='{escape_ffmpeg(force_style)}'"


def overlay_filters(overlays: List[dict], subtitle_style: Optional[dict] = None) -> List[str]:
    filters = []
    default_font_file = str((subtitle_style or {}).get("font_file", "")).strip()
    for overlay in overlays or []:
        payload = _overlay_filter_payload(overlay, default_font_file)
        if payload is not None:
            filters.append(payload)
    return filters


def resolve_overlays(overlays: List[dict], used_segments: List[dict]) -> List[dict]:
    resolved = []
    for overlay in overlays or []:
        payload = _resolve_single_overlay(overlay, used_segments)
        if payload is not None:
            resolved.append(payload)
    return resolved


def _overlay_filter_payload(overlay: dict, default_font_file: str) -> Optional[str]:
    text = escape_ffmpeg(overlay.get("text", ""))
    start = float(overlay.get("start", 0))
    end = float(overlay.get("end", 0))
    if not text or end <= start:
        return None

    font_file = str(overlay.get("font_file", "") or default_font_file).strip()
    font_file_part = _font_file_part(font_file)
    return (
        "drawtext="
        f"text='{text}':"
        f"{font_file_part}"
        f"x={overlay.get('x', '(w-text_w)/2')}:y={overlay.get('y', 'h-160')}:"
        f"fontsize={int(overlay.get('font_size', 44))}:"
        f"fontcolor={overlay.get('font_color', 'white')}:"
        f"box={int(overlay.get('box', 1))}:"
        f"boxcolor={overlay.get('box_color', 'black@0.45')}:"
        f"enable='between(t,{start:.3f},{end:.3f})'"
    )


def _font_file_part(font_file: str) -> str:
    if not font_file:
        return ""
    try:
        return f"fontfile='{escape_ffmpeg(Path(font_file).resolve().as_posix())}':"
    except Exception:
        return ""


def _resolve_single_overlay(overlay: dict, used_segments: List[dict]) -> Optional[dict]:
    text = str(overlay.get("text", "")).strip()
    if not text:
        return None

    clip_id = overlay.get("clip_id")
    if clip_id:
        absolute_times = _resolve_clip_overlay_times(overlay, used_segments, clip_id)
        if absolute_times is None:
            return None
        abs_start, abs_end = absolute_times
    else:
        abs_start, abs_end = _resolve_absolute_overlay_times(overlay)

    if abs_end <= abs_start:
        return None
    return {
        "text": text,
        "start": abs_start,
        "end": abs_end,
        "x": overlay.get("x", "(w-text_w)/2"),
        "y": overlay.get("y", "h-160"),
        "font_size": overlay.get("font_size", 44),
        "font_color": overlay.get("font_color", "white"),
        "box": overlay.get("box", 1),
        "box_color": overlay.get("box_color", "black@0.45"),
    }


def _resolve_clip_overlay_times(overlay: dict, used_segments: List[dict], clip_id: str):
    match = next((segment for segment in used_segments if segment.get("id") == clip_id), None)
    if not match:
        return None
    seg_t0 = float(match.get("timeline_start", 0.0))
    seg_len = float(match.get("duration", 0.0))
    rel_start = max(0.0, float(overlay.get("start", 0.0)))
    rel_end = max(rel_start + 0.01, float(overlay.get("end", rel_start + 1.0)))
    abs_start = seg_t0 + min(rel_start, max(seg_len - 0.01, 0.0))
    abs_end = seg_t0 + min(rel_end, seg_len)
    return abs_start, abs_end


def _resolve_absolute_overlay_times(overlay: dict):
    abs_start = max(0.0, float(overlay.get("start", 0.0)))
    abs_end = max(abs_start + 0.01, float(overlay.get("end", abs_start + 1.0)))
    return abs_start, abs_end

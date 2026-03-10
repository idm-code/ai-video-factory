import uuid
from pathlib import Path

from ..timeline import load_timeline, save_timeline
from ..utils import probe_duration_seconds

DEFAULT_SUBTITLE_STYLE = {
    "font_family": "Arial",
    "font_file": "",
    "font_size": 18,
    "primary_color": "&H00FFFFFF",
    "outline_color": "&H00000000",
    "outline": 2,
}


def empty_timeline(out_final: Path) -> dict:
    return {
        "topic": "",
        "target_minutes": 8.0,
        "desired_seconds": 0.0,
        "voice_path": "",
        "srt_path": "",
        "out_path": str(out_final.resolve()),
        "max_clip_segment_seconds": 6.0,
        "subtitle_style": DEFAULT_SUBTITLE_STYLE.copy(),
        "audio_dirty": False,
        "editor_touched": False,
        "overlays": [],
        "library": [],
        "clips": [],
        "segments": [],
    }


def bootstrap_timeline(root: Path, timeline_path: Path, topic: str, minutes: float) -> dict:
    out_dir = root / "output"
    clips_dir = root / "work" / "clips"
    out_final = out_dir / "final.mp4"
    data = _load_existing_timeline(timeline_path, out_final)
    changed = False

    changed |= _ensure_output_path(data, out_final)
    changed |= _ensure_topic(data, topic)
    changed |= _ensure_target_minutes(data, minutes)
    changed |= _restore_generated_files(data, out_dir)
    changed |= _restore_script_text(data, out_dir)
    changed |= _populate_library(data, clips_dir)

    if not bool(data.get("editor_touched", False)) and looks_autofilled_from_library(data):
        data["segments"] = []
        data["clips"] = []
        data["desired_seconds"] = 0.0
        data["audio_dirty"] = True
        changed = True

    if changed:
        save_timeline(timeline_path, data)
    return data


def looks_autofilled_from_library(timeline_data: dict) -> bool:
    segments = timeline_data.get("segments") or []
    library = timeline_data.get("library") or []
    if not _autofill_shape_is_possible(segments, library):
        return False

    unique_paths = _autofill_unique_paths(segments, _library_durations(library))
    if unique_paths is None:
        return False

    return len(unique_paths) <= max(1, len(library))


def _autofill_shape_is_possible(segments, library) -> bool:
    if not isinstance(segments, list) or not isinstance(library, list):
        return False
    return len(library) >= 2 and len(segments) > len(library)


def _library_durations(library: list[dict]) -> dict:
    durations = {}
    for item in library:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        try:
            durations[path] = float(item.get("duration", 0.0) or 0.0)
        except Exception:
            durations[path] = 0.0
    return durations


def _autofill_unique_paths(segments: list[dict], lib_durations: dict):
    unique_paths = set()
    for segment in segments:
        if not isinstance(segment, dict):
            return None
        path = str(segment.get("clip_path", ""))
        if not path:
            return None
        unique_paths.add(path)
        try:
            if abs(float(segment.get("start", 0.0) or 0.0)) > 1e-6:
                return None
        except Exception:
            return None
        if path in lib_durations and lib_durations[path] > 0 and not _matches_library_duration(segment, lib_durations[path]):
            return None
    return unique_paths


def _matches_library_duration(segment: dict, library_duration: float) -> bool:
    try:
        segment_duration = float(segment.get("duration", 0.0) or 0.0)
    except Exception:
        return False
    return abs(segment_duration - library_duration) <= 0.15


def _load_existing_timeline(timeline_path: Path, out_final: Path) -> dict:
    if timeline_path.exists():
        try:
            return load_timeline(timeline_path)
        except Exception:
            pass
    return empty_timeline(out_final)


def _ensure_output_path(data: dict, out_final: Path) -> bool:
    if str(data.get("out_path", "")).strip():
        return False
    data["out_path"] = str(out_final.resolve())
    return True


def _ensure_topic(data: dict, topic: str) -> bool:
    if not topic or str(data.get("topic", "")).strip():
        return False
    data["topic"] = topic
    return True


def _ensure_target_minutes(data: dict, minutes: float) -> bool:
    if data.get("target_minutes"):
        return False
    data["target_minutes"] = float(minutes)
    return True


def _restore_generated_files(data: dict, out_dir: Path) -> bool:
    changed = False
    if not str(data.get("voice_path", "")).strip():
        for candidate in (out_dir / "voice.mp3", out_dir / "voice.wav"):
            if candidate.exists():
                data["voice_path"] = str(candidate.resolve())
                changed = True
                break
    srt_candidate = out_dir / "subtitles.srt"
    if not str(data.get("srt_path", "")).strip() and srt_candidate.exists():
        data["srt_path"] = str(srt_candidate.resolve())
        changed = True
    return changed


def _restore_script_text(data: dict, out_dir: Path) -> bool:
    if str(data.get("script_text", "")).strip():
        return False
    script_candidate = out_dir / "script.txt"
    if not script_candidate.exists():
        return False
    try:
        data["script_text"] = script_candidate.read_text(encoding="utf-8")
        return True
    except Exception:
        return False


def _populate_library(data: dict, clips_dir: Path) -> bool:
    if data.get("library"):
        return False
    library = []
    for clip_path in sorted(clips_dir.glob("*.mp4")):
        try:
            duration = round(float(probe_duration_seconds(clip_path)), 3)
        except Exception:
            duration = 0.0
        library.append(
            {
                "id": str(uuid.uuid4()),
                "path": str(clip_path.resolve()),
                "name": clip_path.name,
                "duration": duration,
            }
        )
    if not library:
        return False
    data["library"] = library
    return True

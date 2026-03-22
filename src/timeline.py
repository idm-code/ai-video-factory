import json
import random
import uuid
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
    library_paths = [str(Path(p).resolve()) for p in clip_paths]
    library = []
    for p in library_paths:
        clip_path = Path(p)
        try:
            clip_duration = round(float(probe_duration_seconds(clip_path)), 3)
        except Exception:
            clip_duration = 0.0
        library.append(
            {
                "id": str(uuid.uuid4()),
                "path": str(clip_path),
                "name": clip_path.name,
                "duration": clip_duration,
            }
        )

    segments = _make_segments(clip_paths, desired_seconds, max_clip_segment_seconds)
    for s in segments:
        s["id"] = str(uuid.uuid4())
        s["name"] = Path(s["clip_path"]).name

    data = {
        "topic": topic,
        "target_minutes": float(target_minutes),
        "voice_path": str(Path(voice_path).resolve()),
        "srt_path": str(Path(srt_path).resolve()),
        "out_path": str(Path(out_path).resolve()),
        "desired_seconds": round(desired_seconds, 3),
        "script_text": "",
        "audio_dirty": False,
        "max_clip_segment_seconds": float(max_clip_segment_seconds),
        "subtitle_style": {
            "font_family": "Arial",
            "font_file": "",
            "font_size": 18,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 2,
        },
        "overlays": [],
        "library": library,
        "segments": segments,
    }
    timeline_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_timeline(timeline_path: Path):
    timeline_path = Path(timeline_path)
    data = json.loads(timeline_path.read_text(encoding="utf-8"))
    changed = False

    data.setdefault(
        "subtitle_style",
        {
            "font_family": "Arial",
            "font_file": "",
            "font_size": 18,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 2,
        },
    )
    data.setdefault("overlays", [])
    data.setdefault("editor_touched", False)
    data.setdefault("clips", [])

    if data.get("library") and isinstance(data["library"][0], str):
        upgraded_library = []
        for p in data["library"]:
            clip_path = Path(p)
            try:
                clip_duration = round(float(probe_duration_seconds(clip_path)), 3)
            except Exception:
                clip_duration = 0.0
            upgraded_library.append(
                {
                    "id": str(uuid.uuid4()),
                    "path": str(clip_path),
                    "name": clip_path.name,
                    "duration": clip_duration,
                }
            )
        data["library"] = upgraded_library
        changed = True

    upgraded_segments = []
    for seg in data.get("segments", []):
        clip_path = str(seg.get("clip_path", seg.get("path", "")))
        upgraded_segments.append(
            {
                "id": seg.get("id") or str(uuid.uuid4()),
                "name": seg.get("name") or Path(clip_path).name,
                "clip_path": clip_path,
                "start": float(seg.get("start", 0.0)),
                "duration": float(seg.get("duration", 4.0)),
                "enabled": bool(seg.get("enabled", True)),
            }
        )
    data["segments"] = upgraded_segments

    # Campo legacy del editor React: clips.
    # La fuente canónica debe ser siempre segments.
    legacy_clips = data.get("clips", []) or []
    if legacy_clips:
        if not data["segments"] and not bool(data.get("editor_touched", False)):
            migrated = []
            for seg in legacy_clips:
                clip_path = str(seg.get("clip_path") or seg.get("path") or "")
                if not clip_path:
                    continue
                migrated.append(
                    {
                        "id": seg.get("id") or str(uuid.uuid4()),
                        "name": seg.get("name") or Path(clip_path).name,
                        "clip_path": clip_path,
                        "start": float(seg.get("start", 0.0)),
                        "duration": float(seg.get("duration", 4.0)),
                        "enabled": bool(seg.get("enabled", True)),
                    }
                )
            if migrated:
                data["segments"] = migrated

        data["clips"] = []
        changed = True

    # Migra timelines heredados donde la duración de segmentos quedó capada a 6.0s
    # al importar media, usando la duración real existente en biblioteca para ese clip.
    max_cap = float(data.get("max_clip_segment_seconds", 6.0) or 6.0)
    lib_duration_by_path = {
        str(item.get("path", "")): float(item.get("duration", 0.0) or 0.0)
        for item in data.get("library", [])
        if isinstance(item, dict)
    }
    for seg in data.get("segments", []):
        seg_path = str(seg.get("clip_path", ""))
        seg_duration = float(seg.get("duration", 0.0) or 0.0)
        seg_start = float(seg.get("start", 0.0) or 0.0)
        lib_duration = float(lib_duration_by_path.get(seg_path, 0.0) or 0.0)

        is_legacy_capped = seg_start == 0.0 and abs(seg_duration - max_cap) < 1e-6 and lib_duration > seg_duration
        if is_legacy_capped:
            seg["duration"] = round(max(1.0, lib_duration), 3)
            changed = True

    upgraded_overlays = []
    for ov in data.get("overlays", []):
        text = str(ov.get("text", "")).strip()
        if not text:
            continue
        upgraded_overlays.append(
            {
                "id": ov.get("id") or str(uuid.uuid4()),
                "clip_id": ov.get("clip_id"),
                "text": text,
                "start": float(ov.get("start", 0.0)),
                "end": float(ov.get("end", 0.0)),
                "x": ov.get("x", "(w-text_w)/2"),
                "y": ov.get("y", "h-160"),
                "font_size": int(ov.get("font_size", 44)),
                "font_color": ov.get("font_color", "white"),
                "box": int(ov.get("box", 1)),
                "box_color": ov.get("box_color", "black@0.45"),
                "relative": bool(ov.get("relative", False)),
            }
        )
    data["overlays"] = upgraded_overlays
    data.setdefault("script_text", "")
    data.setdefault("audio_dirty", False)

    try:
        data["audio_offset_seconds"] = float(data.get("audio_offset_seconds", 0.0) or 0.0)
    except Exception:
        data["audio_offset_seconds"] = 0.0
        changed = True

    if changed:
        timeline_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return data


def save_timeline(timeline_path: Path, data):
    Path(timeline_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_clip(timeline: dict, clip_id: str) -> dict:
    """Devuelve una copia profunda del clip con un nuevo ID único."""
    import copy, uuid
    for track in timeline.get("tracks", []):
        for clip in track.get("clips", []):
            if clip["id"] == clip_id:
                new_clip = copy.deepcopy(clip)
                new_clip["id"] = str(uuid.uuid4())
                return new_clip
    raise ValueError(f"Clip '{clip_id}' no encontrado en el timeline.")


def paste_clip(timeline: dict, clip: dict, track_index: int, start: float) -> dict:
    """Inserta el clip copiado en el track indicado con el nuevo tiempo de inicio."""
    import copy
    new_clip = copy.deepcopy(clip)
    new_clip["start"] = start
    new_clip["end"] = start + (clip["end"] - clip["start"])
    tracks = timeline.get("tracks", [])
    if track_index < 0 or track_index >= len(tracks):
        raise IndexError(f"Track index {track_index} fuera de rango.")
    tracks[track_index]["clips"].append(new_clip)
    # Ordenar clips por start
    tracks[track_index]["clips"].sort(key=lambda c: c["start"])
    return timeline

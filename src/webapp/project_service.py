import traceback
import uuid
from pathlib import Path
from typing import Optional

from flask import Response

from ..script_gen import generate_script
from ..subtitles import whisper_to_srt
from ..timeline import load_timeline, save_timeline
from ..tts_edge import tts_to_mp3_edge
from ..tts_elevenlabs import tts_to_mp3_elevenlabs
from ..tts_gtts import tts_to_mp3_gtts
from ..tts_local import tts_to_wav_local
from ..video_edit import build_video
from .common import actual_media_duration, clip_signature, is_image_file, is_inside
from .context import EditorContext

TOPIC_REQUIRED = "topic is required"
VOICE_MP3 = "voice.mp3"
DEFAULT_SUBTITLE_STYLE = {
    "font_family": "Arial",
    "font_file": "",
    "font_size": 18,
    "primary_color": "&H00FFFFFF",
    "outline_color": "&H00000000",
    "outline": 2,
}


class ProjectService:
    def __init__(self, ctx: EditorContext):
        self.ctx = ctx

    def serve_react_index(self):
        dist_index = self.ctx.web_dist / "index.html"
        if not dist_index.exists():
            return Response(
                "React build not found. Run: npm --prefix web install && npm --prefix web run build",
                status=404,
            )
        resp = Response(dist_index.read_text(encoding="utf-8"), mimetype="text/html")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    def persist_editor_payload_if_present(self, payload: dict) -> None:
        if any(key in payload for key in ("clips", "library", "overlays", "subtitle_style", "script_text")):
            self.save_from_editor(payload)

    def read_script_text(self) -> str:
        script_path = self.ctx.out_dir / "script.txt"
        if not script_path.exists():
            return ""
        try:
            return script_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def write_script_text(self, text: str) -> Path:
        script_path = self.ctx.out_dir / "script.txt"
        script_path.write_text(text, encoding="utf-8")
        return script_path

    def enabled_timeline_seconds(self, data: dict) -> float:
        total = 0.0
        for seg in data.get("segments", []):
            if seg.get("enabled", True):
                total += max(0.0, float(seg.get("duration", 0.0)))
        return total

    def normalize_editor_clip(self, raw: dict) -> Optional[dict]:
        clip_path = Path(str(raw.get("path") or raw.get("clip_path") or "")).resolve()
        if not clip_path.exists() or not is_inside(self.ctx.workspace_root, clip_path):
            return None

        req_start = max(0.0, float(raw.get("start", 0.0) or 0.0))
        req_duration = max(1.0, float(raw.get("duration", 4.0) or 4.0))
        if is_image_file(clip_path):
            start = 0.0
            duration = req_duration
        else:
            real_duration = actual_media_duration(clip_path, req_duration)
            if real_duration <= 0.05:
                real_duration = req_duration
            start = min(req_start, max(0.0, real_duration - 0.05))
            available = max(0.05, real_duration - start)
            duration = min(req_duration, max(1.0, available))

        return {
            "id": raw.get("id") or str(uuid.uuid4()),
            "name": raw.get("name") or clip_path.name,
            "clip_path": str(clip_path),
            "start": round(float(start), 3),
            "duration": round(float(duration), 3),
            "enabled": bool(raw.get("enabled", True)),
        }

    def get_timeline_payload(self) -> dict:
        data = load_timeline(self.ctx.timeline_path)
        clips = [self._segment_to_editor_clip(seg) for seg in data.get("segments", [])]
        return {
            "clips": clips,
            "script_text": data.get("script_text", ""),
            "target_minutes": data.get("target_minutes", 8),
            "topic": data.get("topic", ""),
            "voice_path": data.get("voice_path", ""),
            "srt_path": data.get("srt_path", ""),
            "audio": {"name": Path(data["voice_path"]).name} if data.get("voice_path") and Path(data["voice_path"]).exists() else None,
            "subtitles": {"name": Path(data["srt_path"]).name} if data.get("srt_path") and Path(data["srt_path"]).exists() else None,
        }

    def save_from_editor(self, payload: dict) -> dict:
        data = load_timeline(self.ctx.timeline_path)
        old_segments = self._clean_segments(data.get("segments", []) or [])
        cleaned_clips = old_segments
        if "clips" in payload:
            cleaned_clips = self._normalize_payload_clips(payload.get("clips", []))
            data["segments"] = cleaned_clips
            data["clips"] = []
            data["editor_touched"] = True
        self._apply_dirty_flag(data, old_segments, cleaned_clips)
        self._apply_editor_metadata(data, payload)
        save_timeline(self.ctx.timeline_path, data)
        return data

    def create_voice_from_text(self, text: str, tts_provider: str, voice: str, speech_rate: str) -> Path:
        tts_provider = (tts_provider or "gtts").lower()
        if tts_provider == "elevenlabs":
            return self._create_elevenlabs_voice(text)
        if tts_provider == "local":
            return self._create_local_voice(text, voice)
        if tts_provider == "edge":
            voice_path = self._edge_voice(text, voice, speech_rate)
            if voice_path is not None:
                return voice_path
        return self._create_gtts_voice(text, voice)

    def generate_script_only(self, payload: dict) -> dict:
        self.persist_editor_payload_if_present(payload)
        current = load_timeline(self.ctx.timeline_path)
        topic = self._resolve_topic(payload, current)
        requested_minutes = float(payload.get("minutes", current.get("target_minutes", 8.0) or 8.0))
        script_provider = str(payload.get("script_provider", "auto")).strip() or "auto"
        script_text = str(payload.get("script_text", "")).strip() or self._generate_script(topic, requested_minutes, script_provider)
        script_path = self.write_script_text(script_text)
        current["topic"] = topic
        current["target_minutes"] = float(requested_minutes)
        current["script_text"] = script_text
        current["audio_dirty"] = True
        save_timeline(self.ctx.timeline_path, current)
        return {"ok": True, "topic": topic, "script_path": str(script_path), "script_text": script_text}

    def generate_audio_only(self, payload: dict) -> dict:
        self.persist_editor_payload_if_present(payload)
        current = load_timeline(self.ctx.timeline_path)
        topic = self._resolve_topic(payload, current)
        timeline_seconds = self.enabled_timeline_seconds(current)
        if timeline_seconds <= 0:
            raise ValueError("Añade clips al timeline antes de generar audio")
        script_text = self._resolve_script_text(payload, current)
        if not script_text:
            raise ValueError("Falta script_text")

        requested_minutes = float(payload.get("minutes", current.get("target_minutes", 8.0) or 8.0))
        effective_minutes = max(1.0, timeline_seconds / 60.0)
        tts_provider = str(payload.get("tts_provider", "gtts")).strip() or "gtts"
        voice = str(payload.get("voice", "en")).strip() or "en"
        speech_rate = str(payload.get("speech_rate", "+0%")).strip() or "+0%"

        voice_path = self.create_voice_from_text(text=script_text, tts_provider=tts_provider, voice=voice, speech_rate=speech_rate)
        current["topic"] = topic
        current["target_minutes"] = float(requested_minutes)
        current["desired_seconds"] = float(max(timeline_seconds, effective_minutes * 60.0))
        current["script_text"] = script_text
        current["voice_path"] = str(Path(voice_path).resolve())
        current["audio_dirty"] = False
        save_timeline(self.ctx.timeline_path, current)
        self.write_script_text(script_text)
        return {"ok": True, "voice_path": str(Path(voice_path).resolve())}

    def generate_subtitles_only(self, payload: dict) -> dict:
        self.persist_editor_payload_if_present(payload)
        current = load_timeline(self.ctx.timeline_path)
        voice_path = Path(str(current.get("voice_path", "") or "")).resolve()
        if not voice_path.exists():
            raise ValueError("Falta audio. Genera audio primero.")
        srt_path = self.ctx.out_dir / "subtitles.srt"
        whisper_to_srt(audio_path=voice_path, srt_path=srt_path)
        current["srt_path"] = str(srt_path.resolve())
        current["audio_dirty"] = False
        save_timeline(self.ctx.timeline_path, current)
        return {"ok": True, "voice_path": str(voice_path), "srt_path": str(srt_path.resolve())}

    def generate_audio_bundle(self, payload: dict) -> dict:
        self.persist_editor_payload_if_present(payload)
        current = load_timeline(self.ctx.timeline_path)
        topic = self._resolve_topic(payload, current)
        requested_minutes = float(payload.get("minutes", current.get("target_minutes", 8.0) or 8.0))
        timeline_seconds = self.enabled_timeline_seconds(current)
        if timeline_seconds <= 0:
            raise ValueError("Añade clips al timeline antes de generar audio")

        effective_minutes = max(1.0, timeline_seconds / 60.0)
        script_text = str(payload.get("script_text", "")).strip()
        script_provider = str(payload.get("script_provider", "auto")).strip() or "auto"
        tts_provider = str(payload.get("tts_provider", "gtts")).strip() or "gtts"
        voice = str(payload.get("voice", "en")).strip() or "en"
        speech_rate = str(payload.get("speech_rate", "+0%")).strip() or "+0%"
        if not script_text:
            script_text = self._generate_script(topic, effective_minutes, script_provider)

        script_path = self.write_script_text(script_text)
        voice_path = self.create_voice_from_text(script_text, tts_provider, voice, speech_rate)
        srt_path = self.ctx.out_dir / "subtitles.srt"
        whisper_to_srt(audio_path=voice_path, srt_path=srt_path)

        current["topic"] = topic
        current["target_minutes"] = float(requested_minutes)
        current["desired_seconds"] = float(max(timeline_seconds, effective_minutes * 60.0))
        current["script_text"] = script_text
        current["voice_path"] = str(Path(voice_path).resolve())
        current["srt_path"] = str(Path(srt_path).resolve())
        current["audio_dirty"] = False
        current.setdefault("library", [])
        current.setdefault("segments", [])
        current.setdefault("overlays", [])
        current.setdefault("subtitle_style", DEFAULT_SUBTITLE_STYLE.copy())
        save_timeline(self.ctx.timeline_path, current)
        return {
            "ok": True,
            "topic": topic,
            "script_path": str(script_path),
            "voice_path": str(Path(voice_path).resolve()),
            "srt_path": str(Path(srt_path).resolve()),
            "script_text": script_text,
            "timeline_seconds": float(timeline_seconds),
        }

    def render(self):
        data = load_timeline(self.ctx.timeline_path)
        segments = data.get("segments", [])
        if not segments:
            return Response("Timeline vacío: añade clips antes de renderizar", status=400)
        if bool(data.get("audio_dirty", False)):
            return Response("El audio está desactualizado: genera audio+subtítulos otra vez", status=400)
        if not data.get("voice_path") or not Path(data["voice_path"]).exists():
            return Response("Falta audio", status=400)
        if not data.get("srt_path") or not Path(data["srt_path"]).exists():
            return Response("Faltan subtítulos", status=400)

        build_video(
            clip_paths=[],
            voice_path=Path(data["voice_path"]),
            srt_path=Path(data["srt_path"]),
            out_path=Path(data["out_path"]),
            target_minutes=float(data.get("target_minutes", 10)),
            max_clip_segment_seconds=float(data.get("max_clip_segment_seconds", 6.0)),
            timeline_segments=segments,
            subtitle_style=data.get("subtitle_style", {}),
            overlays=data.get("overlays", []),
        )
        return {"ok": True, "out_path": data["out_path"]}

    def safe_generate_script(self, payload: dict):
        return self._run_guarded(self.generate_script_only, payload, "Script generation failed")

    def safe_generate_audio(self, payload: dict):
        return self._run_guarded(self.generate_audio_only, payload, "Audio generation failed")

    def safe_generate_subtitles(self, payload: dict):
        return self._run_guarded(self.generate_subtitles_only, payload, "Subtitles generation failed")

    def safe_generate_project(self, payload: dict):
        return self._run_guarded(self.generate_audio_bundle, payload, "Project generation failed")

    def _segment_to_editor_clip(self, seg: dict) -> dict:
        return {
            "id": seg.get("id") or str(uuid.uuid4()),
            "name": seg.get("name") or Path(str(seg.get("clip_path", ""))).name,
            "path": str(seg.get("clip_path", "")),
            "start": float(seg.get("start", 0.0)),
            "duration": float(seg.get("duration", 4.0)),
            "enabled": bool(seg.get("enabled", True)),
        }

    def _clean_segments(self, segments: list[dict]) -> list[dict]:
        return [
            {
                "id": seg.get("id") or str(uuid.uuid4()),
                "name": seg.get("name") or Path(str(seg.get("clip_path", ""))).name,
                "clip_path": str(seg.get("clip_path", "")),
                "start": max(0.0, float(seg.get("start", 0.0))),
                "duration": max(1.0, float(seg.get("duration", 4.0))),
                "enabled": bool(seg.get("enabled", True)),
            }
            for seg in segments
        ]

    def _normalize_payload_clips(self, clips: list[dict]) -> list[dict]:
        normalized = []
        for clip in clips:
            item = self.normalize_editor_clip(clip)
            if item is not None:
                normalized.append(item)
        return normalized

    def _apply_dirty_flag(self, data: dict, old_segments: list[dict], cleaned_clips: list[dict]) -> None:
        if clip_signature(old_segments) != clip_signature(cleaned_clips):
            data["audio_dirty"] = True

    def _apply_editor_metadata(self, data: dict, payload: dict) -> None:
        if "script_text" in payload:
            data["script_text"] = str(payload.get("script_text", "") or "")
        if "library" in payload:
            data["library"] = payload.get("library", []) or []
        if "overlays" in payload:
            data["overlays"] = payload.get("overlays", []) or []
        if "subtitle_style" in payload:
            data["subtitle_style"] = payload.get("subtitle_style", {}) or {}

    def _resolve_topic(self, payload: dict, current: dict) -> str:
        topic = str(payload.get("topic", current.get("topic", ""))).strip()
        if not topic:
            raise ValueError(TOPIC_REQUIRED)
        return topic

    def _resolve_script_text(self, payload: dict, current: dict) -> str:
        return str(payload.get("script_text", "")).strip() or str(current.get("script_text", "")).strip() or self.read_script_text().strip()

    def _generate_script(self, topic: str, minutes: float, provider: str) -> str:
        return generate_script(
            topic=topic,
            target_minutes=max(1, int(round(minutes))),
            ollama_base_url=self.ctx.settings.OLLAMA_BASE_URL,
            ollama_model=self.ctx.settings.OLLAMA_MODEL,
            openai_api_key=self.ctx.settings.OPENAI_API_KEY,
            openai_model=self.ctx.settings.OPENAI_MODEL,
            provider=provider,
        )

    def _create_elevenlabs_voice(self, text: str) -> Path:
        if not self.ctx.settings.ELEVENLABS_API_KEY or not self.ctx.settings.ELEVENLABS_VOICE_ID:
            raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID missing in .env")
        voice_path = self.ctx.out_dir / VOICE_MP3
        tts_to_mp3_elevenlabs(
            text=text,
            out_path=voice_path,
            api_key=self.ctx.settings.ELEVENLABS_API_KEY,
            voice_id=self.ctx.settings.ELEVENLABS_VOICE_ID,
            model_id=self.ctx.settings.ELEVENLABS_MODEL,
        )
        return voice_path

    def _create_local_voice(self, text: str, voice: str) -> Path:
        lang = (voice or "en").split("-")[0].split("_")[0].lower() or "en"
        voice_path = self.ctx.out_dir / "voice.wav"
        tts_to_wav_local(text=text, out_path=voice_path, lang=lang)
        return voice_path

    def _edge_voice(self, text: str, voice: str, speech_rate: str) -> Optional[Path]:
        voice_path = self.ctx.out_dir / VOICE_MP3
        try:
            tts_to_mp3_edge(text=text, out_path=voice_path, voice=voice or "en-US-EmmaNeural", rate=speech_rate or "+0%")
            return voice_path
        except Exception:
            return None

    def _create_gtts_voice(self, text: str, voice: str) -> Path:
        lang = (voice or "en").split("-")[0].split("_")[0].lower() or "en"
        voice_path = self.ctx.out_dir / VOICE_MP3
        tts_to_mp3_gtts(text=text, out_path=voice_path, lang=lang)
        return voice_path

    def _run_guarded(self, fn, payload: dict, prefix: str):
        try:
            return fn(payload), None
        except ValueError as exc:
            return None, Response(str(exc), status=400)
        except Exception as exc:
            traceback.print_exc()
            return None, Response(f"{prefix}: {exc}", status=500)

import argparse
import uuid
from pathlib import Path

from src.config import Settings
from src.script_gen import generate_script
from src.tts_local import tts_to_wav_local
from src.tts_edge import tts_to_mp3_edge
from src.tts_gtts import tts_to_mp3_gtts
from src.tts_elevenlabs import tts_to_mp3_elevenlabs
from src.clips_pexels import download_clips_for_topic
from src.subtitles import whisper_to_srt
from src.video_edit import build_video
from src.timeline import create_timeline_manifest, load_timeline, save_timeline
from src.editor_web import run_editor
from src.utils import probe_duration_seconds

def _empty_timeline(out_final: Path) -> dict:
    return {
        "topic": "",
        "target_minutes": 8.0,
        "desired_seconds": 0.0,
        "voice_path": "",
        "srt_path": "",
        "out_path": str(out_final.resolve()),
        "max_clip_segment_seconds": 6.0,
        "subtitle_style": {
            "font_family": "Arial",
            "font_file": "",
            "font_size": 18,
            "primary_color": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 2,
        },
        "audio_dirty": False,
        "overlays": [],
        "library": [],
        "segments": [],
    }


def _load_or_bootstrap_timeline(root: Path, timeline_path: Path, topic: str, minutes: float) -> dict:
    out_dir = root / "output"
    clips_dir = root / "work" / "clips"
    out_final = out_dir / "final.mp4"

    if timeline_path.exists():
        try:
            data = load_timeline(timeline_path)
        except Exception:
            data = _empty_timeline(out_final)
    else:
        data = _empty_timeline(out_final)

    changed = False

    if not str(data.get("out_path", "")).strip():
        data["out_path"] = str(out_final.resolve())
        changed = True

    if topic and not str(data.get("topic", "")).strip():
        data["topic"] = topic
        changed = True

    if not data.get("target_minutes"):
        data["target_minutes"] = float(minutes)
        changed = True

    voice_candidates = [out_dir / "voice.mp3", out_dir / "voice.wav"]
    if not str(data.get("voice_path", "")).strip():
        for candidate in voice_candidates:
            if candidate.exists():
                data["voice_path"] = str(candidate.resolve())
                changed = True
                break

    srt_candidate = out_dir / "subtitles.srt"
    if not str(data.get("srt_path", "")).strip() and srt_candidate.exists():
        data["srt_path"] = str(srt_candidate.resolve())
        changed = True

    script_candidate = out_dir / "script.txt"
    if not str(data.get("script_text", "")).strip() and script_candidate.exists():
        try:
            data["script_text"] = script_candidate.read_text(encoding="utf-8")
            changed = True
        except Exception:
            pass

    if not data.get("library"):
        clip_paths = sorted(clips_dir.glob("*.mp4"))
        library = []
        for clip_path in clip_paths:
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
        if library:
            data["library"] = library
            changed = True

    def _looks_autofilled_from_library(tl: dict) -> bool:
        """Detecta un timeline autogenerado (batch) que repite toda la biblioteca.

        Heurística segura para evitar que el editor arranque con 100+ clips
        cuando el usuario solo quiere editar desde cero.
        """
        segments = tl.get("segments") or []
        library = tl.get("library") or []
        if not isinstance(segments, list) or not isinstance(library, list):
            return False
        if len(library) < 2 or len(segments) <= len(library):
            return False

        lib_dur_by_path = {}
        for item in library:
            if not isinstance(item, dict):
                continue
            p = str(item.get("path", ""))
            try:
                lib_dur_by_path[p] = float(item.get("duration", 0.0) or 0.0)
            except Exception:
                lib_dur_by_path[p] = 0.0

        unique_paths = set()
        for seg in segments:
            if not isinstance(seg, dict):
                return False
            p = str(seg.get("clip_path", ""))
            if not p:
                return False
            unique_paths.add(p)
            try:
                if abs(float(seg.get("start", 0.0) or 0.0)) > 1e-6:
                    return False
            except Exception:
                return False

            # Si coincide con la biblioteca, verificamos que sea el clip completo.
            if p in lib_dur_by_path and lib_dur_by_path[p] > 0:
                try:
                    seg_d = float(seg.get("duration", 0.0) or 0.0)
                except Exception:
                    return False
                if abs(seg_d - lib_dur_by_path[p]) > 0.15:
                    return False

        return len(unique_paths) <= max(1, len(library))

    # En modo UI, si el timeline parece autogenerado y nunca fue tocado desde la UI,
    # arrancar vacío (sin borrar la biblioteca).
    if not bool(data.get("editor_touched", False)) and _looks_autofilled_from_library(data):
        data["segments"] = []
        data["desired_seconds"] = 0.0
        data["audio_dirty"] = True
        changed = True

    if changed:
        save_timeline(timeline_path, data)

    return data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", nargs="*", default=[])  # <- antes tenía un topic por defecto
    parser.add_argument("--minutes", type=float, default=10.0, help="Target video length in minutes")
    parser.add_argument("--voice", type=str, default="en-US-EmmaNeural", help="Voice id for edge/elevenlabs or language hint for gtts/local")
    parser.add_argument("--tts-provider", choices=["gtts", "edge", "elevenlabs", "local"], default="gtts")
    parser.add_argument("--script-provider", choices=["auto", "gpt", "ollama"], default="auto")
    parser.add_argument("--speech-rate", type=str, default="+0%", help="Edge-TTS rate. Example: -10% or +5%")
    parser.add_argument("--clips", type=int, default=18, help="How many stock clips to download")
    parser.add_argument("--edit-ui", action="store_true", help="(legacy) no longer required")
    parser.add_argument("--ui-port", type=int, default=8765, help="Port for web editor")
    parser.add_argument("--batch", action="store_true", help="Run full automatic pipeline (old behavior)")
    args = parser.parse_args()

    topic = " ".join(args.topic).strip()
    settings = Settings.load()

    root = Path(__file__).parent
    work = root / "work"
    out = root / "output"
    (work / "clips").mkdir(parents=True, exist_ok=True)
    (work / "audio").mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    timeline_path = work / "timeline.json"

    # MODO NUEVO POR DEFECTO: abrir editor web preservando o recuperando timeline existente
    if not args.batch:
        _load_or_bootstrap_timeline(
            root=root,
            timeline_path=timeline_path,
            topic=topic,
            minutes=float(args.minutes),
        )
        run_editor(workspace_root=root, timeline_path=timeline_path, port=args.ui_port)
        return

    print(f"\n[1/5] Generating script for: {topic}")
    script_text = generate_script(
        topic=topic,
        target_minutes=args.minutes,
        ollama_base_url=settings.OLLAMA_BASE_URL,
        ollama_model=settings.OLLAMA_MODEL,
        openai_api_key=settings.OPENAI_API_KEY,
        openai_model=settings.OPENAI_MODEL,
        provider=args.script_provider,
    )
    script_path = out / "script.txt"
    script_path.write_text(script_text, encoding="utf-8")
    print(f"Saved script: {script_path}")

    print(f"\n[2/5] Generating voiceover ({args.tts_provider})")
    if args.tts_provider == "elevenlabs":
        if not settings.ELEVENLABS_API_KEY or not settings.ELEVENLABS_VOICE_ID:
            raise RuntimeError("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID missing in .env")
        voice_path = out / "voice.mp3"
        tts_to_mp3_elevenlabs(
            text=script_text,
            out_path=voice_path,
            api_key=settings.ELEVENLABS_API_KEY,
            voice_id=settings.ELEVENLABS_VOICE_ID,
            model_id=settings.ELEVENLABS_MODEL,
        )
    elif args.tts_provider == "local":
        voice_path = out / "voice.wav"
        tts_to_wav_local(
            text=script_text,
            out_path=voice_path,
            lang=args.voice,
        )
    elif args.tts_provider == "gtts":
        voice_path = out / "voice.mp3"
        lang_hint = (args.voice or "en").split("-")[0].split("_")[0].lower() or "en"
        try:
            tts_to_mp3_gtts(
                text=script_text,
                out_path=voice_path,
                lang=lang_hint,
            )
        except Exception:
            print("gTTS failed, falling back to local TTS")
            voice_path = out / "voice.wav"
            tts_to_wav_local(
                text=script_text,
                out_path=voice_path,
                lang=lang_hint,
            )
    else:
        voice_path = out / "voice.mp3"
        try:
            tts_to_mp3_edge(
                text=script_text,
                out_path=voice_path,
                voice=args.voice,
                rate=args.speech_rate,
            )
        except Exception:
            print("Edge-TTS failed, falling back to gTTS")
            lang_hint = (args.voice or "en").split("-")[0].split("_")[0].lower() or "en"
            voice_path = out / "voice.mp3"
            try:
                tts_to_mp3_gtts(
                    text=script_text,
                    out_path=voice_path,
                    lang=lang_hint,
                )
            except Exception:
                print("gTTS failed, falling back to local TTS")
                voice_path = out / "voice.wav"
                tts_to_wav_local(
                    text=script_text,
                    out_path=voice_path,
                    lang=lang_hint,
                )
    print(f"Saved voice: {voice_path}")

    print("\n[3/5] Downloading clips from Pexels")
    clip_paths = download_clips_for_topic(
        topic=topic,
        api_key=settings.PEXELS_API_KEY,
        out_dir=(work / "clips"),
        max_clips=args.clips,
    )
    print(f"Downloaded {len(clip_paths)} clips")

    print("\n[4/5] Generating subtitles (Whisper local)")
    srt_path = out / "subtitles.srt"
    whisper_to_srt(audio_path=voice_path, srt_path=srt_path)
    print(f"Saved subtitles: {srt_path}")

    timeline_path = work / "timeline.json"
    create_timeline_manifest(
        clip_paths=clip_paths,
        topic=topic,
        target_minutes=args.minutes,
        voice_path=voice_path,
        srt_path=srt_path,
        out_path=(out / "final.mp4"),
        timeline_path=timeline_path,
    )
    print(f"Saved timeline: {timeline_path}")

    if args.edit_ui:
        print("\n[5/5] Launching timeline editor")
        run_editor(workspace_root=root, timeline_path=timeline_path, port=args.ui_port)
        return

    print("\n[5/5] Building final video (FFmpeg)")
    final_path = out / "final.mp4"
    build_video(
        clip_paths=clip_paths,
        voice_path=voice_path,
        srt_path=srt_path,
        out_path=final_path,
        target_minutes=args.minutes,
    )
    print(f"\nDONE ✅ Video exported: {final_path}\n")

if __name__ == "__main__":
    main()
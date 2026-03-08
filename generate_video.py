import argparse
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
        "overlays": [],
        "library": [],
        "segments": [],
    }

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

    # MODO NUEVO POR DEFECTO: siempre abrir editor web, sin autoproceso
    if not args.batch:
        data = _empty_timeline(out / "final.mp4")
        if topic:
            data["topic"] = topic
        data["target_minutes"] = float(args.minutes)
        save_timeline(timeline_path, data)
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
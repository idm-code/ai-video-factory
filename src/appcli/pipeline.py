from dataclasses import dataclass
from pathlib import Path

from ..clips_pexels import download_clips_for_topic
from ..config import Settings
from ..editor_web import run_editor
from ..script_gen import generate_script
from ..subtitles import whisper_to_srt
from ..timeline import create_timeline_manifest
from ..tts_gtts import tts_to_mp3_gtts
from ..video_edit import build_video
from .bootstrap import bootstrap_timeline

VOICE_MP3 = "voice.mp3"


@dataclass
class CliArgs:
    topic: list
    minutes: float
    voice: str
    script_provider: str
    clips: int
    ui_port: int
    batch: bool


@dataclass
class CliPaths:
    root: Path
    work: Path
    out: Path
    timeline_path: Path


def ensure_workspace(root: Path) -> CliPaths:
    work = root / "work"
    out = root / "output"
    (work / "clips").mkdir(parents=True, exist_ok=True)
    (work / "audio").mkdir(parents=True, exist_ok=True)
    (work / "tmp").mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    return CliPaths(root=root, work=work, out=out, timeline_path=work / "timeline.json")


def run_ui_mode(paths: CliPaths, topic: str, minutes: float, port: int) -> None:
    bootstrap_timeline(root=paths.root, timeline_path=paths.timeline_path, topic=topic, minutes=minutes)
    run_editor(workspace_root=paths.root, timeline_path=paths.timeline_path, port=port)


def create_voiceover(out_dir: Path, script_text: str, voice: str) -> Path:
    lang = (voice or "en").split("-")[0].split("_")[0].lower() or "en"
    voice_path = out_dir / VOICE_MP3
    tts_to_mp3_gtts(text=script_text, out_path=voice_path, lang=lang)
    return voice_path


def run_batch_mode(args: CliArgs, settings: Settings, paths: CliPaths, topic: str) -> None:
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
    script_path = paths.out / "script.txt"
    script_path.write_text(script_text, encoding="utf-8")
    print(f"Saved script: {script_path}")

    print("\n[2/5] Generating voiceover (gtts)")
    voice_path = create_voiceover(out_dir=paths.out, script_text=script_text, voice=args.voice)
    print(f"Saved voice: {voice_path}")

    print("\n[3/5] Downloading clips from Pexels")
    clip_paths = download_clips_for_topic(
        topic=topic,
        api_key=settings.PEXELS_API_KEY,
        out_dir=(paths.work / "clips"),
        max_clips=args.clips,
    )
    print(f"Downloaded {len(clip_paths)} clips")

    print("\n[4/5] Generating subtitles (Whisper local)")
    srt_path = paths.out / "subtitles.srt"
    whisper_to_srt(audio_path=voice_path, srt_path=srt_path)
    print(f"Saved subtitles: {srt_path}")

    create_timeline_manifest(
        clip_paths=clip_paths,
        topic=topic,
        target_minutes=args.minutes,
        voice_path=voice_path,
        srt_path=srt_path,
        out_path=(paths.out / "final.mp4"),
        timeline_path=paths.timeline_path,
    )
    print(f"Saved timeline: {paths.timeline_path}")

    print("\n[5/5] Building final video (FFmpeg)")
    final_path = paths.out / "final.mp4"
    build_video(
        clip_paths=clip_paths,
        voice_path=voice_path,
        srt_path=srt_path,
        out_path=final_path,
        target_minutes=args.minutes,
    )
    print(f"\nDONE ✅ Video exported: {final_path}\n")


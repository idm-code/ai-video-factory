import argparse
from pathlib import Path

from ..config import Settings
from .pipeline import CliArgs, ensure_workspace, run_batch_mode, run_ui_mode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", nargs="*", default=[])
    parser.add_argument("--minutes", type=float, default=10.0, help="Target video length in minutes")
    parser.add_argument("--voice", type=str, default="en", help="Language hint for gTTS, for example: en, es, fr")
    parser.add_argument("--script-provider", choices=["auto", "gpt", "ollama"], default="auto")
    parser.add_argument("--clips", type=int, default=18, help="How many stock clips to download")
    parser.add_argument("--ui-port", type=int, default=8765, help="Port for React editor")
    parser.add_argument("--batch", action="store_true", help="Run full automatic pipeline")
    return parser


def parse_args() -> CliArgs:
    parsed = build_parser().parse_args()
    return CliArgs(
        topic=parsed.topic,
        minutes=parsed.minutes,
        voice=parsed.voice,
        script_provider=parsed.script_provider,
        clips=parsed.clips,
        ui_port=parsed.ui_port,
        batch=parsed.batch,
    )


def main() -> None:
    args = parse_args()
    topic = " ".join(args.topic).strip()
    settings = Settings.load()
    paths = ensure_workspace(Path(__file__).resolve().parents[2])

    if args.batch:
        run_batch_mode(args=args, settings=settings, paths=paths, topic=topic)
        return

    run_ui_mode(paths=paths, topic=topic, minutes=float(args.minutes), port=args.ui_port)

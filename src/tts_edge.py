import asyncio
import datetime
from pathlib import Path

import edge_tts


# Python 3.9 compatibility for edge-tts expecting datetime.UTC
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc


def tts_to_mp3_edge(text: str, out_path: Path, voice: str = "en-US-EmmaNeural", rate: str = "+0%") -> Path:
    """Generate TTS audio using Microsoft Edge voices (free, cloud-based)."""
    out_path = Path(out_path)

    async def _run() -> None:
        communicator = edge_tts.Communicate(text=text, voice=voice, rate=rate)
        await communicator.save(str(out_path))

    asyncio.run(_run())
    return out_path

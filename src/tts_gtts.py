import subprocess
from pathlib import Path

from gtts import gTTS


def _build_atempo_filter(speed: float) -> str:
    """Build a chained atempo filter string.

    ffmpeg's atempo accepts values in [0.5, 2.0] per filter application,
    so speeds outside that range are achieved by chaining multiple filters.
    """
    filters = []
    remaining = speed
    if speed > 1.0:
        while remaining > 2.0 + 1e-9:
            filters.append("atempo=2.0")
            remaining /= 2.0
        filters.append(f"atempo={remaining:.6f}")
    else:
        while remaining < 0.5 - 1e-9:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.6f}")
    return ",".join(filters)


def tts_to_mp3_gtts(text: str, out_path: Path, lang: str = "en", speed: float = 1.0) -> Path:
    """Generate TTS audio.

    Args:
        text: Text to synthesize.
        out_path: Destination MP3 path.
        lang: Language code (e.g. "en", "es").
        speed: Playback speed multiplier (e.g. 1.0 = normal, 1.5 = 50% faster).
               Supported range: 0.25 – 4.0.
    """
    out_path = Path(out_path)
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(out_path))
    if abs(speed - 1.0) > 0.01:
        sped_path = out_path.parent / (out_path.stem + "_sped" + out_path.suffix)
        af = _build_atempo_filter(speed)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_path), "-filter:a", af, str(sped_path)],
            check=True,
        )
        sped_path.replace(out_path)
    return out_path

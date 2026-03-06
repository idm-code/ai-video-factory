from pathlib import Path

from gtts import gTTS


def tts_to_mp3_gtts(text: str, out_path: Path, lang: str = "en") -> Path:
    out_path = Path(out_path)
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(out_path))
    return out_path

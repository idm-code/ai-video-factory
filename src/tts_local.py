from pathlib import Path

import pyttsx3


def tts_to_wav_local(text: str, out_path: Path, lang: str = "en") -> None:
    """Generate a WAV file with local/offline TTS using pyttsx3.

    This avoids external paid APIs like ElevenLabs and heavy
    native dependencies like Coqui TTS. It uses the system
    voices available on the host (on Windows, SAPI5).
    """

    out_path = Path(out_path)

    engine = pyttsx3.init()

    # Try to pick a voice that roughly matches the language if possible.
    try:
        if lang:
            voices = engine.getProperty("voices") or []
            selected = None
            for v in voices:
                # v.languages can be bytes on some platforms
                langs = []
                for l in getattr(v, "languages", []):
                    try:
                        langs.append(l.decode("utf-8") if isinstance(l, (bytes, bytearray)) else str(l))
                    except Exception:
                        continue
                if any(lang.lower() in l.lower() for l in langs) or lang.lower() in (v.id or "").lower():
                    selected = v.id
                    break

            if selected:
                engine.setProperty("voice", selected)
    except Exception:
        # Fallback to default voice if anything goes wrong selecting voice
        pass

    engine.save_to_file(text, str(out_path))
    engine.runAndWait()
    engine.stop()

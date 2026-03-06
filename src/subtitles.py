from pathlib import Path
from faster_whisper import WhisperModel

def whisper_to_srt(audio_path: Path, srt_path: Path) -> None:
    audio_path = Path(audio_path)
    srt_path = Path(srt_path)

    model = WhisperModel("small", device="cpu", compute_type="int8")  # change to "cuda" if you have NVIDIA
    segments, _ = model.transcribe(str(audio_path), vad_filter=True)

    def fmt_time(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = int(t % 60)
        ms = int((t - int(t)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    idx = 1
    for seg in segments:
        start = fmt_time(seg.start)
        end = fmt_time(seg.end)
        text = seg.text.strip()
        if not text:
            continue
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        idx += 1

    srt_path.write_text("\n".join(lines), encoding="utf-8")
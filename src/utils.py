import subprocess
from pathlib import Path

def probe_duration_seconds(path: Path) -> float:
    path = Path(path)
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    out = subprocess.check_output(cmd).decode().strip()
    try:
        return float(out)
    except:
        return 0.0
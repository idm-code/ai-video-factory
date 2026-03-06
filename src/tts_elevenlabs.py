import requests
from pathlib import Path

def tts_to_mp3_elevenlabs(text: str, out_path: Path, api_key: str, voice_id: str, model_id: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }

    r = requests.post(url, headers=headers, json=payload)

    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs error: {r.text}")

    with open(out_path, "wb") as f:
        f.write(r.content)

    return out_path
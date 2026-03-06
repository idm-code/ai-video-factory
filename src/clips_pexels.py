import random
import requests
import re
from pathlib import Path
from tqdm import tqdm


def _topic_keywords(topic: str):
    base_words = [w.strip().lower() for w in topic.split() if w.strip()]
    variants = [
        topic,
        " ".join(base_words[:3]) if base_words else topic,
        "business laptop",
        "creative work desk",
        "team collaboration office",
        "startup planning",
        "typing computer close up",
        "digital design workflow",
        "ecommerce customer",
        "wedding invitation design" if "wedding" in topic.lower() else "online marketplace",
    ]
    return [k for k in variants if k]


_BAD_VISUAL_TERMS = {
    "thanks for watching", "subscribe", "end screen", "outro", "intro",
    "template", "lower third", "countdown", "green screen", "overlay",
    "wallpaper", "loop background", "promo", "youtube intro", "youtube outro"
}

def _is_relevant_video(video: dict, topic: str) -> bool:
    text_parts = [
        video.get("url", ""),
        str(video.get("id", "")),
        (video.get("user") or {}).get("name", ""),
    ]
    haystack = " ".join(text_parts).lower()

    # descartar assets típicos de plantillas/outros
    if any(t in haystack for t in _BAD_VISUAL_TERMS):
        return False

    # exigir archivo horizontal y resolución mínima
    files = video.get("video_files") or []
    ok_landscape = any((f.get("width", 0) >= 1280 and f.get("width", 0) >= f.get("height", 0)) for f in files)
    if not ok_landscape:
        return False

    # evitar resultados demasiado genéricos de motion graphics
    if re.search(r"\b(motion graphics|abstract background|neon loop)\b", haystack):
        return False

    return True

def download_clips_for_topic(topic: str, api_key: str, out_dir: Path, max_clips: int = 18):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not api_key:
        raise RuntimeError("PEXELS_API_KEY is empty. Put it in .env")

    keywords = _topic_keywords(topic)

    headers = {"Authorization": api_key}
    collected = []
    seen_video_ids = set()

    for kw in keywords:
        if len(collected) >= max_clips:
            break
        url = "https://api.pexels.com/videos/search"
        params = {
            "query": kw,
            "per_page": 20,
            "orientation": "landscape",
            "size": "medium",
        }
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        filtered = [v for v in videos if _is_relevant_video(v, topic)]
        if filtered:
            videos = filtered
        random.shuffle(videos)

        for v in videos:
            if len(collected) >= max_clips:
                break
            vid = v.get("id")
            if vid in seen_video_ids:
                continue
            duration = float(v.get("duration", 0) or 0)
            if duration < 4 or duration > 30:
                continue
            files = v.get("video_files", [])
            files = [
                f
                for f in files
                if f.get("file_type") == "video/mp4"
                and f.get("width", 0) >= 1280
                and f.get("height", 0) >= 720
            ]
            if not files:
                continue
            best = sorted(
                files,
                key=lambda x: (x.get("width", 0) * x.get("height", 0), -(x.get("fps", 30) or 30)),
                reverse=True,
            )[0]
            link = best.get("link")
            if not link:
                continue
            collected.append(link)
            seen_video_ids.add(vid)

    clip_paths = []
    for i, link in enumerate(tqdm(collected[:max_clips], desc="Downloading clips")):
        out_path = out_dir / f"clip_{i:03d}.mp4"
        if out_path.exists() and out_path.stat().st_size > 1024:
            clip_paths.append(out_path)
            continue
        with requests.get(link, stream=True, timeout=60) as rr:
            rr.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in rr.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        clip_paths.append(out_path)

    return clip_paths
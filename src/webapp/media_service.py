import traceback
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Response, jsonify, send_from_directory

from ..timeline import load_timeline, save_timeline
from .common import actual_media_duration, is_inside
from .context import EditorContext


class MediaService:
    VALID_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png"}

    def __init__(self, ctx: EditorContext):
        self.ctx = ctx

    def search_pexels(
        self,
        query: str,
        media_type: str,
        per_page: int = 24,
        page: int = 1,
        orientation: str = "any",
        min_duration: float = 0.0,
        max_duration: float = 0.0,
    ) -> dict:
        if not self.ctx.settings.PEXELS_API_KEY:
            return {"items": [], "has_more": False}
        if media_type == "image":
            return self._search_pexels_images(query, per_page, page, orientation)
        return self._search_pexels_videos(query, per_page, page, orientation, min_duration, max_duration)

    def search_pixabay(
        self,
        query: str,
        media_type: str,
        per_page: int = 24,
        page: int = 1,
        orientation: str = "any",
        min_duration: float = 0.0,
        max_duration: float = 0.0,
    ) -> dict:
        if not self.ctx.settings.PIXABAY_API_KEY:
            return {"items": [], "has_more": False}
        if media_type == "image":
            return self._search_pixabay_images(query, per_page, page, orientation)
        return self._search_pixabay_videos(query, per_page, page, orientation, min_duration, max_duration)

    def import_media(self, item: dict, add_to_timeline: bool, image_seconds: float):
        media_type = str(item.get("media_type", "video")).lower().strip()
        source_url = self._resolve_source_url(item)
        if not source_url:
            return Response(f"missing source URL. Keys: {list(item.keys())}", status=400)

        clip_path = self._download_media(source_url, media_type, item)
        clip_duration = self._resolve_clip_duration(media_type, image_seconds, item, clip_path)
        data = load_timeline(self.ctx.timeline_path)
        created_clip = None
        if add_to_timeline:
            created_clip = self._append_clip_to_timeline(data, clip_path, clip_duration)
            save_timeline(self.ctx.timeline_path, data)

        return jsonify(
            {
                "ok": True,
                "path": str(clip_path),
                "clip": {
                    "id": created_clip["id"],
                    "name": created_clip["name"],
                    "path": created_clip["clip_path"],
                    "start": created_clip["start"],
                    "duration": created_clip["duration"],
                    "enabled": created_clip["enabled"],
                } if created_clip else None,
            }
        )

    def import_media_from_request(self, payload: dict):
        try:
            payload = payload or {}
            item = payload.get("item") or {}
            add_to_timeline = bool(payload.get("add_to_timeline", False))
            image_seconds = max(1.0, float(payload.get("image_seconds", 6)))
            return self.import_media(item=item, add_to_timeline=add_to_timeline, image_seconds=image_seconds)
        except requests.RequestException as exc:
            traceback.print_exc()
            return Response(f"download failed: {exc}", status=502)
        except Exception as exc:
            traceback.print_exc()
            return Response(f"media import failed: {type(exc).__name__}: {exc}", status=500)

    def send_clip(self, raw_path: str):
        clip = Path(raw_path).resolve()
        if not is_inside(self.ctx.workspace_root, clip) or not clip.exists():
            return Response("Clip not found", status=404)
        return send_from_directory(clip.parent, clip.name)

    def _search_pexels_images(self, query: str, per_page: int, page: int, orientation: str) -> dict:
        headers = {"Authorization": self.ctx.settings.PEXELS_API_KEY}
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": query, "per_page": per_page, "page": page, "orientation": self._pexels_orientation(orientation)},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        items = [self._pexels_image_payload(photo) for photo in payload.get("photos", [])]
        return {"items": items, "has_more": self._has_more(payload.get("total_results", 0), page, per_page, len(items))}

    def _search_pexels_videos(self, query: str, per_page: int, page: int, orientation: str, min_duration: float, max_duration: float) -> dict:
        headers = {"Authorization": self.ctx.settings.PEXELS_API_KEY}
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": per_page, "page": page, "orientation": self._pexels_orientation(orientation)},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        items = []
        for video in payload.get("videos", []):
            duration_val = float(video.get("duration", 0.0) or 0.0)
            if not self._duration_allowed(duration_val, min_duration, max_duration):
                continue
            item = self._pexels_video_payload(video, duration_val)
            if item is not None:
                items.append(item)
        return {"items": items, "has_more": self._has_more(payload.get("total_results", 0), page, per_page, len(items))}

    def _search_pixabay_images(self, query: str, per_page: int, page: int, orientation: str) -> dict:
        params = {
            "key": self.ctx.settings.PIXABAY_API_KEY,
            "q": query,
            "image_type": "photo",
            "per_page": min(per_page, 200),
            "page": page,
            "safesearch": "true",
        }
        pixabay_orientation = self._pixabay_orientation(orientation)
        if pixabay_orientation in ("horizontal", "vertical"):
            params["orientation"] = pixabay_orientation

        response = requests.get("https://pixabay.com/api/", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        items = []
        for item in payload.get("hits", []):
            width_val = int(item.get("imageWidth", 0) or 0)
            height_val = int(item.get("imageHeight", 0) or 0)
            if not self._matches_orientation(orientation, width_val, height_val):
                continue
            items.append(
                {
                    "provider": "pixabay",
                    "media_type": "image",
                    "id": str(item.get("id")),
                    "thumb_url": item.get("previewURL", ""),
                    "preview_url": item.get("webformatURL", ""),
                    "download_url": item.get("largeImageURL") or item.get("webformatURL") or "",
                    "width": width_val,
                    "height": height_val,
                    "duration": 0,
                }
            )
        return {"items": items, "has_more": self._has_more(payload.get("totalHits", 0), page, per_page, len(items))}

    def _search_pixabay_videos(self, query: str, per_page: int, page: int, orientation: str, min_duration: float, max_duration: float) -> dict:
        params = {
            "key": self.ctx.settings.PIXABAY_API_KEY,
            "q": query,
            "video_type": "all",
            "per_page": min(per_page, 200),
            "page": page,
            "safesearch": "true",
        }
        response = requests.get("https://pixabay.com/api/videos/", params=params, timeout=20)
        print(f"[Pixabay video] status={response.status_code} url={response.url}")
        if not response.ok:
            print(f"[Pixabay video] error body: {response.text[:300]}")
            response.raise_for_status()

        payload = response.json()
        print(f"[Pixabay video] totalHits={payload.get('totalHits')} hits={len(payload.get('hits', []))}")
        items = []
        for item in payload.get("hits", []):
            payload_item = self._pixabay_video_payload(item, orientation, min_duration, max_duration)
            if payload_item is not None:
                items.append(payload_item)
        return {"items": items, "has_more": self._has_more(payload.get("totalHits", 0), page, per_page, len(items))}

    def _pexels_orientation(self, orientation: str) -> str:
        return orientation if orientation in {"landscape", "portrait", "square"} else "landscape"

    def _pixabay_orientation(self, orientation: str) -> str:
        if orientation == "landscape":
            return "horizontal"
        if orientation == "portrait":
            return "vertical"
        return "all"

    def _has_more(self, total_results, page: int, per_page: int, current_count: int) -> bool:
        total_results = int(total_results or 0)
        return (page * per_page) < total_results if total_results > 0 else current_count >= per_page

    def _duration_allowed(self, duration_val: float, min_duration: float, max_duration: float) -> bool:
        if min_duration > 0 and duration_val < min_duration:
            return False
        if max_duration > 0 and duration_val > max_duration:
            return False
        return True

    def _matches_orientation(self, orientation: str, width_val: int, height_val: int) -> bool:
        if width_val <= 0 or height_val <= 0:
            return True
        if orientation == "landscape":
            return width_val >= height_val
        if orientation == "portrait":
            return height_val >= width_val
        if orientation == "square":
            return abs(width_val - height_val) <= max(80, int(0.15 * max(width_val, height_val, 1)))
        return True

    def _pexels_image_payload(self, photo: dict) -> dict:
        src = photo.get("src", {}) or {}
        return {
            "provider": "pexels",
            "media_type": "image",
            "id": str(photo.get("id")),
            "thumb_url": src.get("medium") or src.get("small") or "",
            "preview_url": src.get("large") or src.get("medium") or "",
            "download_url": src.get("original") or src.get("large") or src.get("medium") or "",
            "width": int(photo.get("width", 0) or 0),
            "height": int(photo.get("height", 0) or 0),
        }

    def _pexels_video_payload(self, video: dict, duration_val: float):
        files = [item for item in (video.get("video_files") or []) if item.get("file_type") == "video/mp4"]
        if not files:
            return None
        best = sorted(files, key=lambda item: (item.get("width", 0) * item.get("height", 0)), reverse=True)[0]
        return {
            "provider": "pexels",
            "media_type": "video",
            "id": str(video.get("id")),
            "thumb_url": video.get("image", ""),
            "preview_url": best.get("link", ""),
            "download_url": best.get("link", ""),
            "width": int(best.get("width", 0) or 0),
            "height": int(best.get("height", 0) or 0),
            "duration": duration_val,
        }

    def _pixabay_video_payload(self, item: dict, orientation: str, min_duration: float, max_duration: float):
        videos = item.get("videos", {}) or {}
        chosen = videos.get("large") or videos.get("medium") or videos.get("small") or videos.get("tiny") or {}
        download_url = chosen.get("url", "")
        if not download_url:
            return None

        width_val = int(chosen.get("width", 0) or 0)
        height_val = int(chosen.get("height", 0) or 0)
        if not self._matches_orientation(orientation, width_val, height_val):
            return None

        duration_val = float(item.get("duration", 0.0) or 0.0)
        if not self._duration_allowed(duration_val, min_duration, max_duration):
            return None

        thumb = videos.get("tiny", {}).get("thumbnail", "") or item.get("userImageURL", "") or item.get("picture_id", "")
        return {
            "provider": "pixabay",
            "media_type": "video",
            "id": str(item.get("id")),
            "thumb_url": thumb,
            "preview_url": download_url,
            "download_url": download_url,
            "width": width_val,
            "height": height_val,
            "duration": duration_val,
        }

    def _resolve_source_url(self, item: dict) -> str:
        return item.get("download_url") or item.get("source_url") or item.get("video_url") or item.get("image_url") or item.get("url") or ""

    def _download_media(self, source_url: str, media_type: str, item: dict) -> Path:
        parsed = urlparse(str(source_url))
        ext = Path(parsed.path).suffix.lower()
        if ext not in self.VALID_EXTENSIONS:
            ext = ".mp4" if media_type == "video" else ".jpg"
        base_id = str(item.get("id") or uuid.uuid4())
        safe_id = "".join(ch for ch in base_id if ch.isalnum() or ch in "-_")[:60]
        clip_path = (self.ctx.clips_dir / f"clip_{safe_id}{ext}").resolve()

        if not clip_path.exists() or clip_path.stat().st_size < 1024:
            response = requests.get(str(source_url), timeout=90, stream=True, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            with open(clip_path, "wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)

        if clip_path.stat().st_size < 1024:
            clip_path.unlink(missing_ok=True)
            raise RuntimeError("downloaded file too small")
        return clip_path

    def _resolve_clip_duration(self, media_type: str, image_seconds: float, item: dict, clip_path: Path) -> float:
        if media_type == "image":
            return max(1.0, round(float(image_seconds), 3))
        try:
            fallback_duration = float(item.get("duration") or 0.0)
        except Exception:
            fallback_duration = 0.0
        clip_duration = actual_media_duration(clip_path, fallback_duration)
        if clip_duration <= 0:
            clip_duration = max(1.0, fallback_duration or 4.0)
        return max(1.0, round(float(clip_duration), 3))

    def _append_clip_to_timeline(self, data: dict, clip_path: Path, clip_duration: float) -> dict:
        created_clip = {
            "id": str(uuid.uuid4()),
            "name": clip_path.name,
            "clip_path": str(clip_path),
            "start": 0.0,
            "duration": clip_duration,
            "enabled": True,
        }
        data.setdefault("segments", []).append(created_clip)
        data["clips"] = []
        data["editor_touched"] = True
        data["audio_dirty"] = True
        return created_clip

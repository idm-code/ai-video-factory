import json
from pathlib import Path
from urllib.parse import quote

import requests

from .context import EditorContext


class FontsService:
    def __init__(self, ctx: EditorContext):
        self.ctx = ctx

    def load_index(self) -> dict:
        if not self.ctx.fonts_index_path.exists():
            return {"fonts": []}
        try:
            return json.loads(self.ctx.fonts_index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"fonts": []}

    def save_index(self, data: dict) -> None:
        self.ctx.fonts_index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_local_fonts(self) -> list:
        data = self.load_index()
        return [self._font_payload(Path(item.get("file_path", "")), item.get("family"), item.get("variant", "regular")) for item in data.get("fonts", []) if Path(item.get("file_path", "")).exists()]

    def fetch_google_fonts_catalog(self, limit: int = 120) -> list:
        response = requests.get(
            "https://gwfh.mranftl.com/api/fonts",
            params={"subsets": "latin", "sort": "popularity"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        items = data if isinstance(data, list) else []
        return [
            {
                "id": item.get("id"),
                "family": item.get("family"),
                "category": item.get("category", ""),
                "variants": item.get("variants", []),
            }
            for item in items[: max(1, min(limit, 300))]
        ]

    def install_google_font(self, font_id: str, family: str, variant: str = "regular") -> dict:
        data = self._fetch_font_details(font_id)
        chosen = self._pick_variant(data.get("variants", []) or [], variant)
        ttf_url = self._resolve_ttf_url(chosen)
        safe_family = "".join(ch for ch in (family or font_id) if ch.isalnum() or ch in ("-", "_", " ")).strip().replace(" ", "_")
        safe_variant = "".join(ch for ch in (variant or "regular") if ch.isalnum() or ch in ("-", "_")).strip() or "regular"
        out_path = self.ctx.fonts_dir / f"{safe_family}-{safe_variant}.ttf"
        self._download_font_file(out_path, ttf_url)
        self._add_to_index(font_id=font_id, family=family, variant=safe_variant, out_path=out_path)
        return self._font_payload(out_path, family, safe_variant)

    def _fetch_font_details(self, font_id: str) -> dict:
        response = requests.get(
            f"https://gwfh.mranftl.com/api/fonts/{font_id}",
            params={"subsets": "latin"},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _pick_variant(self, variants, requested_variant: str):
        if isinstance(variants, dict):
            chosen = variants.get(requested_variant) or variants.get("regular")
            if chosen:
                return chosen
            raise RuntimeError("No downloadable variant found for this font")

        if not isinstance(variants, list) or not variants:
            raise RuntimeError("No downloadable variant found for this font")

        requested = str(requested_variant or "regular").lower()
        for candidate in variants:
            if str(candidate.get("id", "")).lower() == requested:
                return candidate
        for candidate in variants:
            if str(candidate.get("id", "")).lower() == "regular":
                return candidate
        return variants[0]

    def _resolve_ttf_url(self, chosen: dict) -> str:
        ttf_url = chosen.get("ttf")
        if ttf_url:
            return ttf_url
        latin = chosen.get("latin", {}) if isinstance(chosen.get("latin"), dict) else {}
        ttf_url = latin.get("ttf")
        if ttf_url:
            return ttf_url
        raise RuntimeError("No TTF URL available for selected font variant")

    def _download_font_file(self, out_path: Path, ttf_url: str) -> None:
        if out_path.exists():
            return
        download = requests.get(ttf_url, timeout=60)
        download.raise_for_status()
        out_path.write_bytes(download.content)

    def _add_to_index(self, font_id: str, family: str, variant: str, out_path: Path) -> None:
        index = self.load_index()
        fonts = index.get("fonts", [])
        existing = next((item for item in fonts if Path(item.get("file_path", "")).name == out_path.name), None)
        if existing is not None:
            return
        fonts.append(
            {
                "family": family,
                "variant": variant,
                "font_id": font_id,
                "file_path": str(out_path.resolve()),
            }
        )
        index["fonts"] = fonts
        self.save_index(index)

    def _font_payload(self, file_path: Path, family: str, variant: str) -> dict:
        return {
            "family": family,
            "variant": variant,
            "file_name": file_path.name,
            "file_path": str(file_path.resolve()),
            "url": f"/fonts/{quote(file_path.name)}",
        }

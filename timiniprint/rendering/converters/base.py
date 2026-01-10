from __future__ import annotations

from dataclasses import dataclass
from typing import List

from PIL import Image, ImageOps


@dataclass(frozen=True)
class Page:
    image: Image.Image
    dither: bool
    is_text: bool


class PageConverter:
    def load(self, path: str, width: int) -> List[Page]:
        raise NotImplementedError


class RasterConverter(PageConverter):
    @staticmethod
    def _load_image(path: str) -> Image.Image:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            return img.copy()

    @staticmethod
    def _normalize_image(img: Image.Image) -> Image.Image:
        if img.mode not in ("RGB", "L"):
            return img.convert("RGB")
        return img

    @staticmethod
    def _resize_to_width(img: Image.Image, width: int) -> Image.Image:
        if img.width == width:
            return img
        ratio = width / float(img.width)
        height = max(1, int(img.height * ratio))
        return img.resize((width, height), Image.LANCZOS)

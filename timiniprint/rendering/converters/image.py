from __future__ import annotations

from typing import List

from .base import Page, RasterConverter


class ImageConverter(RasterConverter):
    def load(self, path: str, width: int) -> List[Page]:
        img = self._load_image(path)
        img = self._resize_to_width(self._normalize_image(img), width)
        return [Page(img, dither=True, is_text=False)]

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set

from .base import Page, PageConverter
from .image import ImageConverter
from .pdf import PdfConverter
from .text import TextConverter

SUPPORTED_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".txt"}


class PageLoader:
    def __init__(self, converters: Optional[Dict[str, PageConverter]] = None) -> None:
        if converters is None:
            converters = {}
            image_converter = ImageConverter()
            for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
                converters[ext] = image_converter
            converters[".pdf"] = PdfConverter()
            converters[".txt"] = TextConverter()
        self._converters = converters

    @property
    def supported_extensions(self) -> Set[str]:
        return set(self._converters.keys())

    def load(self, path: str, width: int) -> List[Page]:
        ext = os.path.splitext(path)[1].lower()
        converter = self._converters.get(ext)
        if not converter:
            raise ValueError(f"Unsupported file extension: {ext}")
        return converter.load(path, width)


def load_pages(path: str, width: int) -> List[Page]:
    return PageLoader().load(path, width)


__all__ = ["Page", "PageLoader", "SUPPORTED_EXTENSIONS", "load_pages"]

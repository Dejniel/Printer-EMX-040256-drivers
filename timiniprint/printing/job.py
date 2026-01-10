from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from ..protocol import build_job
from ..rendering.converters import Page, PageLoader
from ..rendering.renderer import image_to_bw_pixels
from ..devices.models import PrinterModel

DEFAULT_BLACKENING = 3
DEFAULT_FEED_PADDING = 12
DEFAULT_IMAGE_ENERGY = 5000
DEFAULT_TEXT_ENERGY = 8000


@dataclass
class PrintSettings:
    compress: Optional[bool] = None
    dither: bool = True
    lsb_first: Optional[bool] = None
    blackening: int = DEFAULT_BLACKENING
    feed_padding: int = DEFAULT_FEED_PADDING


class PrintJobBuilder:
    def __init__(
        self,
        model: PrinterModel,
        settings: Optional[PrintSettings] = None,
        page_loader: Optional[PageLoader] = None,
    ) -> None:
        self.model = model
        self.settings = settings or PrintSettings()
        self.page_loader = page_loader or PageLoader()

    def build_from_file(self, path: str) -> bytes:
        self._validate_input_path(path)
        width = self._normalized_width(self.model.width)
        pages = self.page_loader.load(path, width)
        data_parts: List[bytes] = []
        for page in pages:
            pixels = image_to_bw_pixels(page.image, dither=self._use_dither(page))
            speed = self.model.text_print_speed if page.is_text else self.model.img_print_speed
            energy = self._select_energy(page)
            job = build_job(
                pixels,
                width,
                is_text=page.is_text,
                speed=speed,
                energy=energy,
                blackening=self.settings.blackening,
                compress=self._use_compress(),
                lsb_first=self._lsb_first(),
                new_format=self.model.new_format,
                feed_padding=self.settings.feed_padding,
                dev_dpi=self.model.dev_dpi,
            )
            data_parts.append(job)
        return b"".join(data_parts)

    def _use_dither(self, page: Page) -> bool:
        return self.settings.dither and page.dither

    def _use_compress(self) -> bool:
        if self.settings.compress is not None:
            return self.settings.compress
        return self.model.new_compress

    def _lsb_first(self) -> bool:
        if self.settings.lsb_first is not None:
            return self.settings.lsb_first
        return not self.model.a4xii

    def _select_energy(self, page: Page) -> int:
        if page.is_text:
            return self.model.text_energy or DEFAULT_TEXT_ENERGY
        return self.model.moderation_energy or DEFAULT_IMAGE_ENERGY

    @staticmethod
    def _normalized_width(width: int) -> int:
        if width % 8 == 0:
            return width
        return width - (width % 8)

    def _validate_input_path(self, path: str) -> None:
        ext = os.path.splitext(path)[1].lower()
        supported = self.page_loader.supported_extensions
        if ext not in supported:
            raise ValueError("Supported formats: " + ", ".join(sorted(supported)))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")

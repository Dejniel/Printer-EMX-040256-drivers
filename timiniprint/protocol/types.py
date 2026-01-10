from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Raster:
    """Row-major 0/1 pixel buffer used by the protocol encoder."""

    pixels: List[int]
    width: int

    def validate(self) -> None:
        """Validate dimensions for protocol encoding."""
        if self.width <= 0:
            raise ValueError("Width must be greater than zero")
        if len(self.pixels) % self.width != 0:
            raise ValueError("Pixels length must be a multiple of width")

    @property
    def height(self) -> int:
        """Return raster height computed from width and pixel count."""
        self.validate()
        return len(self.pixels) // self.width

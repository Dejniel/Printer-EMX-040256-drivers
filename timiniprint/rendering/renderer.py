from __future__ import annotations

from typing import List

from PIL import Image


def image_to_bw_pixels(img: Image.Image, dither: bool) -> List[int]:
    if dither:
        img = img.convert("1")
        data = list(img.getdata())
        return [1 if p == 0 else 0 for p in data]
    img = img.convert("L")
    data = list(img.getdata())
    avg = sum(data) / len(data) if data else 0
    threshold = int(max(0, min(255, avg - 13)))
    return [1 if p <= threshold else 0 for p in data]

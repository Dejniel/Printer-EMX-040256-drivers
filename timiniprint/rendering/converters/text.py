from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from .base import Page, PageConverter
from ..fonts import find_monospace_bold_font, load_font

COLUMNS_PER_WIDTH = 35 / 384
REFERENCE_PATTERN = "M.I"


class TextConverter(PageConverter):
    def __init__(self, font_path: Optional[str] = None, columns: Optional[int] = None) -> None:
        self._font_path = font_path
        self._columns_override = columns

    def load(self, path: str, width: int) -> List[Page]:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        text = text.replace("\t", "    ")
        img = self._render_text_image(text, width)
        return [Page(img, dither=False, is_text=True)]

    def _render_text_image(self, text: str, width: int) -> Image.Image:
        font_path = self._font_path or find_monospace_bold_font()
        columns = self._columns_for_width(width)
        reference_text = self._reference_text(columns)
        font = self._fit_truetype_font(font_path, width, reference_text)
        lines = self._wrap_text_lines(text, width, font)
        line_height = self._font_line_height(font)
        height = max(1, line_height * len(lines))
        img = Image.new("1", (width, height), 1)
        draw = ImageDraw.Draw(img)
        y = 0
        for line in lines:
            draw.text((0, y), line, font=font, fill=0)
            y += line_height
        return img

    @staticmethod
    def default_columns_for_width(width: int) -> int:
        return max(1, int(round(width * COLUMNS_PER_WIDTH)))

    def _columns_for_width(self, width: int) -> int:
        if self._columns_override is not None:
            return max(1, int(self._columns_override))
        return self.default_columns_for_width(width)

    def _reference_text(self, columns: int) -> str:
        if columns <= 0:
            return REFERENCE_PATTERN
        repeats = (columns // len(REFERENCE_PATTERN)) + 1
        return (REFERENCE_PATTERN * repeats)[:columns]

    @staticmethod
    def _fit_truetype_font(path: Optional[str], width: int, reference_text: str) -> ImageFont.FreeTypeFont:
        if not path:
            return ImageFont.load_default()
        low = 6
        high = 80
        best = None
        sample = reference_text or "M"
        while low <= high:
            size = (low + high) // 2
            font = load_font(path, size)
            if TextConverter._text_width(font, sample) <= width:
                best = font
                low = size + 1
            else:
                high = size - 1
        if best is None:
            return load_font(path, 6)
        return best

    def _wrap_text_lines(self, text: str, width: int, font: ImageFont.FreeTypeFont) -> List[str]:
        if text == "":
            return [""]
        lines: List[str] = []
        raw_lines = text.splitlines()
        if text.endswith("\n"):
            raw_lines.append("")
        for raw_line in raw_lines:
            if raw_line == "":
                lines.append("")
                continue
            lines.extend(self._wrap_line_by_width(raw_line, width, font))
        return lines

    def _wrap_line_by_width(
        self,
        line: str,
        width: int,
        font: ImageFont.FreeTypeFont,
    ) -> List[str]:
        if self._text_width(font, line) <= width:
            return [line]
        lines: List[str] = []
        remaining = line
        while remaining:
            if self._text_width(font, remaining) <= width:
                lines.append(remaining)
                break
            cut = self._fit_substring_length(remaining, width, font)
            if cut <= 0:
                lines.append(remaining[:1])
                remaining = remaining[1:]
                continue
            slice_text = remaining[:cut]
            split_at = slice_text.rfind(" ")
            if split_at > 0:
                lines.append(slice_text[:split_at])
                remaining = remaining[split_at + 1 :]
            else:
                lines.append(slice_text)
                remaining = remaining[cut:]
        return lines

    def _fit_substring_length(
        self,
        text: str,
        width: int,
        font: ImageFont.FreeTypeFont,
    ) -> int:
        low = 0
        high = len(text)
        best = 0
        while low <= high:
            mid = (low + high) // 2
            if mid == 0:
                low = 1
                continue
            if self._text_width(font, text[:mid]) <= width:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best

    @staticmethod
    def _text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
        if hasattr(font, "getlength"):
            return int(font.getlength(text))
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0]
        return font.getsize(text)[0]

    @staticmethod
    def _font_line_height(font: ImageFont.FreeTypeFont) -> int:
        if hasattr(font, "getmetrics"):
            ascent, descent = font.getmetrics()
            return ascent + descent
        if hasattr(font, "getbbox"):
            bbox = font.getbbox("Ag")
            return bbox[3] - bbox[1]
        return font.getsize("Ag")[1]

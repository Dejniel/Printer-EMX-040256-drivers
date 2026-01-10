from __future__ import annotations

from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from .base import Page, PageConverter
from ..fonts import find_monospace_bold_font, load_font


class TextConverter(PageConverter):
    def load(self, path: str, width: int) -> List[Page]:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        text = text.replace("\t", "    ")
        img = self._render_text_image(text, width)
        return [Page(img, dither=False, is_text=True)]

    def _render_text_image(self, text: str, width: int) -> Image.Image:
        font_path = find_monospace_bold_font()
        columns = self._columns_for_width(width)
        font = self._fit_truetype_font(font_path, width, columns)
        lines = self._wrap_text_lines(text, columns)
        line_height = self._font_line_height(font)
        height = max(1, line_height * len(lines))
        img = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(img)
        y = 0
        for line in lines:
            draw.text((0, y), line, font=font, fill=0)
            y += line_height
        return img

    @staticmethod
    def _columns_for_width(width: int) -> int:
        base_width = 384
        base_columns = 35
        return max(1, int(round(width * base_columns / base_width)))

    @staticmethod
    def _fit_truetype_font(path: Optional[str], width: int, columns: int) -> ImageFont.FreeTypeFont:
        if not path:
            return ImageFont.load_default()
        low = 6
        high = 80
        best = None
        sample = "M" * max(1, columns)
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

    @staticmethod
    def _wrap_text_lines(text: str, columns: int) -> List[str]:
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
            line = raw_line
            while len(line) > columns:
                break_at = line.rfind(" ", 0, columns + 1)
                if break_at > 0:
                    lines.append(line[:break_at])
                    line = line[break_at + 1 :]
                else:
                    lines.append(line[:columns])
                    line = line[columns:]
            lines.append(line)
        return lines

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

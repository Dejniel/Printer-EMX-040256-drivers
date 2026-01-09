from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence

from .font_utils import find_monospace_bold_font, load_font


@dataclass(frozen=True)
class Page:
    image: Image.Image
    dither: bool
    is_text: bool


class ImageConverter:
    def load(self, path: str, width: int) -> List[Page]:
        img = load_image(path)
        img = resize_to_width(normalize_image(img), width)
        return [Page(img, dither=True, is_text=False)]


class PdfConverter:
    def load(self, path: str, width: int) -> List[Page]:
        pages = load_pdf_pages(path)
        out = []
        for page in pages:
            img = resize_to_width(normalize_image(page), width)
            out.append(Page(img, dither=True, is_text=False))
        return out


class TextConverter:
    def load(self, path: str, width: int) -> List[Page]:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        text = text.replace("\t", "    ")
        img = render_text_image(text, width)
        return [Page(img, dither=False, is_text=True)]


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".pdf", ".txt"}


def load_pages(path: str, width: int) -> List[Page]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return PdfConverter().load(path, width)
    if ext == ".txt":
        return TextConverter().load(path, width)
    return ImageConverter().load(path, width)


def load_image(path: str) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.copy()


def normalize_image(img: Image.Image) -> Image.Image:
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img


def resize_to_width(img: Image.Image, width: int) -> Image.Image:
    if img.width == width:
        return img
    ratio = width / float(img.width)
    height = max(1, int(img.height * ratio))
    return img.resize((width, height), Image.LANCZOS)


def render_text_image(text: str, width: int) -> Image.Image:
    font_path = find_monospace_bold_font()
    columns = columns_for_width(width)
    font = fit_truetype_font(font_path, width, columns)
    lines = wrap_text_lines(text, columns)
    line_height = font_line_height(font)
    height = max(1, line_height * len(lines))
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    y = 0
    for line in lines:
        draw.text((0, y), line, font=font, fill=0)
        y += line_height
    return img


def columns_for_width(width: int) -> int:
    base_width = 384
    base_columns = 35
    return max(1, int(round(width * base_columns / base_width)))


def fit_truetype_font(path: Optional[str], width: int, columns: int) -> ImageFont.FreeTypeFont:
    if not path:
        return ImageFont.load_default()
    low = 6
    high = 80
    best = None
    sample = "M" * max(1, columns)
    while low <= high:
        size = (low + high) // 2
        font = load_font(path, size)
        if text_width(font, sample) <= width:
            best = font
            low = size + 1
        else:
            high = size - 1
    if best is None:
        return load_font(path, 6)
    return best


def wrap_text_lines(text: str, columns: int) -> List[str]:
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


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    if hasattr(font, "getlength"):
        return int(font.getlength(text))
    if hasattr(font, "getbbox"):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    return font.getsize(text)[0]


def font_line_height(font: ImageFont.FreeTypeFont) -> int:
    if hasattr(font, "getmetrics"):
        ascent, descent = font.getmetrics()
        return ascent + descent
    if hasattr(font, "getbbox"):
        bbox = font.getbbox("Ag")
        return bbox[3] - bbox[1]
    return font.getsize("Ag")[1]


def load_pdf_pages(path: str) -> List[Image.Image]:
    errors = []
    try:
        pages: List[Image.Image] = []
        with Image.open(path) as img:
            for page in ImageSequence.Iterator(img):
                page.load()
                pages.append(normalize_image(page).copy())
        if pages:
            return pages
        errors.append("Pillow: no pages rendered")
    except Exception as exc:
        errors.append(f"Pillow: {exc}")

    try:
        import fitz  # type: ignore
    except Exception:
        fitz = None
    if fitz:
        try:
            doc = fitz.open(path)
            pages = []
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    mode = "RGBA" if pix.n >= 4 else "RGB"
                    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                    pages.append(normalize_image(img))
            finally:
                doc.close()
            if pages:
                return pages
            errors.append("PyMuPDF: no pages rendered")
        except Exception as exc:
            errors.append(f"PyMuPDF: {exc}")

    try:
        from pdf2image import convert_from_path  # type: ignore
    except Exception:
        convert_from_path = None
    if convert_from_path:
        try:
            images = convert_from_path(path, dpi=200)
            if images:
                return [normalize_image(img) for img in images]
            errors.append("pdf2image: no pages rendered")
        except Exception as exc:
            errors.append(f"pdf2image: {exc}")

    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_base = os.path.join(tmpdir, "page")
                cmd = [pdftoppm, "-png", "-r", "200", path, output_base]
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    msg = result.stderr.strip() or result.stdout.strip()
                    raise RuntimeError(msg or f"pdftoppm exited with {result.returncode}")
                output_paths = glob.glob(output_base + "-*.png")
                if not output_paths:
                    raise RuntimeError("no pages rendered")
                pages = []
                for output_path in sorted(output_paths, key=_pdftoppm_page_sort_key):
                    with Image.open(output_path) as img:
                        img.load()
                        pages.append(normalize_image(img).copy())
                return pages
        except Exception as exc:
            errors.append(f"pdftoppm: {exc}")
    else:
        errors.append("pdftoppm: not found")

    detail = "; ".join(errors) if errors else "no details"
    raise RuntimeError(
        "PDF render failed. Install PyMuPDF (pip install pymupdf) or pdf2image + poppler, "
        "or install system pdftoppm. Details: " + detail
    )


def _pdftoppm_page_sort_key(path: str) -> int:
    stem = os.path.splitext(path)[0]
    suffix = stem.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return 0

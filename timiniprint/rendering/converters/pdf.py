from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
from typing import List

from PIL import Image, ImageSequence

from .base import Page, RasterConverter


class PdfConverter(RasterConverter):
    def load(self, path: str, width: int) -> List[Page]:
        pages = self._load_pdf_pages(path)
        out = []
        for page in pages:
            img = self._resize_to_width(self._normalize_image(page), width)
            out.append(Page(img, dither=True, is_text=False))
        return out

    def _load_pdf_pages(self, path: str) -> List[Image.Image]:
        errors: List[str] = []

        pages = self._load_with_pillow(path, errors)
        if pages:
            return pages

        pages = self._load_with_pymupdf(path, errors)
        if pages:
            return pages

        pages = self._load_with_pdf2image(path, errors)
        if pages:
            return pages

        pages = self._load_with_pdftoppm(path, errors)
        if pages:
            return pages

        detail = "; ".join(errors) if errors else "no details"
        raise RuntimeError(
            "PDF render failed. Install PyMuPDF (pip install pymupdf) or pdf2image + poppler, "
            "or install system pdftoppm. Details: " + detail
        )

    def _load_with_pillow(self, path: str, errors: List[str]) -> List[Image.Image]:
        try:
            pages: List[Image.Image] = []
            with Image.open(path) as img:
                for page in ImageSequence.Iterator(img):
                    page.load()
                    pages.append(self._normalize_image(page).copy())
            if pages:
                return pages
            errors.append("Pillow: no pages rendered")
        except Exception as exc:
            errors.append(f"Pillow: {exc}")
        return []

    def _load_with_pymupdf(self, path: str, errors: List[str]) -> List[Image.Image]:
        try:
            import fitz  # type: ignore
        except Exception:
            fitz = None
        if not fitz:
            return []
        try:
            doc = fitz.open(path)
            pages = []
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    mode = "RGBA" if pix.n >= 4 else "RGB"
                    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                    pages.append(self._normalize_image(img))
            finally:
                doc.close()
            if pages:
                return pages
            errors.append("PyMuPDF: no pages rendered")
        except Exception as exc:
            errors.append(f"PyMuPDF: {exc}")
        return []

    def _load_with_pdf2image(self, path: str, errors: List[str]) -> List[Image.Image]:
        try:
            from pdf2image import convert_from_path  # type: ignore
        except Exception:
            convert_from_path = None
        if not convert_from_path:
            return []
        try:
            images = convert_from_path(path, dpi=200)
            if images:
                return [self._normalize_image(img) for img in images]
            errors.append("pdf2image: no pages rendered")
        except Exception as exc:
            errors.append(f"pdf2image: {exc}")
        return []

    def _load_with_pdftoppm(self, path: str, errors: List[str]) -> List[Image.Image]:
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            errors.append("pdftoppm: not found")
            return []
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
                for output_path in sorted(output_paths, key=self._pdftoppm_page_sort_key):
                    with Image.open(output_path) as img:
                        img.load()
                        pages.append(self._normalize_image(img).copy())
                return pages
        except Exception as exc:
            errors.append(f"pdftoppm: {exc}")
        return []

    @staticmethod
    def _pdftoppm_page_sort_key(path: str) -> int:
        stem = os.path.splitext(path)[0]
        suffix = stem.rsplit("-", 1)[-1]
        try:
            return int(suffix)
        except ValueError:
            return 0

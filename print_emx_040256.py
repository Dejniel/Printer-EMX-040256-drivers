#!/usr/bin/env python3
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence
except Exception as exc:  # pragma: no cover
    print("Pillow is required. Install with: pip install -r requirements.txt", file=sys.stderr)
    raise

try:
    import serial
except Exception as exc:  # pragma: no cover
    print("pyserial is required. Install with: pip install -r requirements.txt", file=sys.stderr)
    raise


# EMX-040256 defaults (from PrintModelUtils)
PRINTER_WIDTH = 384
DEV_DPI = 200
IMG_SPEED = 10
IMG_MTU = 180
INTERVAL_MS = 4
ENERGY_IMAGE = 5000
BLACKENING_LEVEL = 3
BAUD_RATE = 115200
DEVICE_ENV_VAR = "EMX_DEVICE"
DEFAULT_DEVICE = "/dev/rfcomm0"
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".txt"}
DEFAULT_FEED_PADDING = 25
FEED_PADDING = max(1, DEFAULT_FEED_PADDING // 2)
TEXT_COLUMNS = 35
MONO_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
)

# Flow control patterns seen in the Android app
FLOW_ON = bytes.fromhex("51 78 AE 01 01 00 10 70 FF")
FLOW_OFF = bytes.fromhex("51 78 AE 01 01 00 00 00 FF")

def build_crc8_table() -> List[int]:
    table = []
    for value in range(256):
        crc = value
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        table.append(crc)
    return table


CHECKSUM_TABLE = build_crc8_table()


def crc8(data: bytes, initial: int = 0) -> int:
    crc = initial
    for value in data:
        crc = CHECKSUM_TABLE[(crc ^ value) & 0xFF]
    return crc & 0xFF


def make_packet(cmd: int, payload: bytes) -> bytes:
    length = len(payload)
    header = bytes([
        0x51, 0x78, cmd & 0xFF, 0x00,
        length & 0xFF, (length >> 8) & 0xFF,
    ])
    checksum = crc8(payload)
    return header + payload + bytes([checksum, 0xFF])


def blackening_cmd(level: int) -> bytes:
    level = max(1, min(5, level))
    payload = bytes([0x30 + level])
    return make_packet(0xA4, payload)


def energy_cmd(energy: int) -> bytes:
    if energy <= 0:
        return b""
    payload = energy.to_bytes(2, "little", signed=False)
    return make_packet(0xAF, payload)


def print_mode_cmd(is_text: bool) -> bytes:
    payload = bytes([1 if is_text else 0])
    return make_packet(0xBE, payload)


def feed_paper_cmd(speed: int) -> bytes:
    payload = bytes([speed & 0xFF])
    return make_packet(0xBD, payload)


def paper_cmd(dpi: int) -> bytes:
    if dpi == 300:
        payload = bytes([0x48, 0x00])
    else:
        payload = bytes([0x30, 0x00])
    return make_packet(0xA1, payload)


def dev_state_cmd() -> bytes:
    return make_packet(0xA3, bytes([0x00]))


def encode_run(color: int, count: int) -> List[int]:
    out = []
    while count > 127:
        out.append((color << 7) | 127)
        count -= 127
    if count > 0:
        out.append((color << 7) | count)
    return out


def rle_encode_line(line: List[int]) -> List[int]:
    if not line:
        return []
    runs: List[int] = []
    prev = line[0]
    count = 1
    has_black = 1 if prev else 0
    for pix in line[1:]:
        if pix:
            has_black = 1
        if pix == prev:
            count += 1
        else:
            runs.extend(encode_run(prev, count))
            prev = pix
            count = 1
    if has_black:
        runs.extend(encode_run(prev, count))
    if not runs:
        runs.extend(encode_run(prev, count))
    return runs


def pack_line(line: List[int], lsb_first: bool) -> bytes:
    out = bytearray()
    for i in range(0, len(line), 8):
        chunk = line[i:i + 8]
        if len(chunk) < 8:
            chunk = chunk + [0] * (8 - len(chunk))
        value = 0
        if lsb_first:
            for bit, pix in enumerate(chunk):
                if pix:
                    value |= (1 << bit)
        else:
            for bit, pix in enumerate(chunk):
                if pix:
                    value |= (1 << (7 - bit))
        out.append(value)
    return bytes(out)


def build_line_packets(
    pixels: List[int],
    width: int,
    speed: int,
    compress: bool,
    lsb_first: bool,
    line_feed_every: int,
) -> bytes:
    if width % 8 != 0:
        raise ValueError("Width must be divisible by 8")
    height = len(pixels) // width
    width_bytes = width // 8
    out = bytearray()
    for row in range(height):
        line = pixels[row * width:(row + 1) * width]
        if compress:
            rle = rle_encode_line(line)
            if len(rle) <= width_bytes:
                out += make_packet(0xBF, bytes(rle))
            else:
                raw = pack_line(line, lsb_first)
                out += make_packet(0xA2, raw)
        else:
            raw = pack_line(line, lsb_first)
            out += make_packet(0xA2, raw)
        if line_feed_every and (row + 1) % line_feed_every == 0:
            out += feed_paper_cmd(speed)
    return bytes(out)


def build_print_payload(
    pixels: List[int],
    width: int,
    is_text: bool,
    speed: int,
    energy: int,
    compress: bool,
    lsb_first: bool,
) -> bytes:
    payload = bytearray()
    payload += energy_cmd(energy)
    payload += print_mode_cmd(is_text)
    payload += feed_paper_cmd(speed)
    payload += build_line_packets(
        pixels,
        width,
        speed,
        compress,
        lsb_first,
        line_feed_every=200,
    )
    return bytes(payload)


def build_job(
    pixels: List[int],
    width: int,
    is_text: bool,
    speed: int,
    energy: int,
    blackening: int,
    compress: bool,
    lsb_first: bool,
) -> bytes:
    job = bytearray()
    job += blackening_cmd(blackening)
    job += build_print_payload(
        pixels,
        width,
        is_text,
        speed,
        energy,
        compress,
        lsb_first,
    )
    job += feed_paper_cmd(FEED_PADDING)
    job += paper_cmd(DEV_DPI)
    job += paper_cmd(DEV_DPI)
    job += feed_paper_cmd(FEED_PADDING)
    job += dev_state_cmd()
    return bytes(job)


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


def load_image(path: str) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        return img.copy()


def resize_to_width(img: Image.Image, width: int) -> Image.Image:
    if img.width == width:
        return img
    ratio = width / float(img.width)
    height = max(1, int(img.height * ratio))
    return img.resize((width, height), Image.LANCZOS)


def normalize_image(img: Image.Image) -> Image.Image:
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img


def load_images(path: str, width: int) -> List[Tuple[Image.Image, bool]]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        images = [(img, True) for img in load_pdf_pages(path)]
    elif ext == ".txt":
        images = [(load_text_image(path, width, TEXT_COLUMNS), False)]
    else:
        images = [(load_image(path), True)]
    return [(resize_to_width(normalize_image(img), width), dither) for img, dither in images]


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
            pages: List[Image.Image] = []
            try:
                for page in doc:
                    pix = page.get_pixmap(dpi=DEV_DPI)
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
            images = convert_from_path(path, dpi=DEV_DPI)
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
                cmd = [
                    pdftoppm,
                    "-png",
                    "-r", str(DEV_DPI),
                    path,
                    output_base,
                ]
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


def load_text_image(path: str, width: int, columns: int) -> Image.Image:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    text = text.replace("\t", "    ")
    return render_text_image(text, width, columns)


def render_text_image(text: str, width: int, columns: int) -> Image.Image:
    font = load_monospace_font(width, columns)
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
                line = line[break_at + 1:]
            else:
                lines.append(line[:columns])
                line = line[columns:]
        lines.append(line)
    return lines


def load_monospace_font(width: int, columns: int) -> ImageFont.FreeTypeFont:
    for path in MONO_FONT_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            return fit_truetype_font(path, width, columns)
        except Exception:
            continue
    return ImageFont.load_default()


def fit_truetype_font(path: str, width: int, columns: int) -> ImageFont.FreeTypeFont:
    low = 6
    high = 80
    best = None
    sample = "M" * columns
    while low <= high:
        size = (low + high) // 2
        font = ImageFont.truetype(path, size)
        if text_width(font, sample) <= width:
            best = font
            low = size + 1
        else:
            high = size - 1
    if best is None:
        return ImageFont.truetype(path, 6)
    return best


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


def send_data(
    device: str,
    baud: int,
    data: bytes,
    chunk_size: int,
    interval_ms: int,
    flow_control: bool,
) -> None:
    with serial.Serial(device, baudrate=baud, timeout=0) as ser:
        is_full = False
        offset = 0
        while offset < len(data):
            if flow_control:
                pending = ser.read(ser.in_waiting or 0)
                if FLOW_ON in pending:
                    is_full = True
                elif FLOW_OFF in pending:
                    is_full = False
            if is_full:
                time.sleep(0.01)
                continue
            chunk = data[offset:offset + chunk_size]
            ser.write(chunk)
            ser.flush()
            offset += len(chunk)
            time.sleep(interval_ms / 1000.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print a PNG/JPG/TXT or a multi-page PDF to EMX-040256. Device path comes from "
            f"${DEVICE_ENV_VAR} or defaults to {DEFAULT_DEVICE}."
        )
    )
    parser.add_argument("path", help="Path to a .png/.jpg/.jpeg/.pdf/.txt file")
    return parser.parse_args()


def resolve_device() -> str:
    return os.environ.get(DEVICE_ENV_VAR, DEFAULT_DEVICE)


def validate_input_path(path: str) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError("Only .png, .jpg, .jpeg, .pdf, or .txt files are supported.")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")


def main() -> int:
    args = parse_args()
    try:
        validate_input_path(args.path)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

    images = load_images(args.path, PRINTER_WIDTH)
    jobs = []
    for img, dither in images:
        pixels = image_to_bw_pixels(img, dither=dither)
        jobs.append(
            build_job(
                pixels,
                PRINTER_WIDTH,
                is_text=False,
                speed=IMG_SPEED,
                energy=ENERGY_IMAGE,
                blackening=BLACKENING_LEVEL,
                compress=True,
                lsb_first=True,
            )
        )
    data = b"".join(jobs)

    send_data(
        resolve_device(),
        BAUD_RATE,
        data,
        chunk_size=IMG_MTU,
        interval_ms=INTERVAL_MS,
        flow_control=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

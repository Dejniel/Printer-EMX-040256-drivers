from __future__ import annotations

from typing import Iterable, List

import crc8


def crc8_value(data: bytes) -> int:
    hasher = crc8.crc8()
    hasher.update(data)
    return hasher.digest()[0]


def make_packet(cmd: int, payload: bytes, new_format: bool) -> bytes:
    length = len(payload)
    header = bytes(
        [
            0x51,
            0x78,
            cmd & 0xFF,
            0x00,
            length & 0xFF,
            (length >> 8) & 0xFF,
        ]
    )
    checksum = crc8_value(payload)
    packet = header + payload + bytes([checksum, 0xFF])
    if new_format:
        return bytes([0x12]) + packet
    return packet


def blackening_cmd(level: int, new_format: bool) -> bytes:
    level = max(1, min(5, level))
    payload = bytes([0x30 + level])
    return make_packet(0xA4, payload, new_format)


def energy_cmd(energy: int, new_format: bool) -> bytes:
    if energy <= 0:
        return b""
    payload = energy.to_bytes(2, "little", signed=False)
    return make_packet(0xAF, payload, new_format)


def print_mode_cmd(is_text: bool, new_format: bool) -> bytes:
    payload = bytes([1 if is_text else 0])
    return make_packet(0xBE, payload, new_format)


def feed_paper_cmd(speed: int, new_format: bool) -> bytes:
    payload = bytes([speed & 0xFF])
    return make_packet(0xBD, payload, new_format)


def paper_cmd(dpi: int, new_format: bool) -> bytes:
    if dpi == 300:
        payload = bytes([0x48, 0x00])
    else:
        payload = bytes([0x30, 0x00])
    return make_packet(0xA1, payload, new_format)


def dev_state_cmd(new_format: bool) -> bytes:
    return make_packet(0xA3, bytes([0x00]), new_format)


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
        chunk = line[i : i + 8]
        if len(chunk) < 8:
            chunk = chunk + [0] * (8 - len(chunk))
        value = 0
        if lsb_first:
            for bit, pix in enumerate(chunk):
                if pix:
                    value |= 1 << bit
        else:
            for bit, pix in enumerate(chunk):
                if pix:
                    value |= 1 << (7 - bit)
        out.append(value)
    return bytes(out)


def build_line_packets(
    pixels: List[int],
    width: int,
    speed: int,
    compress: bool,
    lsb_first: bool,
    new_format: bool,
    line_feed_every: int,
) -> bytes:
    if width % 8 != 0:
        raise ValueError("Width must be divisible by 8")
    height = len(pixels) // width
    width_bytes = width // 8
    out = bytearray()
    for row in range(height):
        line = pixels[row * width : (row + 1) * width]
        if compress:
            rle = rle_encode_line(line)
            if len(rle) <= width_bytes:
                out += make_packet(0xBF, bytes(rle), new_format)
            else:
                raw = pack_line(line, lsb_first)
                out += make_packet(0xA2, raw, new_format)
        else:
            raw = pack_line(line, lsb_first)
            out += make_packet(0xA2, raw, new_format)
        if line_feed_every and (row + 1) % line_feed_every == 0:
            out += feed_paper_cmd(speed, new_format)
    return bytes(out)


def build_print_payload(
    pixels: List[int],
    width: int,
    is_text: bool,
    speed: int,
    energy: int,
    compress: bool,
    lsb_first: bool,
    new_format: bool,
) -> bytes:
    payload = bytearray()
    payload += energy_cmd(energy, new_format)
    payload += print_mode_cmd(is_text, new_format)
    payload += feed_paper_cmd(speed, new_format)
    payload += build_line_packets(
        pixels,
        width,
        speed,
        compress,
        lsb_first,
        new_format,
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
    new_format: bool,
    feed_padding: int,
    dev_dpi: int,
) -> bytes:
    job = bytearray()
    job += blackening_cmd(blackening, new_format)
    job += build_print_payload(
        pixels,
        width,
        is_text,
        speed,
        energy,
        compress,
        lsb_first,
        new_format,
    )
    job += feed_paper_cmd(feed_padding, new_format)
    job += paper_cmd(dev_dpi, new_format)
    job += paper_cmd(dev_dpi, new_format)
    job += feed_paper_cmd(feed_padding, new_format)
    job += dev_state_cmd(new_format)
    return bytes(job)

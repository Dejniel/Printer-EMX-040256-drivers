from __future__ import annotations

import crc8


def crc8_value(data: bytes) -> int:
    """Return CRC8 checksum byte for the payload."""
    hasher = crc8.crc8()
    hasher.update(data)
    return hasher.digest()[0]


def make_packet(cmd: int, payload: bytes, new_format: bool) -> bytes:
    """Wrap a payload in the printer command packet format."""
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
    """Build the blackening (density) command packet."""
    level = max(1, min(5, level))
    payload = bytes([0x30 + level])
    return make_packet(0xA4, payload, new_format)


def energy_cmd(energy: int, new_format: bool) -> bytes:
    """Build the energy command packet (empty if energy <= 0)."""
    if energy <= 0:
        return b""
    payload = energy.to_bytes(2, "little", signed=False)
    return make_packet(0xAF, payload, new_format)


def print_mode_cmd(is_text: bool, new_format: bool) -> bytes:
    """Build the print mode command packet (text vs image)."""
    payload = bytes([1 if is_text else 0])
    return make_packet(0xBE, payload, new_format)


def feed_paper_cmd(speed: int, new_format: bool) -> bytes:
    """Build the feed paper command packet."""
    payload = bytes([speed & 0xFF])
    return make_packet(0xBD, payload, new_format)


def paper_cmd(dpi: int, new_format: bool) -> bytes:
    """Build the paper size/DPI command packet."""
    if dpi == 300:
        payload = bytes([0x48, 0x00])
    else:
        payload = bytes([0x30, 0x00])
    return make_packet(0xA1, payload, new_format)


def dev_state_cmd(new_format: bool) -> bytes:
    """Build the device state query command packet."""
    return make_packet(0xA3, bytes([0x00]), new_format)

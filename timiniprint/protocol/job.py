from __future__ import annotations

from typing import List

from .commands import (
    blackening_cmd,
    dev_state_cmd,
    energy_cmd,
    feed_paper_cmd,
    paper_cmd,
    print_mode_cmd,
)
from .encoding import build_line_packets
from .types import Raster


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
    """Build the main payload for a print job (no final feed/state)."""
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


def build_print_payload_from_raster(
    raster: Raster,
    is_text: bool,
    speed: int,
    energy: int,
    compress: bool,
    lsb_first: bool,
    new_format: bool,
) -> bytes:
    """Build the main payload from a Raster helper object."""
    raster.validate()
    return build_print_payload(
        raster.pixels,
        raster.width,
        is_text,
        speed,
        energy,
        compress,
        lsb_first,
        new_format,
    )


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
    """Build a full job payload ready to send to the printer."""
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


def build_job_from_raster(
    raster: Raster,
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
    """Build a full job payload from a Raster helper object."""
    raster.validate()
    return build_job(
        raster.pixels,
        raster.width,
        is_text,
        speed,
        energy,
        blackening,
        compress,
        lsb_first,
        new_format,
        feed_padding,
        dev_dpi,
    )

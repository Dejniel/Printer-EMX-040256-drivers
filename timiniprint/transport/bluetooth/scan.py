from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import List

from .types import DeviceInfo


def _scan_bluetoothctl(timeout: float) -> List[DeviceInfo]:
    if not shutil.which("bluetoothctl"):
        return []
    timeout_s = max(1, int(timeout))
    try:
        subprocess.run(
            ["bluetoothctl", "--timeout", str(timeout_s), "scan", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except Exception:
        return []
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except Exception:
        return []
    devices = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("Device "):
            continue
        parts = line.split(" ", 2)
        if len(parts) < 2:
            continue
        address = parts[1]
        name = parts[2] if len(parts) > 2 else ""
        devices.append(DeviceInfo(name=name, address=address))
    return _dedupe_devices(devices)


def _scan_bleak(timeout: float) -> List[DeviceInfo]:
    try:
        from bleak import BleakScanner
    except Exception:
        return []

    async def run() -> List[DeviceInfo]:
        found = await BleakScanner.discover(timeout=timeout)
        results = []
        for device in found:
            name = device.name or ""
            results.append(DeviceInfo(name=name, address=device.address))
        return results

    try:
        devices = asyncio.run(run())
    except Exception:
        return []
    return _dedupe_devices(devices)


def _dedupe_devices(devices: List[DeviceInfo]) -> List[DeviceInfo]:
    by_addr = {}
    for device in devices:
        existing = by_addr.get(device.address)
        if existing is None or (not existing.name and device.name):
            by_addr[device.address] = device
    results = list(by_addr.values())
    results.sort(key=lambda item: (item.name or "", item.address))
    return results

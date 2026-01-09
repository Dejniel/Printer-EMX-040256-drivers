from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
RFCOMM_CHANNELS = [1, 2, 3, 4, 5]


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    address: str


class SppBackend:
    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._connected = False
        self._channel: Optional[int] = None

    @staticmethod
    async def scan(timeout: float = 5.0) -> List[DeviceInfo]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _scan_blocking, timeout)

    async def connect(self, address: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect_blocking, address)

    def is_connected(self) -> bool:
        return self._connected

    async def disconnect(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._disconnect_blocking)

    async def write(self, data: bytes, chunk_size: int, interval_ms: int) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_blocking, data, chunk_size, interval_ms)

    def _connect_blocking(self, address: str) -> None:
        if self._connected:
            return
        if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
            raise RuntimeError(
                "RFCOMM sockets are not supported on this system. Use --serial or run on Linux."
            )
        channels = _resolve_rfcomm_channels(address)
        last_error = None
        for channel in channels:
            sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            sock.settimeout(8)
            try:
                sock.connect((address, channel))
                self._sock = sock
                self._connected = True
                self._channel = channel
                return
            except OSError as exc:
                last_error = exc
                try:
                    sock.close()
                except Exception:
                    pass
        detail = f"channels tried: {channels}"
        if last_error:
            detail += f", last error: {last_error}"
        raise RuntimeError("SPP connection failed (" + detail + ")")

    def _disconnect_blocking(self) -> None:
        if not self._sock:
            self._connected = False
            self._channel = None
            return
        try:
            self._sock.close()
        finally:
            self._sock = None
            self._connected = False
            self._channel = None

    def _write_blocking(self, data: bytes, chunk_size: int, interval_ms: int) -> None:
        if not self._sock or not self._connected:
            raise RuntimeError("Not connected to a Bluetooth SPP device")
        interval = max(0.0, interval_ms / 1000.0)
        offset = 0
        while offset < len(data):
            chunk = data[offset : offset + chunk_size]
            with self._lock:
                self._sock.sendall(chunk)
            offset += len(chunk)
            if interval:
                time.sleep(interval)


def _scan_blocking(timeout: float) -> List[DeviceInfo]:
    devices = _scan_bluetoothctl(timeout)
    if devices:
        return devices
    return _scan_bleak(timeout)


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


def _resolve_rfcomm_channels(address: str) -> List[int]:
    channel = _resolve_rfcomm_channel(address)
    if channel is None:
        return list(RFCOMM_CHANNELS)
    channels = [channel]
    for candidate in RFCOMM_CHANNELS:
        if candidate != channel:
            channels.append(candidate)
    return channels


def _resolve_rfcomm_channel(address: str) -> Optional[int]:
    if not shutil.which("sdptool"):
        return None
    try:
        result = subprocess.run(
            ["sdptool", "browse", address],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except Exception:
        return None
    output = result.stdout or ""
    channel = None
    seen_serial = False
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("Service Name:"):
            name = line.split(":", 1)[-1].strip().lower()
            seen_serial = any(key in name for key in ("serial", "spp", "printer"))
        elif line.startswith("Channel:"):
            try:
                value = int(line.split(":", 1)[-1].strip())
            except ValueError:
                value = None
            if value is None:
                continue
            if seen_serial:
                return value
            if channel is None:
                channel = value
            seen_serial = False
        elif not line:
            seen_serial = False
    return channel

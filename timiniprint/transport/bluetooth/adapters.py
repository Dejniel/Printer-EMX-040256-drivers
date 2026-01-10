from __future__ import annotations

import socket
import shutil
import subprocess
from typing import Dict, List, Optional

from .constants import IS_WINDOWS, RFCOMM_CHANNELS
from .scan import _scan_bleak, _scan_bluetoothctl
from .types import DeviceInfo, SocketLike
from .winrt import _scan_winrt, _scan_winrt_async, _WinRtSocket, _winrt_imports


class _BluetoothAdapter:
    single_channel = False

    def scan_blocking(self, timeout: float) -> List[DeviceInfo]:
        raise NotImplementedError

    def create_socket(self) -> SocketLike:
        raise NotImplementedError

    def resolve_rfcomm_channel(self, address: str) -> Optional[int]:
        return None


class _LinuxBluetoothAdapter(_BluetoothAdapter):
    def scan_blocking(self, timeout: float) -> List[DeviceInfo]:
        devices = _scan_bluetoothctl(timeout)
        if devices:
            return devices
        return _scan_bleak(timeout)

    def create_socket(self) -> SocketLike:
        if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(socket, "BTPROTO_RFCOMM"):
            raise RuntimeError(
                "RFCOMM sockets are not supported on this system. Use --serial or run on Linux."
            )
        return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)

    def resolve_rfcomm_channel(self, address: str) -> Optional[int]:
        return _resolve_rfcomm_channel_linux(address)


class _WindowsBluetoothAdapter(_BluetoothAdapter):
    single_channel = True

    def __init__(self) -> None:
        self._service_by_address: Dict[str, str] = {}

    def scan_blocking(self, timeout: float) -> List[DeviceInfo]:
        devices, mapping = _scan_winrt(timeout)
        self._service_by_address = mapping
        return devices

    def create_socket(self) -> SocketLike:
        return _WinRtSocket(self)

    def resolve_rfcomm_channel(self, address: str) -> Optional[int]:
        return RFCOMM_CHANNELS[0]

    async def _resolve_service_async(self, address: str, timeout: float = 5.0):
        service_id = self._service_by_address.get(address)
        if not service_id:
            _, mapping = await _scan_winrt_async(timeout)
            self._service_by_address = mapping
            service_id = self._service_by_address.get(address)
        if not service_id:
            return None
        _, _, RfcommDeviceService, _, _, _ = _winrt_imports()
        return await RfcommDeviceService.from_id_async(service_id)


_ADAPTER: Optional[_BluetoothAdapter] = None


def _get_adapter() -> _BluetoothAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        if IS_WINDOWS:
            _ADAPTER = _WindowsBluetoothAdapter()
        else:
            _ADAPTER = _LinuxBluetoothAdapter()
    return _ADAPTER


def _resolve_rfcomm_channel_linux(address: str) -> Optional[int]:
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

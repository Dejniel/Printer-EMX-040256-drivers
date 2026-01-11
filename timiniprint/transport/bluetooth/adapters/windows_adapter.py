from __future__ import annotations

from typing import Dict, List, Optional

from .base import _BluetoothAdapter
from ..constants import RFCOMM_CHANNELS
from ..types import DeviceInfo, SocketLike
from .windows_win32 import pair_device, scan_inquiry
from .windows_winrt import _pair_winrt_async, _run_winrt, _scan_winrt, _scan_winrt_async, _WinRtSocket, _winrt_imports


class _WindowsBluetoothAdapter(_BluetoothAdapter):
    single_channel = True

    def __init__(self) -> None:
        self._service_by_address: Dict[str, str] = {}

    def scan_blocking(self, timeout: float) -> List[DeviceInfo]:
        devices = scan_inquiry(timeout)
        bleak_devices = self._scan_bleak(timeout)
        devices = DeviceInfo.dedupe(devices + bleak_devices)
        try:
            winrt_devices, mapping = _scan_winrt(timeout)
            self._service_by_address = mapping
            if winrt_devices:
                devices = DeviceInfo.dedupe(devices + winrt_devices)
        except Exception:
            pass
        return devices

    def create_socket(self) -> SocketLike:
        return _WinRtSocket(self)

    def resolve_rfcomm_channel(self, address: str) -> Optional[int]:
        return RFCOMM_CHANNELS[0]

    def ensure_paired(self, address: str) -> None:
        service_id = self._service_by_address.get(address)
        winrt_error = None
        win32_error = None
        win32_paired = False
        try:
            _run_winrt(_pair_winrt_async(address, service_id))
        except Exception as exc:
            winrt_error = exc
        if address not in self._service_by_address:
            try:
                _, mapping = _scan_winrt(5.0)
            except Exception:
                mapping = None
            if mapping is not None:
                self._service_by_address = mapping
        needs_win32 = winrt_error is not None or address not in self._service_by_address
        if needs_win32:
            try:
                win32_paired = pair_device(address)
                if not win32_paired:
                    win32_error = RuntimeError("pairing failed (Win32 returned False)")
            except Exception as exc:
                win32_error = exc
            if address not in self._service_by_address:
                try:
                    _, mapping = _scan_winrt(5.0)
                except Exception:
                    mapping = None
                if mapping is not None:
                    self._service_by_address = mapping
        if winrt_error and not win32_paired:
            if win32_error:
                raise RuntimeError(f"pairing failed (WinRT: {winrt_error}; Win32: {win32_error})")
            raise RuntimeError(f"pairing failed (WinRT: {winrt_error})")
        if win32_error and address not in self._service_by_address:
            raise RuntimeError(f"pairing failed (Win32: {win32_error})")

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

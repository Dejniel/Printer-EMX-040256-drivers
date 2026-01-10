from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Dict, List, Optional, Tuple, TypeVar

SPP_UUID = uuid.UUID("00001101-0000-1000-8000-00805f9b34fb")
RFCOMM_CHANNELS = [1, 2, 3, 4, 5]
SocketLike = Any
IS_WINDOWS = sys.platform.startswith("win")
T = TypeVar("T")


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    address: str


ScanResult = Tuple[List[DeviceInfo], Dict[str, str]]


class _BluetoothAdapter:
    single_channel = False

    def scan_blocking(self, timeout: float) -> List[DeviceInfo]:
        raise NotImplementedError

    def create_socket(self) -> SocketLike:
        raise NotImplementedError

    def resolve_rfcomm_channel(self, address: str) -> Optional[int]:
        return None


class _BlueZAdapter(_BluetoothAdapter):
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
            _ADAPTER = _BlueZAdapter()
    return _ADAPTER


class _WinRtSocket:
    def __init__(self, adapter: _WindowsBluetoothAdapter) -> None:
        self._adapter = adapter
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._socket = None
        self._writer = None

    def _run(self, coro: Awaitable[T]) -> T:
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        return self._loop.run_until_complete(coro)

    def connect(self, target) -> None:
        address, _channel = target
        service = self._run(self._adapter._resolve_service_async(address))
        if not service:
            raise RuntimeError("Bluetooth SPP service not found for device")
        _, _, _, _, StreamSocket, DataWriter = _winrt_imports()
        self._socket = StreamSocket()
        self._run(self._socket.connect_async(service.connection_host_name, service.connection_service_name))
        self._writer = DataWriter(self._socket.output_stream)

    def sendall(self, data: bytes) -> None:
        if not self._writer:
            raise RuntimeError("Not connected to a Bluetooth SPP device")
        self._writer.write_bytes(bytearray(data))
        self._run(self._writer.store_async())
        self._run(self._writer.flush_async())

    def close(self) -> None:
        if self._writer:
            close_writer = getattr(self._writer, "close", None)
            if callable(close_writer):
                close_writer()
            self._writer = None
        if self._socket:
            close_socket = getattr(self._socket, "close", None)
            if callable(close_socket):
                close_socket()
            self._socket = None
        if self._loop:
            asyncio.set_event_loop(None)
            self._loop.close()
            self._loop = None


class SppBackend:
    def __init__(self) -> None:
        self._sock: Optional[SocketLike] = None
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
        channels = _resolve_rfcomm_channels(address)
        last_error = None
        for channel in channels:
            sock = None
            try:
                sock = _get_adapter().create_socket()
                set_timeout = getattr(sock, "settimeout", None)
                if callable(set_timeout):
                    set_timeout(8)
                sock.connect((address, channel))
                self._sock = sock
                self._connected = True
                self._channel = channel
                return
            except Exception as exc:
                last_error = exc
                _safe_close(sock)
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
                _send_all(self._sock, chunk)
            offset += len(chunk)
            if interval:
                time.sleep(interval)


def _scan_blocking(timeout: float) -> List[DeviceInfo]:
    return _get_adapter().scan_blocking(timeout)


def _safe_close(sock: Optional[SocketLike]) -> None:
    if not sock:
        return
    try:
        sock.close()
    except Exception:
        pass


def _send_all(sock: SocketLike, data: bytes) -> None:
    sendall = getattr(sock, "sendall", None)
    if callable(sendall):
        sendall(data)
        return
    send = getattr(sock, "send", None)
    if not callable(send):
        raise RuntimeError("Bluetooth socket does not support send")
    offset = 0
    while offset < len(data):
        sent = send(data[offset:])
        if not sent:
            raise RuntimeError("Bluetooth send failed")
        offset += sent


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


def _winrt_missing_message() -> str:
    return (
        "WinRT Bluetooth support on Windows requires the 'winsdk' package. "
        "Install with: pip install -r requirements.txt"
    )


def _winrt_imports():
    try:
        from winsdk.windows.devices.bluetooth.rfcomm import RfcommDeviceService, RfcommServiceId
        from winsdk.windows.devices.enumeration import DeviceInformation, DeviceInformationKind
        from winsdk.windows.networking.sockets import StreamSocket
        from winsdk.windows.storage.streams import DataWriter
    except Exception as exc:
        raise RuntimeError(_winrt_missing_message()) from exc
    return DeviceInformation, DeviceInformationKind, RfcommDeviceService, RfcommServiceId, StreamSocket, DataWriter


def _run_winrt(coro: Awaitable[T]) -> T:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            asyncio.set_event_loop(None)
        finally:
            loop.close()


def _format_bt_address(value: int) -> str:
    if not value:
        return ""
    text = f"{value:012X}"
    return ":".join(text[i : i + 2] for i in range(0, 12, 2))


async def _scan_winrt_async(timeout: float) -> ScanResult:
    DeviceInformation, DeviceInformationKind, RfcommDeviceService, RfcommServiceId, _, _ = _winrt_imports()
    selector = str(RfcommDeviceService.get_device_selector(RfcommServiceId.from_uuid(SPP_UUID)))

    async def find_all():
        try:
            return await DeviceInformation.find_all_async(selector)
        except TypeError:
            return await DeviceInformation.find_all_async(
                selector, [], DeviceInformationKind.ASSOCIATION_ENDPOINT
            )

    if timeout:
        infos = await asyncio.wait_for(find_all(), timeout=timeout)
    else:
        infos = await find_all()
    devices: List[DeviceInfo] = []
    mapping: Dict[str, str] = {}
    for info in infos:
        service = await RfcommDeviceService.from_id_async(info.id)
        if not service:
            continue
        device = service.device
        name = (device.name or info.name or "").strip()
        address = _format_bt_address(getattr(device, "bluetooth_address", 0))
        if not address:
            address = info.id
        if address not in mapping:
            mapping[address] = info.id
        devices.append(DeviceInfo(name=name, address=address))
    return _dedupe_devices(devices), mapping


def _scan_winrt(timeout: float) -> ScanResult:
    return _run_winrt(_scan_winrt_async(timeout))


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
    adapter = _get_adapter()
    channel = adapter.resolve_rfcomm_channel(address)
    if getattr(adapter, "single_channel", False):
        return [channel or RFCOMM_CHANNELS[0]]
    if channel is None:
        return list(RFCOMM_CHANNELS)
    channels = [channel]
    for candidate in RFCOMM_CHANNELS:
        if candidate != channel:
            channels.append(candidate)
    return channels


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

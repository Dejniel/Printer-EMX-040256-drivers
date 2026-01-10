from __future__ import annotations

import re
from typing import Iterable, List, Optional

from ..transport.bluetooth import DeviceInfo, SppBackend
from .models import PrinterModel, PrinterModelRegistry

_ADDRESS_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


class DeviceResolver:
    def __init__(self, registry: PrinterModelRegistry) -> None:
        self._registry = registry

    def filter_printer_devices(self, devices: Iterable[DeviceInfo]) -> List[DeviceInfo]:
        filtered = []
        for device in devices:
            if self._registry.detect_from_device_name(device.name or ""):
                filtered.append(device)
        return filtered

    async def resolve_printer_device(self, name_or_address: Optional[str]) -> DeviceInfo:
        devices = await SppBackend.scan()
        devices = self.filter_printer_devices(devices)
        if not devices:
            raise RuntimeError("No supported printers found")
        if name_or_address:
            device = self._select_device(devices, name_or_address)
            if not device:
                raise RuntimeError(f"No device matches '{name_or_address}'")
            return device
        return devices[0]

    def resolve_model(self, device_name: str, model_no: Optional[str] = None) -> PrinterModel:
        if model_no:
            model = self._registry.get(model_no)
            if not model:
                raise RuntimeError(f"Unknown printer model '{model_no}'")
            return model
        model = self._registry.detect_from_device_name(device_name)
        if model:
            return model
        raise RuntimeError("Printer model not detected from Bluetooth name")

    def require_model(self, model_no: Optional[str]) -> PrinterModel:
        if not model_no:
            raise RuntimeError("Serial printing requires --model (see --list-models)")
        model = self._registry.get(model_no)
        if not model:
            raise RuntimeError(f"Unknown printer model '{model_no}'")
        return model

    @staticmethod
    def _looks_like_address(value: str) -> bool:
        return bool(_ADDRESS_RE.match(value.strip()))

    def _select_device(self, devices: Iterable[DeviceInfo], name_or_address: str) -> Optional[DeviceInfo]:
        if self._looks_like_address(name_or_address):
            for device in devices:
                if device.address.lower() == name_or_address.lower():
                    return device
            return None
        target = name_or_address.lower()
        for device in devices:
            if (device.name or "").lower() == target:
                return device
        for device in devices:
            if target in (device.name or "").lower():
                return device
        return None

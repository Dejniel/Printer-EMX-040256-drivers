from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Optional

from .ble import SppBackend
from .models import PrinterModel, PrinterModelRegistry
from .print_job import PrintJobBuilder, PrintSettings

SERIAL_BAUD_RATE = 115200


def looks_like_address(value: str) -> bool:
    return ":" in value or "-" in value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TiMini Print: Bluetooth printing for TiMini-compatible thermal printers."
    )
    parser.add_argument("path", nargs="?", help="File to print (.png/.jpg/.pdf/.txt)")
    parser.add_argument("--bluetooth", help="Bluetooth name or address (default: first supported printer)")
    parser.add_argument("--serial", metavar="PATH", help="Serial port path to bypass Bluetooth (e.g. /dev/rfcomm0)")
    parser.add_argument("--scan", action="store_true", help="List nearby supported printers and exit")
    parser.add_argument("--list-models", action="store_true", help="List known printer models and exit")
    parser.epilog = "If any CLI options/arguments are provided, the GUI will not be launched."
    return parser.parse_args()


def list_models() -> int:
    registry = PrinterModelRegistry.load()
    for model in registry.models:
        print(model.model_no)
    return 0


def scan_devices() -> int:
    async def run() -> None:
        registry = PrinterModelRegistry.load()
        devices = await SppBackend.scan()
        devices = filter_printer_devices(registry, devices)
        for device in devices:
            name = device.name or ""
            if name:
                print(f"{name} ({device.address})")
            else:
                print(device.address)

    asyncio.run(run())
    return 0


def launch_gui() -> int:
    from .gui import TiMiniPrintGUI

    app = TiMiniPrintGUI()
    app.mainloop()
    return 0


def detect_model(registry: PrinterModelRegistry, device_name: str) -> PrinterModel:
    model = registry.detect_from_device_name(device_name)
    if model:
        return model
    raise RuntimeError("Printer model not detected from Bluetooth name")


def detect_model_from_hint(registry: PrinterModelRegistry, hint: Optional[str]) -> Optional[PrinterModel]:
    if not hint:
        return None
    return registry.detect_from_device_name(hint)


def select_device(devices, name_or_address: str):
    if looks_like_address(name_or_address):
        for device in devices:
            if device.address.lower() == name_or_address.lower():
                return device
        return None
    for device in devices:
        if (device.name or "").lower() == name_or_address.lower():
            return device
    for device in devices:
        if name_or_address.lower() in (device.name or "").lower():
            return device
    return None


def filter_printer_devices(registry: PrinterModelRegistry, devices):
    filtered = []
    for device in devices:
        if registry.detect_from_device_name(device.name or ""):
            filtered.append(device)
    return filtered


async def resolve_printer_device(registry: PrinterModelRegistry, name_or_address: Optional[str]):
    devices = await SppBackend.scan()
    devices = filter_printer_devices(registry, devices)
    if not devices:
        raise RuntimeError("No supported printers found")
    if name_or_address:
        device = select_device(devices, name_or_address)
        if not device:
            raise RuntimeError(f"No device matches '{name_or_address}'")
        return device
    return devices[0]


def build_print_data(model: PrinterModel, path: str) -> bytes:
    settings = PrintSettings()
    builder = PrintJobBuilder(model, settings)
    return builder.build_from_file(path)


def write_serial_blocking(port: str, data: bytes, chunk_size: int, interval_ms: int) -> None:
    try:
        import serial
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pyserial is required. Install with: pip install -r requirements.txt") from exc
    interval = max(0.0, interval_ms / 1000.0)
    try:
        with serial.Serial(port, SERIAL_BAUD_RATE, timeout=1, write_timeout=5) as ser:
            offset = 0
            while offset < len(data):
                chunk = data[offset : offset + chunk_size]
                ser.write(chunk)
                offset += len(chunk)
                if interval:
                    time.sleep(interval)
            ser.flush()
    except Exception as exc:
        raise RuntimeError(f"Serial connection failed: {exc}") from exc


async def write_serial(port: str, data: bytes, chunk_size: int, interval_ms: int) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, write_serial_blocking, port, data, chunk_size, interval_ms)


def print_bluetooth(args: argparse.Namespace) -> int:
    registry = PrinterModelRegistry.load()

    async def run() -> None:
        device = await resolve_printer_device(registry, args.bluetooth)
        model = detect_model(registry, device.name or "")
        data = build_print_data(model, args.path)
        backend = SppBackend()
        await backend.connect(device.address)
        await backend.write(data, model.img_mtu or 180, model.interval_ms or 4)
        await backend.disconnect()

    asyncio.run(run())
    return 0


def print_serial(args: argparse.Namespace) -> int:
    registry = PrinterModelRegistry.load()

    async def run() -> None:
        model = detect_model_from_hint(registry, args.bluetooth)
        if not model:
            model = detect_model_from_hint(registry, os.path.basename(args.serial or ""))
        if not model:
            device = await resolve_printer_device(registry, args.bluetooth)
            model = detect_model(registry, device.name or "")
        data = build_print_data(model, args.path)
        await write_serial(args.serial, data, model.img_mtu or 180, model.interval_ms or 4)

    asyncio.run(run())
    return 0


def main() -> int:
    if len(sys.argv) == 1:
        return launch_gui()
    args = parse_args()
    if args.list_models:
        return list_models()
    if args.scan:
        return scan_devices()
    if not args.path:
        print("Missing file path. Use --help for usage.", file=sys.stderr)
        return 2
    try:
        if args.serial:
            return print_serial(args)
        return print_bluetooth(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

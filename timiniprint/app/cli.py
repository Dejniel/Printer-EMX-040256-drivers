from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from typing import Optional

from ..devices import DeviceResolver, PrinterModel, PrinterModelRegistry
from ..transport.bluetooth import SppBackend
from ..transport.serial import SerialTransport
from .diagnostics import emit_startup_warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TiMini Print: Bluetooth printing for TiMini-compatible thermal printers."
    )
    parser.add_argument("path", nargs="?", help="File to print (.png/.jpg/.pdf/.txt)")
    parser.add_argument("--bluetooth", help="Bluetooth name or address (default: first supported printer)")
    parser.add_argument("--serial", metavar="PATH", help="Serial port path to bypass Bluetooth (e.g. /dev/rfcomm0)")
    parser.add_argument("--model", help="Printer model number (required for --serial)")
    parser.add_argument("--scan", action="store_true", help="List nearby supported printers and exit")
    parser.add_argument("--list-models", action="store_true", help="List known printer models and exit")
    parser.add_argument("--text", metavar="TEXT", help="Print raw text instead of a file path")
    parser.add_argument("--darkness", type=int, choices=range(1, 6), help="Print darkness (1-5)")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--force-text-mode", action="store_true", help="Force printer protocol text mode")
    mode_group.add_argument("--force-image-mode", action="store_true", help="Force printer protocol image mode")
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
        resolver = DeviceResolver(registry)
        devices = await SppBackend.scan()
        devices = resolver.filter_printer_devices(devices)
        for device in devices:
            name = device.name or ""
            status = " [unpaired]" if device.paired is False else ""
            if name:
                print(f"{name} ({device.address}){status}")
            else:
                print(f"{device.address}{status}")

    asyncio.run(run())
    return 0


def launch_gui() -> int:
    from .gui import TiMiniPrintGUI

    app = TiMiniPrintGUI()
    app.mainloop()
    return 0


def build_print_data(
    model: PrinterModel,
    path: Optional[str],
    text_mode: Optional[bool] = None,
    blackening: Optional[int] = None,
    text_input: Optional[str] = None,
) -> bytes:
    from ..printing import PrintJobBuilder, PrintSettings

    settings = PrintSettings(text_mode=text_mode)
    if blackening is not None:
        settings.blackening = blackening
    builder = PrintJobBuilder(model, settings)
    if text_input is None:
        if not path:
            raise RuntimeError("Missing file path")
        return builder.build_from_file(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
            handle.write(text_input)
            temp_path = handle.name
        return builder.build_from_file(temp_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _resolve_text_mode(args: argparse.Namespace) -> Optional[bool]:
    if args.force_text_mode:
        return True
    if args.force_image_mode:
        return False
    return None


def _resolve_blackening(args: argparse.Namespace) -> Optional[int]:
    return args.darkness


def _resolve_text_input(args: argparse.Namespace) -> Optional[str]:
    if args.text is None:
        return None
    return args.text


def print_bluetooth(args: argparse.Namespace) -> int:
    registry = PrinterModelRegistry.load()
    resolver = DeviceResolver(registry)

    async def run() -> None:
        device = await resolver.resolve_printer_device(args.bluetooth)
        model = resolver.resolve_model(device.name or "", args.model)
        data = build_print_data(
            model,
            args.path,
            _resolve_text_mode(args),
            _resolve_blackening(args),
            _resolve_text_input(args),
        )
        backend = SppBackend()
        await backend.connect(device.address)
        await backend.write(data, model.img_mtu or 180, model.interval_ms or 4)
        await backend.disconnect()

    asyncio.run(run())
    return 0


def print_serial(args: argparse.Namespace) -> int:
    registry = PrinterModelRegistry.load()
    resolver = DeviceResolver(registry)
    model = resolver.require_model(args.model)
    data = build_print_data(
        model,
        args.path,
        _resolve_text_mode(args),
        _resolve_blackening(args),
        _resolve_text_input(args),
    )

    async def run() -> None:
        transport = SerialTransport(args.serial)
        await transport.write(data, model.img_mtu or 180, model.interval_ms or 4)

    asyncio.run(run())
    return 0


def main() -> int:
    emit_startup_warnings()
    if len(sys.argv) == 1:
        return launch_gui()
    args = parse_args()
    if args.list_models:
        return list_models()
    if args.scan:
        return scan_devices()
    if args.path and args.text is not None:
        print("Provide either a file path or --text, not both. Use --help for usage.", file=sys.stderr)
        return 2
    if not args.path and args.text is None:
        print("Missing file path or --text. Use --help for usage.", file=sys.stderr)
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

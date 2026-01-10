from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from ..devices import DeviceResolver, PrinterModelRegistry
from ..printing import PrintJobBuilder, PrintSettings
from ..transport.bluetooth import SppBackend


class BleLoop:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro, callback=None):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if callback:
            future.add_done_callback(callback)
        return future


class TiMiniPrintGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TiMini Print")
        self.geometry("800x400")
        self.resizable(False, False)

        self.registry = PrinterModelRegistry.load()
        self.resolver = DeviceResolver(self.registry)
        self.backend = SppBackend()
        self.ble_loop = BleLoop()
        self.queue: queue.Queue = queue.Queue()

        self.devices = []
        self.device_map = {}

        self.device_var = tk.StringVar()
        self.model_var = tk.StringVar(value="")
        self.file_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.connected_model = None

        self._build_ui()
        self._set_connected_state(False)
        self.after(100, self._process_queue)
        self.after(200, self.scan)

    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 6}

        device_frame = ttk.LabelFrame(self, text="Bluetooth")
        device_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(device_frame, text="Device:").grid(row=0, column=0, sticky="w", **padding)
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=48, state="readonly")
        self.device_combo.grid(row=0, column=1, sticky="w", **padding)

        self.refresh_button = ttk.Button(device_frame, text="Refresh", command=self.scan)
        self.refresh_button.grid(row=0, column=2, **padding)
        self.connect_button = ttk.Button(device_frame, text="Connect", command=self.connect)
        self.connect_button.grid(row=1, column=1, sticky="w", **padding)
        self.disconnect_button = ttk.Button(device_frame, text="Disconnect", command=self.disconnect)
        self.disconnect_button.grid(row=1, column=2, **padding)

        model_frame = ttk.LabelFrame(self, text="Printer Model")
        model_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(model_frame, text="Model:").grid(row=0, column=0, sticky="w", **padding)
        self.model_label = ttk.Label(model_frame, textvariable=self.model_var, width=48)
        self.model_label.grid(row=0, column=1, sticky="w", **padding)

        file_frame = ttk.LabelFrame(self, text="File")
        file_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(file_frame, text="Path:").grid(row=0, column=0, sticky="w", **padding)
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=48)
        self.file_entry.grid(row=0, column=1, sticky="w", **padding)
        self.browse_button = ttk.Button(file_frame, text="Browse", command=self.browse)
        self.browse_button.grid(row=0, column=2, **padding)

        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=10, pady=10)
        self.print_button = ttk.Button(action_frame, text="Print", command=self.print_file)
        self.print_button.pack(side="right")

        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=10, pady=10)
        ttk.Label(status_frame, text="Status:").pack(side="left")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left", padx=6)

    def _process_queue(self) -> None:
        while True:
            try:
                action, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if action == "status":
                self.status_var.set(payload)
            elif action == "devices":
                self.devices = payload
                self.device_map = {self._device_label(d): d for d in payload}
                values = list(self.device_map.keys())
                self.device_combo["values"] = values
                current = self.device_var.get()
                if values:
                    if current in self.device_map:
                        self.device_var.set(current)
                    elif not self.connected_model:
                        self.device_var.set(values[0])
                else:
                    self.device_var.set("")
            elif action == "connected":
                self._set_connected_state(True, payload)
            elif action == "disconnected":
                self._set_connected_state(False)
            elif action == "error":
                self.status_var.set(f"Error: {payload}")
        self.after(100, self._process_queue)

    def _device_label(self, device) -> str:
        name = device.name or ""
        if name:
            return f"{name} ({device.address})"
        return device.address

    def _queue_status(self, message: str) -> None:
        self.queue.put(("status", message))

    def _queue_error(self, message: str) -> None:
        self.queue.put(("error", message))

    def scan(self) -> None:
        self._queue_status("Refreshing devices...")

        def done(fut):
            try:
                devices = fut.result()
                filtered = self.resolver.filter_printer_devices(devices)
                self.queue.put(("devices", filtered))
                self._queue_status(f"Found {len(filtered)} devices")
            except Exception as exc:
                self._queue_error(str(exc))

        self.ble_loop.submit(self.backend.scan(), callback=done)

    def connect(self) -> None:
        label = self.device_var.get()
        device = self.device_map.get(label)
        if not device:
            self._queue_error("Select a Bluetooth device")
            return
        self._queue_status("Connecting...")

        def done(fut):
            try:
                fut.result()
                self._queue_status("Connected")
                self.queue.put(("connected", device))
                self.device_var.set(self._device_label(device))
            except Exception as exc:
                self._queue_error(str(exc))

        self.ble_loop.submit(self.backend.connect(device.address), callback=done)

    def disconnect(self) -> None:
        self._queue_status("Disconnecting...")

        def done(fut):
            try:
                fut.result()
                self._queue_status("Disconnected")
                self.queue.put(("disconnected", None))
            except Exception as exc:
                self._queue_error(str(exc))

        self.ble_loop.submit(self.backend.disconnect(), callback=done)

    def browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select file",
            filetypes=[
                ("Supported", "*.png *.jpg *.jpeg *.gif *.bmp *.pdf *.txt"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.file_var.set(path)

    def print_file(self) -> None:
        label = self.device_var.get()
        device = self.device_map.get(label)
        if not device:
            self._queue_error("Select a Bluetooth device")
            return
        path = self.file_var.get().strip()
        if not path:
            self._queue_error("Select a file to print")
            return
        model = self.connected_model
        if not model:
            self._queue_error("Printer model not detected")
            return
        settings = PrintSettings()
        builder = PrintJobBuilder(model, settings)

        def done(fut):
            try:
                fut.result()
                self._queue_status("Print job sent")
            except Exception as exc:
                self._queue_error(str(exc))

        async def run() -> None:
            if not self.backend.is_connected():
                await self.backend.connect(device.address)
            data = builder.build_from_file(path)
            await self.backend.write(data, model.img_mtu or 180, model.interval_ms or 4)

        self._queue_status("Printing...")
        self.ble_loop.submit(run(), callback=done)

    def _set_connected_state(self, connected: bool, device=None) -> None:
        self.connected_model = None
        if connected and device:
            try:
                model = self.resolver.resolve_model(device.name or "")
            except Exception as exc:
                self._queue_error(str(exc))
                self.ble_loop.submit(self.backend.disconnect())
                self._set_connected_state(False)
                return
            self.connected_model = model
            self.model_var.set(model.model_no)
            self._set_device_combo_state(False)
            self._set_widget_state(self.refresh_button, False)
            self._set_widget_state(self.file_entry, True)
            self._set_widget_state(self.browse_button, True)
            self._set_widget_state(self.print_button, True)
            self._set_widget_state(self.connect_button, False)
            self._set_widget_state(self.disconnect_button, True)
            return

        self.model_var.set("")
        self._set_device_combo_state(True)
        self._set_widget_state(self.refresh_button, True)
        self._set_widget_state(self.file_entry, False)
        self._set_widget_state(self.browse_button, False)
        self._set_widget_state(self.print_button, False)
        self._set_widget_state(self.connect_button, True)
        self._set_widget_state(self.disconnect_button, False)

    @staticmethod
    def _set_widget_state(widget, enabled: bool) -> None:
        if enabled:
            widget.state(["!disabled"])
        else:
            widget.state(["disabled"])

    def _set_device_combo_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        self.device_combo.configure(state=state)

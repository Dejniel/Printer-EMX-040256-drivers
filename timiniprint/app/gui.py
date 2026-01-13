from __future__ import annotations

import asyncio
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from .diagnostics import emit_startup_warnings
from ..devices import DeviceResolver, PrinterModelRegistry
from ..rendering.converters.text import TextConverter
from ..transport.bluetooth import DeviceInfo, SppBackend

PAPER_MOTION_INTERVAL_MS = 1000


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
        emit_startup_warnings()
        self.title("TiMini Print")
        self.geometry("800x380")
        self.resizable(True, True)

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
        self.text_mode_var = tk.BooleanVar(value=False)
        self.darkness_var = tk.IntVar(value=3)
        self.text_font_var = tk.StringVar()
        self.text_columns_var = tk.IntVar(value=35)
        self.status_var = tk.StringVar(value="Idle")
        self.connected_model = None
        self._connecting = False
        self._paper_motion_action = None
        self._paper_motion_job = None
        self._paper_motion_busy = False
        self.file_var.trace_add("write", self._on_file_path_change)

        self._build_ui()
        self.update_idletasks()
        self.minsize(int(self.winfo_reqwidth()*.75),self.winfo_reqheight())
        self._set_connected_state(False)
        self.after(100, self._process_queue)
        self.after(200, self.scan)

    def _build_ui(self) -> None:
        padding = {"padx": 10, "pady": 6}

        device_frame = ttk.LabelFrame(self, text="Bluetooth")
        device_frame.pack(fill="x", padx=10, pady=10)
        device_frame.columnconfigure(1, weight=1)

        ttk.Label(device_frame, text="Device:").grid(row=0, column=0, sticky="w", **padding)
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, width=48, state="readonly")
        self.device_combo.grid(row=0, column=1, sticky="ew", **padding)

        self.refresh_button = ttk.Button(device_frame, text="Refresh", command=self.scan)
        self.refresh_button.grid(row=0, column=2, **padding)
        self.connect_button = ttk.Button(device_frame, text="Connect", command=self.connect)
        self.connect_button.grid(row=1, column=1, sticky="w", **padding)
        self.disconnect_button = ttk.Button(device_frame, text="Disconnect", command=self.disconnect)
        self.disconnect_button.grid(row=1, column=2, **padding)

        model_frame = ttk.LabelFrame(self, text="Printer Model")
        model_frame.pack(fill="x", padx=10, pady=10)
        model_frame.columnconfigure(1, weight=1)

        ttk.Label(model_frame, text="Model:").grid(row=0, column=0, sticky="w", **padding)
        self.model_label = ttk.Label(model_frame, textvariable=self.model_var, width=48)
        self.model_label.grid(row=0, column=1, sticky="ew", **padding)

        file_frame = ttk.LabelFrame(self, text="File")
        file_frame.pack(fill="x", padx=10, pady=10)
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Path:").grid(row=0, column=0, sticky="w", **padding)
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=48)
        self.file_entry.grid(row=0, column=1, sticky="ew", **padding)
        self.browse_button = ttk.Button(file_frame, text="Browse", command=self.browse)
        self.browse_button.grid(row=0, column=2, **padding)

        options_frame = ttk.LabelFrame(self, text="Options")
        options_frame.pack(fill="x", padx=10, pady=10)
        self.text_mode_check = ttk.Checkbutton(
            options_frame,
            text="Firmware text mode",
            variable=self.text_mode_var,
        )
        self.text_mode_check.grid(row=0, column=0, sticky="w", **padding)
        ttk.Label(options_frame, text="Darkness:").grid(row=0, column=1, sticky="w", **padding)
        self.darkness_scale = tk.Scale(
            options_frame,
            from_=1,
            to=5,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            length=120,
            variable=self.darkness_var,
        )
        self.darkness_scale.grid(row=0, column=2, sticky="w", **padding)
        self.darkness_value_label = ttk.Label(options_frame, textvariable=self.darkness_var, width=2)
        self.darkness_value_label.grid(row=0, column=3, sticky="w", **padding)
        options_frame.columnconfigure(4, weight=1)

        text_frame = ttk.LabelFrame(self, text="Txt Options")
        text_frame.pack(fill="x", padx=10, pady=10)
        text_frame.columnconfigure(1, weight=1)
        ttk.Label(text_frame, text="Font:").grid(row=0, column=0, sticky="w", **padding)
        self.text_font_entry = ttk.Entry(text_frame, textvariable=self.text_font_var, width=48)
        self.text_font_entry.grid(row=0, column=1, sticky="ew", **padding)
        self.text_font_browse = ttk.Button(text_frame, text="Browse", command=self.browse_text_font)
        self.text_font_browse.grid(row=0, column=2, **padding)
        self.text_font_clear = ttk.Button(text_frame, text="Default", command=self.clear_text_font)
        self.text_font_clear.grid(row=0, column=3, **padding)
        ttk.Label(text_frame, text="Letters per line:").grid(row=1, column=0, sticky="w", **padding)
        self.text_columns_scale = tk.Scale(
            text_frame,
            from_=30,
            to=40,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            length=160,
            variable=self.text_columns_var,
        )
        self.text_columns_scale.grid(row=1, column=1, sticky="w", **padding)
        self.text_columns_value_label = ttk.Label(text_frame, textvariable=self.text_columns_var, width=4)
        self.text_columns_value_label.grid(row=1, column=2, sticky="w", **padding)

        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=10, pady=10)
        self.print_button = ttk.Button(action_frame, text="Print", command=self.print_file)
        self.retract_button = ttk.Button(action_frame, text="Retract")
        self.feed_button = ttk.Button(action_frame, text="Feed")
        self.feed_button.pack(side="left")
        self.retract_button.pack(side="left", padx=(6, 0))
        self.print_button.pack(side="right")
        self.feed_button.bind("<ButtonPress-1>", lambda event: self._start_paper_motion("feed"))
        self.feed_button.bind("<ButtonRelease-1>", self._stop_paper_motion)
        self.feed_button.bind("<Leave>", self._stop_paper_motion)
        self.retract_button.bind("<ButtonPress-1>", lambda event: self._start_paper_motion("retract"))
        self.retract_button.bind("<ButtonRelease-1>", self._stop_paper_motion)
        self.retract_button.bind("<Leave>", self._stop_paper_motion)

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
                device = payload
                if device:
                    device = self._mark_device_paired(device)
                self._set_connected_state(True, device)
            elif action == "disconnected":
                self._set_connected_state(False)
            elif action == "error":
                self.status_var.set(f"Error: {payload}")
            elif action == "connecting":
                self._set_connecting_state(bool(payload))
        self.after(100, self._process_queue)

    def _device_label(self, device) -> str:
        name = device.name or ""
        status = " [unpaired]" if device.paired is False else ""
        if name:
            return f"{name} ({device.address}){status}"
        return f"{device.address}{status}"

    def _mark_device_paired(self, device: DeviceInfo) -> DeviceInfo:
        updated_devices = []
        updated = DeviceInfo(name=device.name or "", address=device.address, paired=True)
        found = False
        for item in self.devices:
            if item.address == device.address:
                name = item.name or updated.name
                updated = DeviceInfo(name=name, address=item.address, paired=True)
                updated_devices.append(updated)
                found = True
            else:
                updated_devices.append(item)
        if not found:
            updated_devices.append(updated)
        self.devices = updated_devices
        self.device_map = {self._device_label(d): d for d in updated_devices}
        values = list(self.device_map.keys())
        self.device_combo["values"] = values
        self.device_var.set(self._device_label(updated))
        return updated

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
        self.queue.put(("connecting", True))

        def done(fut):
            try:
                fut.result()
                self._queue_status("Connected")
                self.queue.put(("connected", device))
            except Exception as exc:
                self._queue_error(str(exc))
                self.queue.put(("connecting", False))

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

    def browse_text_font(self) -> None:
        path = filedialog.askopenfilename(
            title="Select font",
            filetypes=[
                ("Fonts", "*.ttf *.otf *.ttc"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.text_font_var.set(path)

    def clear_text_font(self) -> None:
        self.text_font_var.set("")

    def _on_file_path_change(self, *_args) -> None:
        self._set_text_mode_for_path(self.file_var.get())

    def _set_text_mode_for_path(self, path: str) -> None:
        path = path.strip()
        if not path:
            self.text_mode_var.set(False)
            return
        ext = os.path.splitext(path)[1].lower()
        self.text_mode_var.set(ext == ".txt")

    def print_file(self) -> None:
        from ..printing import PrintJobBuilder, PrintSettings

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
        settings = PrintSettings(
            text_mode=self.text_mode_var.get(),
            blackening=self.darkness_var.get(),
            text_font=self.text_font_var.get().strip() or None,
            text_columns=self.text_columns_var.get(),
        )
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

    def _start_paper_motion(self, action: str) -> None:
        if action not in {"feed", "retract"}:
            return
        self._stop_paper_motion()
        self._paper_motion_action = action
        self._send_paper_motion(action)
        self._schedule_paper_motion()

    def _schedule_paper_motion(self) -> None:
        if not self._paper_motion_action:
            return
        self._paper_motion_job = self.after(PAPER_MOTION_INTERVAL_MS, self._paper_motion_tick)

    def _paper_motion_tick(self) -> None:
        if not self._paper_motion_action:
            return
        self._send_paper_motion(self._paper_motion_action)
        self._schedule_paper_motion()

    def _stop_paper_motion(self, *_args) -> None:
        self._paper_motion_action = None
        if self._paper_motion_job is not None:
            self.after_cancel(self._paper_motion_job)
            self._paper_motion_job = None

    def _send_paper_motion(self, action: str) -> None:
        if self._paper_motion_busy:
            return
        label = self.device_var.get()
        device = self.device_map.get(label)
        if not device:
            self._queue_error("Select a Bluetooth device")
            self._stop_paper_motion()
            return
        model = self.connected_model
        if not model:
            self._queue_error("Printer model not detected")
            self._stop_paper_motion()
            return

        from ..protocol import advance_paper_cmd, retract_paper_cmd

        if action == "feed":
            data = advance_paper_cmd(model.dev_dpi, model.new_format)
        else:
            data = retract_paper_cmd(model.dev_dpi, model.new_format)
        self._paper_motion_busy = True

        async def run() -> None:
            if not self.backend.is_connected():
                await self.backend.connect(device.address)
            await self.backend.write(data, model.img_mtu or 180, model.interval_ms or 4)

        def done(fut):
            self._paper_motion_busy = False
            try:
                fut.result()
            except Exception as exc:
                self._queue_error(str(exc))
                self._stop_paper_motion()

        self.ble_loop.submit(run(), callback=done)

    def _set_connected_state(self, connected: bool, device=None) -> None:
        self._connecting = False
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
            self._set_widget_state(self.text_mode_check, True)
            self._set_widget_state(self.darkness_scale, True)
            self._set_widget_state(self.darkness_value_label, True)
            self._set_widget_state(self.text_font_entry, True)
            self._set_widget_state(self.text_font_browse, True)
            self._set_widget_state(self.text_font_clear, True)
            self._set_widget_state(self.text_columns_scale, True)
            self._set_widget_state(self.text_columns_value_label, True)
            self._set_widget_state(self.feed_button, True)
            self._set_widget_state(self.retract_button, True)
            self._set_widget_state(self.print_button, True)
            self._set_widget_state(self.connect_button, False)
            self._set_widget_state(self.disconnect_button, True)
            self._configure_text_columns(model)
            return

        self.model_var.set("")
        self._set_device_combo_state(True)
        self._set_widget_state(self.refresh_button, True)
        self._set_widget_state(self.file_entry, False)
        self._set_widget_state(self.browse_button, False)
        self._set_widget_state(self.text_mode_check, False)
        self._set_widget_state(self.darkness_scale, False)
        self._set_widget_state(self.darkness_value_label, False)
        self._set_widget_state(self.text_font_entry, False)
        self._set_widget_state(self.text_font_browse, False)
        self._set_widget_state(self.text_font_clear, False)
        self._set_widget_state(self.text_columns_scale, False)
        self._set_widget_state(self.text_columns_value_label, False)
        self._set_widget_state(self.feed_button, False)
        self._set_widget_state(self.retract_button, False)
        self._set_widget_state(self.print_button, False)
        self._set_widget_state(self.connect_button, True)
        self._set_widget_state(self.disconnect_button, False)
        self._stop_paper_motion()

    def _configure_text_columns(self, model) -> None:
        width = self._normalized_width(model.width)
        default_columns = TextConverter.default_columns_for_width(width)
        min_columns = max(5, int(round(default_columns * 0.5)))
        max_columns = max(min_columns + 1, int(round(default_columns * 1.5)))
        self.text_columns_scale.configure(from_=min_columns, to=max_columns)
        self.text_columns_var.set(default_columns)

    @staticmethod
    def _normalized_width(width: int) -> int:
        if width % 8 == 0:
            return width
        return width - (width % 8)

    def _set_connecting_state(self, connecting: bool) -> None:
        self._connecting = connecting
        if connecting:
            self._set_device_combo_state(False)
            self._set_widget_state(self.refresh_button, False)
            self._set_widget_state(self.connect_button, False)
            self._set_widget_state(self.disconnect_button, False)
            return
        if self.connected_model:
            return
        self._set_device_combo_state(True)
        self._set_widget_state(self.refresh_button, True)
        self._set_widget_state(self.connect_button, True)
        self._set_widget_state(self.disconnect_button, False)

    @staticmethod
    def _set_widget_state(widget, enabled: bool) -> None:
        if isinstance(widget, ttk.Widget):
            if enabled:
                widget.state(["!disabled"])
            else:
                widget.state(["disabled"])
            return
        state = "normal" if enabled else "disabled"
        widget.configure(state=state)

    def _set_device_combo_state(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        self.device_combo.configure(state=state)

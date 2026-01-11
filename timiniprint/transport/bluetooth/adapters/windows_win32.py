from __future__ import annotations

from typing import List

from ..types import DeviceInfo


def scan_inquiry(timeout: float) -> List[DeviceInfo]:
    import ctypes
    from ctypes import wintypes

    BLUETOOTH_MAX_NAME_SIZE = 248

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [
            ("wYear", wintypes.WORD),
            ("wMonth", wintypes.WORD),
            ("wDayOfWeek", wintypes.WORD),
            ("wDay", wintypes.WORD),
            ("wHour", wintypes.WORD),
            ("wMinute", wintypes.WORD),
            ("wSecond", wintypes.WORD),
            ("wMilliseconds", wintypes.WORD),
        ]

    class BLUETOOTH_ADDRESS(ctypes.Structure):
        _fields_ = [("ullLong", ctypes.c_ulonglong)]

    class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("Address", BLUETOOTH_ADDRESS),
            ("ulClassofDevice", wintypes.ULONG),
            ("fConnected", wintypes.BOOL),
            ("fRemembered", wintypes.BOOL),
            ("fAuthenticated", wintypes.BOOL),
            ("stLastSeen", SYSTEMTIME),
            ("stLastUsed", SYSTEMTIME),
            ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
        ]

    class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("fReturnAuthenticated", wintypes.BOOL),
            ("fReturnRemembered", wintypes.BOOL),
            ("fReturnUnknown", wintypes.BOOL),
            ("fReturnConnected", wintypes.BOOL),
            ("fIssueInquiry", wintypes.BOOL),
            ("cTimeoutMultiplier", ctypes.c_ubyte),
            ("hRadio", wintypes.HANDLE),
        ]

    class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD)]

    try:
        bt = ctypes.WinDLL("bluetoothapis.dll")
        k32 = ctypes.WinDLL("kernel32.dll")

        bt.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS), ctypes.POINTER(wintypes.HANDLE)]
        bt.BluetoothFindFirstRadio.restype = wintypes.HANDLE
        bt.BluetoothFindNextRadio.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)]
        bt.BluetoothFindNextRadio.restype = wintypes.BOOL
        bt.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
        bt.BluetoothFindRadioClose.restype = wintypes.BOOL

        bt.BluetoothFindFirstDevice.argtypes = [ctypes.POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS), ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
        bt.BluetoothFindFirstDevice.restype = wintypes.HANDLE
        bt.BluetoothFindNextDevice.argtypes = [wintypes.HANDLE, ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
        bt.BluetoothFindNextDevice.restype = wintypes.BOOL
        bt.BluetoothFindDeviceClose.argtypes = [wintypes.HANDLE]
        bt.BluetoothFindDeviceClose.restype = wintypes.BOOL
    except Exception:
        return []

    rp = BLUETOOTH_FIND_RADIO_PARAMS()
    rp.dwSize = ctypes.sizeof(rp)
    h_radio = wintypes.HANDLE()
    h_find_radio = bt.BluetoothFindFirstRadio(ctypes.byref(rp), ctypes.byref(h_radio))
    if not h_find_radio:
        return []
    radios = [h_radio.value]
    while True:
        h_next = wintypes.HANDLE()
        if not bt.BluetoothFindNextRadio(h_find_radio, ctypes.byref(h_next)):
            break
        radios.append(h_next.value)
    bt.BluetoothFindRadioClose(h_find_radio)

    timeout_multiplier = int(round(timeout / 1.28))
    if timeout_multiplier < 1:
        timeout_multiplier = 1
    if timeout_multiplier > 48:
        timeout_multiplier = 48

    seen = {}
    for h_val in radios:
        params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
        params.dwSize = ctypes.sizeof(params)
        params.fReturnAuthenticated = True
        params.fReturnRemembered = True
        params.fReturnUnknown = True
        params.fReturnConnected = True
        params.fIssueInquiry = True
        params.cTimeoutMultiplier = timeout_multiplier
        params.hRadio = wintypes.HANDLE(h_val)

        info = BLUETOOTH_DEVICE_INFO()
        info.dwSize = ctypes.sizeof(info)
        h_find = bt.BluetoothFindFirstDevice(ctypes.byref(params), ctypes.byref(info))
        if h_find:
            while True:
                raw_name = info.szName
                name = raw_name.rstrip("\x00") if isinstance(raw_name, str) else str(raw_name)
                addr_bytes = int(info.Address.ullLong).to_bytes(8, "little")[:6]
                address = ":".join(f"{b:02X}" for b in addr_bytes[::-1])
                paired = bool(info.fAuthenticated or info.fRemembered)
                if address not in seen:
                    seen[address] = DeviceInfo(name=name, address=address, paired=paired)
                if not bt.BluetoothFindNextDevice(h_find, ctypes.byref(info)):
                    break
            bt.BluetoothFindDeviceClose(h_find)
        k32.CloseHandle(wintypes.HANDLE(h_val))
    return list(seen.values())


def pair_device(address: str) -> bool:
    import ctypes
    from ctypes import wintypes

    cleaned = address.replace(":", "").replace("-", "")
    if len(cleaned) != 12:
        return False
    try:
        addr_value = int(cleaned, 16)
    except ValueError:
        return False

    BLUETOOTH_MAX_NAME_SIZE = 248

    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [
            ("wYear", wintypes.WORD),
            ("wMonth", wintypes.WORD),
            ("wDayOfWeek", wintypes.WORD),
            ("wDay", wintypes.WORD),
            ("wHour", wintypes.WORD),
            ("wMinute", wintypes.WORD),
            ("wSecond", wintypes.WORD),
            ("wMilliseconds", wintypes.WORD),
        ]

    class BLUETOOTH_ADDRESS(ctypes.Structure):
        _fields_ = [("ullLong", ctypes.c_ulonglong)]

    class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("Address", BLUETOOTH_ADDRESS),
            ("ulClassofDevice", wintypes.ULONG),
            ("fConnected", wintypes.BOOL),
            ("fRemembered", wintypes.BOOL),
            ("fAuthenticated", wintypes.BOOL),
            ("stLastSeen", SYSTEMTIME),
            ("stLastUsed", SYSTEMTIME),
            ("szName", wintypes.WCHAR * BLUETOOTH_MAX_NAME_SIZE),
        ]

    class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD)]

    try:
        bt = ctypes.WinDLL("bluetoothapis.dll")
        k32 = ctypes.WinDLL("kernel32.dll")
    except Exception:
        return False

    try:
        bt.BluetoothFindFirstRadio.argtypes = [ctypes.POINTER(BLUETOOTH_FIND_RADIO_PARAMS), ctypes.POINTER(wintypes.HANDLE)]
        bt.BluetoothFindFirstRadio.restype = wintypes.HANDLE
        bt.BluetoothFindNextRadio.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HANDLE)]
        bt.BluetoothFindNextRadio.restype = wintypes.BOOL
        bt.BluetoothFindRadioClose.argtypes = [wintypes.HANDLE]
        bt.BluetoothFindRadioClose.restype = wintypes.BOOL

        bt.BluetoothGetDeviceInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(BLUETOOTH_DEVICE_INFO)]
        bt.BluetoothGetDeviceInfo.restype = wintypes.DWORD
    except Exception:
        return False

    try:
        auth_lib = ctypes.WinDLL("bthprops.cpl")
    except Exception:
        auth_lib = None

    def _get_auth_func(lib, name: str, stdcall_bytes: int):
        if not lib:
            return None
        func = getattr(lib, name, None)
        if func:
            return func
        decorated = f"{name}@{stdcall_bytes}"
        return getattr(lib, decorated, None)

    auth_ex = _get_auth_func(auth_lib, "BluetoothAuthenticateDeviceEx", 20) or _get_auth_func(
        bt, "BluetoothAuthenticateDeviceEx", 20
    )
    auth_legacy = _get_auth_func(auth_lib, "BluetoothAuthenticateDevice", 20) or _get_auth_func(
        bt, "BluetoothAuthenticateDevice", 20
    )
    if auth_ex:
        auth_ex.argtypes = [
            wintypes.HWND,
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
            ctypes.c_void_p,
            wintypes.ULONG,
        ]
        auth_ex.restype = wintypes.DWORD
    if auth_legacy:
        auth_legacy.argtypes = [
            wintypes.HWND,
            wintypes.HANDLE,
            ctypes.POINTER(BLUETOOTH_DEVICE_INFO),
            wintypes.LPWSTR,
            wintypes.ULONG,
        ]
        auth_legacy.restype = wintypes.DWORD
    if not auth_ex and not auth_legacy:
        return False

    rp = BLUETOOTH_FIND_RADIO_PARAMS()
    rp.dwSize = ctypes.sizeof(rp)
    h_radio = wintypes.HANDLE()
    h_find_radio = bt.BluetoothFindFirstRadio(ctypes.byref(rp), ctypes.byref(h_radio))
    if not h_find_radio:
        return False
    radios = [h_radio.value]
    while True:
        h_next = wintypes.HANDLE()
        if not bt.BluetoothFindNextRadio(h_find_radio, ctypes.byref(h_next)):
            break
        radios.append(h_next.value)
    bt.BluetoothFindRadioClose(h_find_radio)

    try:
        for h_val in radios:
            info = BLUETOOTH_DEVICE_INFO()
            info.dwSize = ctypes.sizeof(info)
            info.Address.ullLong = addr_value
            bt.BluetoothGetDeviceInfo(wintypes.HANDLE(h_val), ctypes.byref(info))
            if bool(info.fAuthenticated):
                return True
            result = None
            if auth_ex:
                result = auth_ex(None, wintypes.HANDLE(h_val), ctypes.byref(info), None, 0)
            elif auth_legacy:
                result = auth_legacy(None, wintypes.HANDLE(h_val), ctypes.byref(info), None, 0)
            if result in {0, 183, 1247}:
                return True
    finally:
        for h_val in radios:
            k32.CloseHandle(wintypes.HANDLE(h_val))
    return False

import base64
import ctypes
import os
from ctypes import wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect(secret: str, machine_scope: bool = False) -> str:
    if os.name != "nt":
        return "plain:" + base64.b64encode(secret.encode()).decode()
    source, source_buffer = _blob(secret.encode())
    output = DATA_BLOB()
    flags = 0x01 | (0x04 if machine_scope else 0)  # UI_FORBIDDEN | LOCAL_MACHINE
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "Northstar Endpoint Agent", None, None, None,
                                                  flags, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        scope = "machine" if machine_scope else "user"
        return f"dpapi-{scope}:" + base64.b64encode(ctypes.string_at(output.pbData, output.cbData)).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def unprotect(value: str) -> str:
    mode, encoded = value.split(":", 1)
    raw = base64.b64decode(encoded)
    if mode == "plain":
        if os.name == "nt":
            raise RuntimeError("Refusing a plaintext credential on Windows")
        return raw.decode()
    if mode not in {"dpapi", "dpapi-user", "dpapi-machine"}:
        raise RuntimeError("Unsupported endpoint credential protection mode")
    source, source_buffer = _blob(raw)
    output = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0x01,
                                                    ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode()
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)

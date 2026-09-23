import json
import os
import subprocess
import time
from typing import Any


class ProbeFailure(RuntimeError):
    pass


def run_hidden(arguments: list[str], timeout: float = 15) -> tuple[int, str, str]:
    """Run a fixed command invisibly and terminate its Windows process tree on timeout."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    startup = None
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", creationflags=flags, startupinfo=startup)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, creationflags=flags, startupinfo=startup, timeout=5)
        else:
            process.kill()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        raise ProbeFailure(f"command timed out after {timeout:g}s") from exc
    return process.returncode, stdout.strip(), stderr.strip()


def powershell_json(script: str, timeout: float = 20, default: Any = None) -> Any:
    code, output, error = run_hidden([
        "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-Command", f"$ErrorActionPreference='Stop'; & {{ {script} }} | ConvertTo-Json -Depth 8 -Compress",
    ], timeout=timeout)
    if code != 0:
        raise ProbeFailure(error or f"PowerShell exited with {code}")
    if not output:
        return default
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ProbeFailure("PowerShell returned invalid JSON") from exc


def probe(name: str, operation, fallback: Any) -> tuple[Any, dict]:
    started = time.monotonic()
    try:
        value = operation()
        return value, {"probe": name, "status": "Completed", "duration_ms": round((time.monotonic()-started)*1000)}
    except Exception as exc:
        return fallback, {"probe": name, "status": "Unavailable", "duration_ms": round((time.monotonic()-started)*1000),
                          "exception_type": type(exc).__name__}


def as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]

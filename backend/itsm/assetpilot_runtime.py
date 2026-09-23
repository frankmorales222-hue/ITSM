"""Start the local AssetPilot service on demand for seamless deep links."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from .config import settings


_start_lock = threading.Lock()


def assetpilot_executable() -> Path:
    if settings.assetpilot_executable:
        return Path(settings.assetpilot_executable)
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AssetPilot" / "AssetPilot.exe"


def assetpilot_database() -> Path:
    if settings.assetpilot_database_path:
        return Path(settings.assetpilot_database_path)
    return Path(os.environ.get("LOCALAPPDATA", "")) / "AssetPilot" / "Data" / "assetpilot.db"


def assetpilot_healthy() -> bool:
    try:
        with urlopen(f"{settings.assetpilot_internal_url.rstrip('/')}/health", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def ensure_assetpilot_running(timeout_seconds: float = 20) -> None:
    if assetpilot_healthy():
        return
    with _start_lock:
        if assetpilot_healthy():
            return
        executable = assetpilot_executable()
        if not executable.is_file():
            raise FileNotFoundError(f"AssetPilot is not installed at {executable}")
        database = assetpilot_database()
        database.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update({
            "Database__Path": str(database),
            "Backup__Path": str(database.parent / "Backups"),
            "ASPNETCORE_URLS": settings.assetpilot_internal_url,
            "ASPNETCORE_ENVIRONMENT": "Production",
            "Logging__EventLog__LogLevel__Default": "None",
        })
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([str(executable)], cwd=str(executable.parent), env=environment,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=creation_flags)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if assetpilot_healthy():
                return
            time.sleep(0.25)
        raise TimeoutError("AssetPilot did not become ready within 20 seconds")

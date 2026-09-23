"""Verification, staging, and installation of signed offline update packages."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import __version__
from .config import settings

PRODUCT = "Northstar Desk Server"
PACKAGE_SUFFIX = ".nsupdate"
REQUIRED_ENTRIES = {"manifest.json", "signature.ed25519"}
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$")


class UpdateValidationError(ValueError):
    pass


def version_key(value: str) -> tuple[int, int, int, tuple[int, str]]:
    match = VERSION_RE.fullmatch((value or "").strip())
    if not match:
        raise UpdateValidationError("Versions must use semantic version format, for example 1.4.2.")
    prerelease = match.group(4)
    # A final release sorts after its prerelease with the same numeric version.
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), (1 if prerelease is None else 0, prerelease or "")


def canonical_manifest(manifest: dict) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _decode_public_key(value: str) -> Ed25519PublicKey:
    raw_value = (value or "").strip()
    if not raw_value:
        raise UpdateValidationError("Update signature verification is not configured on this server.")
    try:
        if "BEGIN PUBLIC KEY" in raw_value:
            key = serialization.load_pem_public_key(raw_value.encode("ascii"))
            if not isinstance(key, Ed25519PublicKey):
                raise TypeError("not Ed25519")
            return key
        raw = base64.b64decode(raw_value, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise UpdateValidationError("The configured update verification key is invalid.") from exc


def public_key_fingerprint(value: str) -> str:
    if not (value or "").strip():
        return ""
    key = _decode_public_key(value)
    raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    digest = hashlib.sha256(raw).hexdigest().upper()
    return ":".join(digest[index:index + 4] for index in range(0, 32, 4))


def staging_root() -> Path:
    configured = (settings.update_staging_directory or "").strip()
    root = Path(configured) if configured else Path(settings.data_directory).resolve().parent / "updates"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def stream_to_staging(source: BinaryIO, original_name: str) -> tuple[Path, str]:
    if not (original_name or "").lower().endswith(PACKAGE_SUFFIX):
        raise UpdateValidationError(f"Choose a {PACKAGE_SUFFIX} update package.")
    limit = max(1, settings.update_max_package_mb) * 1024 * 1024
    temporary = staging_root() / f"upload-{uuid.uuid4().hex}.tmp"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as output:
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise UpdateValidationError(f"The update package exceeds the {settings.update_max_package_mb} MB limit.")
                digest.update(block)
                output.write(block)
        return temporary, digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def verify_package(path: Path, public_key_value: str, current_version: str = __version__) -> dict:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = {item.filename for item in infos}
            if any(item.is_dir() or Path(item.filename).name != item.filename for item in infos):
                raise UpdateValidationError("Update packages may not contain folders or unsafe paths.")
            if not REQUIRED_ENTRIES.issubset(names) or len(names) != 3 or len(infos) != 3:
                raise UpdateValidationError("The update package structure is invalid.")
            if sum(item.file_size for item in infos) > max(1, settings.update_max_package_mb) * 1024 * 1024 * 2:
                raise UpdateValidationError("The expanded update package is too large.")
            manifest_bytes = archive.read("manifest.json")
            if len(manifest_bytes) > 128 * 1024:
                raise UpdateValidationError("The update manifest is too large.")
            manifest = json.loads(manifest_bytes)
            if canonical_manifest(manifest) != manifest_bytes:
                raise UpdateValidationError("The update manifest is not in canonical signed form.")
            signature = base64.b64decode(archive.read("signature.ed25519"), validate=True)
            _decode_public_key(public_key_value).verify(signature, manifest_bytes)
            required = {"product", "version", "package_id", "released_at", "publisher", "payload", "payload_sha256", "release_notes"}
            if not required.issubset(manifest):
                raise UpdateValidationError("The update manifest is missing required fields.")
            if manifest["product"] != PRODUCT:
                raise UpdateValidationError("This package is not a Northstar Desk Server update.")
            version_key(manifest["version"])
            version_key(current_version)
            if version_key(manifest["version"]) <= version_key(current_version):
                raise UpdateValidationError(f"Version {manifest['version']} is not newer than installed version {current_version}.")
            minimum = manifest.get("minimum_current_version")
            if minimum and version_key(current_version) < version_key(minimum):
                raise UpdateValidationError(f"Install version {minimum} or later before applying this update.")
            if "component_update" in manifest and not isinstance(manifest["component_update"], bool):
                raise UpdateValidationError("The component update declaration is invalid.")
            uuid.UUID(str(manifest["package_id"]))
            payload_name = str(manifest["payload"])
            if Path(payload_name).name != payload_name or not payload_name.lower().endswith(".exe") or payload_name not in names:
                raise UpdateValidationError("The signed installer payload is invalid.")
            payload_digest = hashlib.sha256(archive.read(payload_name)).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", str(manifest["payload_sha256"])) or payload_digest != manifest["payload_sha256"]:
                raise UpdateValidationError("The installer payload hash does not match the signed manifest.")
            datetime.fromisoformat(str(manifest["released_at"]).replace("Z", "+00:00"))
            return manifest
    except InvalidSignature as exc:
        raise UpdateValidationError("The update signature is not trusted. The package may be altered or unofficial.") from exc
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, UpdateValidationError):
            raise
        raise UpdateValidationError("The update package is damaged or malformed.") from exc


def finalize_staging(temporary: Path, manifest: dict) -> tuple[Path, Path]:
    release = staging_root() / f"{manifest['version']}-{manifest['package_id']}"
    if release.exists():
        raise UpdateValidationError("This exact update package has already been staged.")
    release.mkdir(parents=False)
    package_path = release / f"NorthstarDesk-{manifest['version']}{PACKAGE_SUFFIX}"
    try:
        os.replace(temporary, package_path)
        with zipfile.ZipFile(package_path, "r") as archive:
            payload_path = release / manifest["payload"]
            with archive.open(manifest["payload"], "r") as source, payload_path.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
        return package_path, payload_path
    except Exception:
        shutil.rmtree(release, ignore_errors=True)
        raise


def launch_installer(payload_path: Path, update_id: int, *, component_update: bool = False) -> None:
    if os.name != "nt" or not settings.production:
        raise RuntimeError("One-click installation is available only on the packaged Windows production server.")
    if not payload_path.is_file():
        raise RuntimeError("The staged installer payload is missing.")
    script = payload_path.parent / "apply-update.cmd"
    log_path = payload_path.parent / "installation.log"
    installer_log_path = payload_path.parent / "installer.log"
    exit_code_path = payload_path.parent / "exit-code.txt"
    task_name = f"Northstar Desk Update {update_id}"
    shutdown_commands = (
        "echo [%DATE% %TIME%] Stopping Northstar tasks >> \"%~dp0installation.log\"\r\n"
        "schtasks.exe /End /TN \"Northstar Desk\" >> \"%~dp0installation.log\" 2>&1\r\n"
        "schtasks.exe /End /TN \"Northstar HTTPS\" >> \"%~dp0installation.log\" 2>&1\r\n"
        "taskkill.exe /F /IM NorthstarDeskServer.exe >> \"%~dp0installation.log\" 2>&1\r\n"
        "taskkill.exe /F /IM caddy.exe >> \"%~dp0installation.log\" 2>&1\r\n"
    )
    if component_update:
        # Component packages only replace a separately distributed artifact such
        # as the endpoint-agent installer.  They must never interrupt the live
        # Desk or HTTPS processes because no server binary is being replaced.
        shutdown_commands = (
            "echo [%DATE% %TIME%] Component-only update; Northstar tasks remain online. "
            ">> \"%~dp0installation.log\"\r\n"
        )
    # All paths are generated by the application, not supplied by the manifest.
    script.write_text(
        "@echo off\r\n"
        "setlocal EnableExtensions\r\n"
        f'echo [%DATE% %TIME%] Starting supervised update > "{log_path}"\r\n'
        "timeout /t 8 /nobreak >> \"%~dp0installation.log\" 2>&1\r\n"
        f"{shutdown_commands}"
        "echo [%DATE% %TIME%] Launching installer >> \"%~dp0installation.log\"\r\n"
        f'"{payload_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /LOG="{installer_log_path}" >> "%~dp0installation.log" 2>&1\r\n'
        "set \"UPDATE_EXIT_CODE=%ERRORLEVEL%\"\r\n"
        "if not defined UPDATE_EXIT_CODE set \"UPDATE_EXIT_CODE=1\"\r\n"
        f'>"{exit_code_path}" echo(%UPDATE_EXIT_CODE%\r\n'
        "echo [%DATE% %TIME%] Installer exit code: %UPDATE_EXIT_CODE% >> \"%~dp0installation.log\"\r\n"
        "endlocal\r\n",
        encoding="ascii",
    )
    # A one-time SYSTEM task survives the shutdown of the current Northstar task.
    # A detached child process does not reliably survive an in-place installer that
    # terminates and recreates its parent scheduled task.
    start_at = datetime.now() + timedelta(days=1)
    try:
        subprocess.run(
            ["schtasks.exe", "/Create", "/TN", task_name,
             "/TR", f'cmd.exe /d /c "{script}"',
             "/SC", "ONCE", "/ST", start_at.strftime("%H:%M"),
             "/SD", start_at.strftime("%m/%d/%Y"), "/RU", "SYSTEM",
             "/RL", "HIGHEST", "/F"],
            cwd=str(payload_path.parent), check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["schtasks.exe", "/Run", "/TN", task_name],
            cwd=str(payload_path.parent), check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        details = getattr(exc, "stderr", "") or str(exc)
        raise RuntimeError(f"Windows could not schedule the verified update: {details.strip()}") from exc

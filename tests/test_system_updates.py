import base64
import hashlib
import json
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from itsm import __version__
from itsm.config import settings
from itsm import system_updates
from itsm.system_updates import UpdateValidationError, canonical_manifest, launch_installer, verify_package


def package(path, key, version="0.5.0", payload=b"MZ signed test installer"):
    payload_name = f"NorthstarDesk-Server-Setup-{version}.exe"
    manifest = {
        "product": "Northstar Desk Server", "version": version,
        "package_id": str(uuid.uuid4()),
        "released_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "publisher": "Northstar Test", "payload": payload_name,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "release_notes": "Signed updater test", "database_backup_required": True,
    }
    raw = canonical_manifest(manifest)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", raw)
        archive.writestr("signature.ed25519", base64.b64encode(key.sign(raw)))
        archive.writestr(payload_name, payload)
    return manifest


def test_component_update_declaration_must_be_boolean(tmp_path):
    key = Ed25519PrivateKey.generate()
    valid = tmp_path / "component.nsupdate"
    manifest = package(valid, key)
    manifest["component_update"] = "yes"
    raw = canonical_manifest(manifest)
    with zipfile.ZipFile(valid, "w") as archive:
        archive.writestr("manifest.json", raw)
        archive.writestr("signature.ed25519", base64.b64encode(key.sign(raw)))
        archive.writestr(manifest["payload"], b"MZ signed test installer")
    with pytest.raises(UpdateValidationError, match="component update declaration"):
        verify_package(valid, public_value(key))


def public_value(key):
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def test_signed_package_rejects_tampering_and_downgrades(tmp_path):
    key = Ed25519PrivateKey.generate()
    valid = tmp_path / "valid.nsupdate"
    package(valid, key)
    assert verify_package(valid, public_value(key))["version"] == "0.5.0"

    old = tmp_path / "old.nsupdate"
    package(old, key, "0.4.0")
    with pytest.raises(UpdateValidationError, match="not newer"):
        verify_package(old, public_value(key))

    damaged = tmp_path / "damaged.nsupdate"
    original = tmp_path / "original.nsupdate"
    package(original, key, "0.4.2")
    with zipfile.ZipFile(original, "r") as archive:
        manifest = json.loads(archive.read("manifest.json")); signature = archive.read("signature.ed25519")
        payload_name = manifest["payload"]; payload = archive.read(payload_name)
    manifest["release_notes"] = "Altered after signing"
    with zipfile.ZipFile(damaged, "w") as archive:
        archive.writestr("manifest.json", canonical_manifest(manifest))
        archive.writestr("signature.ed25519", signature)
        archive.writestr(payload_name, payload)
    with pytest.raises(UpdateValidationError, match="signature is not trusted"):
        verify_package(damaged, public_value(key))


def test_admin_uploads_signed_update_once(admin, tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    update = tmp_path / "release.nsupdate"
    package(update, key, "0.5.0")
    monkeypatch.setattr(settings, "update_public_key", public_value(key))
    monkeypatch.setattr(settings, "update_staging_directory", str(tmp_path / "staging"))

    with update.open("rb") as stream:
        result = admin.post("/api/admin/system-updates/upload", files={"package": (update.name, stream, "application/octet-stream")})
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "Validated"
    listing = admin.get("/api/admin/system-updates")
    assert listing.status_code == 200
    assert listing.json()["verification_configured"] is True
    assert listing.json()["current_version"] == __version__
    assert listing.json()["updates"][0]["version"] == "0.5.0"

    with update.open("rb") as stream:
        duplicate = admin.post("/api/admin/system-updates/upload", files={"package": (update.name, stream, "application/octet-stream")})
    assert duplicate.status_code == 400
    assert "already been uploaded" in duplicate.text


def test_update_launcher_uses_supervised_system_task(tmp_path, monkeypatch):
    payload = tmp_path / "NorthstarDesk-Server-Setup-0.5.0.exe"
    payload.write_bytes(b"MZ")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(system_updates.os, "name", "nt")
    monkeypatch.setattr(system_updates.subprocess, "run", fake_run)

    launch_installer(payload, 42)

    script = (tmp_path / "apply-update.cmd").read_text(encoding="ascii")
    assert 'schtasks.exe /End /TN "Northstar Desk"' in script
    assert "NorthstarDeskServer.exe" in script
    assert (tmp_path / "exit-code.txt").name in script
    assert calls[0][0][:4] == ["schtasks.exe", "/Create", "/TN", "Northstar Desk Update 42"]
    assert calls[1][0] == ["schtasks.exe", "/Run", "/TN", "Northstar Desk Update 42"]


def test_component_update_leaves_desk_and_https_running(tmp_path, monkeypatch):
    payload = tmp_path / "NorthstarDesk-Agent-Refresh-0.5.0.exe"
    payload.write_bytes(b"MZ")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(system_updates.os, "name", "nt")
    monkeypatch.setattr(system_updates.subprocess, "run", fake_run)

    launch_installer(payload, 43, component_update=True)

    script = (tmp_path / "apply-update.cmd").read_text(encoding="ascii")
    assert "Component-only update; Northstar tasks remain online." in script
    assert 'schtasks.exe /End /TN "Northstar Desk"' not in script
    assert 'schtasks.exe /End /TN "Northstar HTTPS"' not in script
    assert "taskkill.exe" not in script
    assert calls[0][0][:4] == ["schtasks.exe", "/Create", "/TN", "Northstar Desk Update 43"]
    assert calls[1][0] == ["schtasks.exe", "/Run", "/TN", "Northstar Desk Update 43"]

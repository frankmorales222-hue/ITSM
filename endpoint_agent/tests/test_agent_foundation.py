import json
from pathlib import Path

import pytest

from asset_agent.identity.device_identity import stable_device_id
from asset_agent.agent import Agent, SingleInstance
from asset_agent.storage.database import AgentDatabase
from asset_agent.tray import help_desk_urls
from asset_agent.transport.sync_interface import InventoryTransport
from asset_agent.observed_user import observed_user_claims


def test_stable_device_identity_prefers_valid_smbios_uuid():
    first, source = stable_device_id("01234567-89ab-cdef-0123-456789abcdef", "SERIAL", "Maker", "Model", "guid")
    second, _ = stable_device_id("01234567-89AB-CDEF-0123-456789ABCDEF", "different", "Other", "Other", "other")
    assert first == second
    assert source == "smbios_uuid"


def test_stable_device_identity_falls_back_and_rejects_empty():
    value, source = stable_device_id("00000000-0000-0000-0000-000000000000", "ABC123", "Maker", "Model", "guid")
    assert len(value) == 64
    assert source == "hardware_composite"
    with pytest.raises(RuntimeError):
        stable_device_id("", "Unknown", "", "", "")


def test_observed_user_rejects_a_computer_account(monkeypatch):
    monkeypatch.setattr("asset_agent.observed_user.powershell_json", lambda _script: {
        "email": "MRWS-FRANK$@medreceivables.com", "user_principal_name": "MRWS-FRANK$@medreceivables.com",
    })
    monkeypatch.setattr("asset_agent.observed_user.run_hidden", lambda *_args, **_kwargs: (0, "MRWS-FRANK$@medreceivables.com", ""))
    assert observed_user_claims() == {}


def test_invalid_installer_override_falls_through_to_interactive_user(monkeypatch):
    monkeypatch.setattr("asset_agent.observed_user.powershell_json", lambda _script: {
        "email": "Francisco.Morales@medreceivables.com", "account_name": "Francisco.Morales",
    })
    assert observed_user_claims("MRWS-FRANK$@medreceivables.com") == {
        "email": "francisco.morales@medreceivables.com", "account_name": "Francisco.Morales",
    }


def test_observed_user_uses_the_interactive_person_email(monkeypatch):
    monkeypatch.setattr("asset_agent.observed_user.powershell_json", lambda _script: {
        "email": "Francisco.Morales@medreceivables.com", "account_name": "Francisco.Morales",
    })
    assert observed_user_claims() == {
        "email": "francisco.morales@medreceivables.com", "account_name": "Francisco.Morales",
    }


def test_inventory_outbox_is_durable():
    path = Path("data/test_endpoint_agent.db")
    path.unlink(missing_ok=True)


def test_duplicate_long_running_agents_are_prevented():
    path = Path("data/test_endpoint_agent.lock")
    path.unlink(missing_ok=True)
    first, second = SingleInstance(path), SingleInstance(path)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
    path.unlink(missing_ok=True)
    db = AgentDatabase(path)
    payload = {"collected_at": "2026-08-13T12:00:00+00:00", "device_id": "a" * 64}
    item_id = db.save_inventory(payload)
    pending = db.pending()
    assert pending[0]["id"] == item_id
    assert json.loads(pending[0]["payload"])["device_id"] == "a" * 64
    db.failed(item_id, "offline")
    assert db.pending()[0]["attempts"] == 1
    db.delivered(item_id)
    assert db.pending() == []
    db.close()
    path.unlink(missing_ok=True)


def test_tray_urls_open_home_and_request_catalog():
    assert help_desk_urls("https://helpdesk.example.test/") == (
        "https://helpdesk.example.test/#home", "https://helpdesk.example.test/#catalog",
        "https://helpdesk.example.test/#tickets", "https://helpdesk.example.test/#notifications"
    )
    assert help_desk_urls("http://127.0.0.1:8011") == (
        "http://127.0.0.1:8011/#home", "http://127.0.0.1:8011/#catalog",
        "http://127.0.0.1:8011/#tickets", "http://127.0.0.1:8011/#notifications"
    )
    with pytest.raises(ValueError):
        help_desk_urls("http://helpdesk.example.test")


class _FakeTlsSocket:
    def __init__(self, certificate: bytes):
        self.certificate = certificate

    def getpeercert(self, binary_form=False):
        return self.certificate if binary_form else {}


class _FakeResponse:
    status = 200

    def read(self):
        return b'{"ok": true}'


class _FakeHttpsConnection:
    certificate = b"northstar-test-certificate"

    def __init__(self, *args, **kwargs):
        self.sock = None

    def connect(self):
        self.sock = _FakeTlsSocket(self.certificate)

    def request(self, *args, **kwargs):
        return None

    def getresponse(self):
        return _FakeResponse()

    def close(self):
        return None


def test_pinned_tls_accepts_only_the_approved_certificate(monkeypatch):
    import hashlib
    monkeypatch.setattr("asset_agent.transport.sync_interface.http.client.HTTPSConnection", _FakeHttpsConnection)
    approved = hashlib.sha256(_FakeHttpsConnection.certificate).hexdigest()
    transport = InventoryTransport("https://helpdesk.example.test", tls_certificate_sha256=approved)
    assert transport._request("POST", "/api/test", {"test": True}) == {"ok": True}

    rejected = InventoryTransport("https://helpdesk.example.test", tls_certificate_sha256="0" * 64)
    with pytest.raises(RuntimeError, match="does not match"):
        rejected._request("POST", "/api/test", {"test": True})


def test_invalid_tls_pin_is_rejected():
    with pytest.raises(ValueError, match="64 hexadecimal"):
        InventoryTransport("https://helpdesk.example.test", tls_certificate_sha256="not-a-pin")


def test_agent_runs_only_server_approved_allowlisted_action(monkeypatch):
    class Transport:
        def __init__(self):
            self.result = None
        def next_action(self, _credential):
            return {"action":{"id":7,"action_type":"terminate_process","target":"EXCEL.EXE"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-action-test")
    observed = []
    monkeypatch.setattr(Agent, "_run", staticmethod(lambda command, timeout=30: (
        observed.append(command) is None, "Closed EXCEL.EXE.",
    )))
    agent.perform_approved_action()
    assert len(observed) == 1
    assert observed[0][-4:] == ["/F", "/T", "/IM", "EXCEL.EXE"]
    assert observed[0][0].lower().endswith("\\system32\\taskkill.exe") or observed[0][0] == "taskkill.exe"
    assert transport.result == (7, True, "Closed EXCEL.EXE.")


def test_agent_waits_for_service_to_stop_before_restart(monkeypatch):
    class Transport:
        def __init__(self):
            self.result = None
        def next_action(self, _credential):
            return {"action":{"id":8,"action_type":"restart_service","target":"Spooler"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-service-action-test")
    observed = []
    responses = iter([(True, "STOP_PENDING"), (True, "STOPPED"), (True, "START_PENDING")])
    monkeypatch.setattr(Agent, "_run", staticmethod(lambda command, timeout=30: (
        observed.append(command) is None and next(responses)
    )))
    monkeypatch.setattr("asset_agent.agent.time.sleep", lambda _seconds: None)
    agent.perform_approved_action()
    assert observed == [
        ["sc.exe", "stop", "Spooler"],
        ["sc.exe", "query", "Spooler"],
        ["sc.exe", "start", "Spooler"],
    ]
    assert transport.result == (8, True, "START_PENDING")


def test_system_install_relaunches_tray_through_users_group_task():
    root = Path(__file__).resolve().parents[1]
    installer = (root / "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")
    task_installer = (root / "scripts/install-tray-launcher-task.ps1").read_text(encoding="utf-8")
    tray_launcher = (root / "scripts/launch-tray.ps1").read_text(encoding="utf-8")
    uninstaller = (root / "scripts/uninstall-enterprise.ps1").read_text(encoding="utf-8")
    enterprise_builder = (root / "scripts/build-enterprise-package.ps1").read_text(encoding="utf-8")
    migration = (root / "scripts/migrate-legacy-x86-install.ps1").read_text(encoding="utf-8")

    tray_file_line = next(line for line in installer.splitlines()
                          if 'Source: "artifacts\\NorthstarEndpointAgent-enterprise\\NorthstarEndpointTray\\*"' in line)
    assert "restartreplace" not in tray_file_line.lower()
    assert "runasoriginaluser" not in installer.lower()
    assert 'install-tray-launcher-task.ps1' in installer
    assert '/Run /TN ""Northstar Endpoint Tray Launcher""' in installer

    assert "<GroupId>S-1-5-32-545</GroupId>" in task_installer
    assert "<RunLevel>LeastPrivilege</RunLevel>" in task_installer
    assert "<Triggers />" in task_installer
    assert "-WindowStyle Hidden" in task_installer
    assert '& $schtasks /Create /TN $TaskName /XML $xmlPath /F' in task_installer

    assert 'Local\\NorthstarEndpointTrayLauncher-$sessionId' in tray_launcher
    assert 'Where-Object { $_.SessionId -eq $sessionId }' in tray_launcher
    assert 'Northstar Endpoint Tray Launcher' in uninstaller
    assert 'install-tray-launcher-task.ps1' in enterprise_builder
    assert 'migrate-legacy-x86-install.ps1' in installer
    assert 'migrate-legacy-x86-install.ps1' in enterprise_builder
    assert 'Northstar Endpoint Agent - User Logon Inventory' in migration
    assert '$exec.Command = $targetExecutable' in migration
    assert 'Copy-Item -LiteralPath $legacyTrayConfig' in migration
    assert 'Get-CimInstance Win32_Process' in migration
    assert 'WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall' in migration
    assert 'UninstallString' in migration
    assert 'Uninstall.exe' not in migration
    assert 'ProgramData' not in migration


def test_agent_0139_release_metadata_is_aligned():
    root = Path(__file__).resolve().parents[1]
    assert '__version__ = "0.1.39"' in (root /
        "asset_agent/__init__.py").read_text(encoding="utf-8")
    assert 'version = "0.1.39"' in (root /
        "pyproject.toml").read_text(encoding="utf-8")
    assert '#define MyAppVersion "0.1.39"' in (root /
        "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")
    notes = (root / "release-notes-0.1.39.txt").read_text(encoding="utf-8")
    assert "32-bit" in notes and "ProgramData" in notes and "tray" in notes.lower()
    server_installer = (root.parent / "installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    server_builder = (root.parent / "installer/build-full-server-update.ps1").read_text(encoding="utf-8")
    assert '#define MyAppVersion "0.4.92"' in server_installer
    assert '[string]$Version = "0.4.92"' in server_builder

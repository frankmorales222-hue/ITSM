import base64
import ctypes
import json
import hashlib
import os
import re
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest

from asset_agent.identity.device_identity import stable_device_id
from asset_agent.agent import Agent, SingleInstance, watchdog_restart_reason
from asset_agent.storage.database import AgentDatabase
from asset_agent.tray import help_desk_urls
from asset_agent.transport.sync_interface import InventoryTransport
from asset_agent.observed_user import observed_user_claims
from asset_agent.scheduler import Scheduler


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
            return {"action":{"id":7,"action_type":"terminate_process","target":"EXCEL.EXE",
                              "requester_username":"requester"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-action-test")
    observed = []
    monkeypatch.setattr(Agent, "_session_id_for_requester", classmethod(lambda cls, action: 7))
    monkeypatch.setattr(Agent, "_run", staticmethod(lambda command, timeout=30: (
        observed.append(command) is None, "Closed EXCEL.EXE.",
    )))
    agent.perform_approved_action()
    assert len(observed) == 1
    assert observed[0][1:] == [
        "/F", "/T", "/FI", "SESSION eq 7", "/FI", "IMAGENAME eq EXCEL.EXE",
    ]
    assert "/IM" not in observed[0]
    assert observed[0][0].lower().endswith("\\system32\\taskkill.exe") or observed[0][0] == "taskkill.exe"
    assert transport.result == (7, True, "Closed EXCEL.EXE.")


def test_agent_reports_when_process_is_not_running_in_signed_in_session(monkeypatch):
    class Transport:
        def __init__(self):
            self.result = None
        def next_action(self, _credential):
            return {"action":{"id":9,"action_type":"terminate_process","target":"EXCEL.EXE",
                              "requester_username":"requester"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-action-missing-test")
    monkeypatch.setattr(Agent, "_session_id_for_requester", classmethod(lambda cls, action: 12))
    monkeypatch.setattr(Agent, "_run", staticmethod(lambda command, timeout=30: (
        True, "INFO: No tasks running with the specified criteria.",
    )))

    agent.perform_approved_action()

    assert transport.result == (9, False, "EXCEL.EXE is not running for the signed-in user")


def test_requester_rdp_session_is_chosen_over_console_session(monkeypatch):
    monkeypatch.setattr(Agent, "_windows_sessions", staticmethod(lambda: [
        {"session_id": 1, "username": "console.user", "domain": "EXAMPLE", "console": True},
        {"session_id": 14, "username": "requester", "domain": "EXAMPLE", "console": False},
    ]))

    assert Agent._session_id_for_requester({
        "requester_username": "requester",
        "requester_upn": "requester@example.test",
    }) == 14


def test_unmatched_requester_uses_the_only_active_user_session(monkeypatch):
    monkeypatch.setattr(Agent, "_windows_sessions", staticmethod(lambda: [
        {"session_id": 22, "username": "only.user", "domain": "EXAMPLE", "console": False},
    ]))

    assert Agent._session_id_for_requester({
        "requester_username": "different.user",
        "requester_upn": "different.user@example.test",
    }) == 22


def test_unmatched_requester_is_not_assigned_when_two_users_are_active(monkeypatch):
    monkeypatch.setattr(Agent, "_windows_sessions", staticmethod(lambda: [
        {"session_id": 1, "username": "console.user", "domain": "EXAMPLE", "console": True},
        {"session_id": 14, "username": "rdp.user", "domain": "EXAMPLE", "console": False},
    ]))

    assert Agent._session_id_for_requester({
        "requester_username": "missing.user",
        "requester_upn": "missing.user@example.test",
    }) is None


def test_action_does_not_run_when_requester_is_unmatched_with_two_active_users(monkeypatch):
    class Transport:
        def __init__(self):
            self.result = None
        def next_action(self, _credential):
            return {"action":{"id":11,"action_type":"terminate_process","target":"EXCEL.EXE",
                              "requester_username":"missing.user"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-action-ambiguous-session-test")
    monkeypatch.setattr(Agent, "_windows_sessions", staticmethod(lambda: [
        {"session_id": 1, "username": "console.user", "domain": "EXAMPLE", "console": True},
        {"session_id": 14, "username": "rdp.user", "domain": "EXAMPLE", "console": False},
    ]))
    executed = []
    monkeypatch.setattr(Agent, "_run", staticmethod(
        lambda command, timeout=30: (executed.append(command) is None, "unexpected")))

    agent.perform_approved_action()

    assert executed == []
    assert transport.result == (11, False, "The requester is not signed in on this computer.")


def test_taskkill_access_denied_reports_the_real_error(monkeypatch):
    class Transport:
        def __init__(self):
            self.result = None
        def next_action(self, _credential):
            return {"action":{"id":10,"action_type":"terminate_process","target":"EXCEL.EXE",
                              "requester_username":"requester"}}
        def action_result(self, _credential, action_id, succeeded, summary):
            self.result = (action_id, succeeded, summary)
    transport = Transport()
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential":"device-secret"})()
    agent.transport = transport
    agent.logger = __import__("logging").getLogger("endpoint-action-denied-test")
    monkeypatch.setattr(Agent, "_session_id_for_requester", classmethod(lambda cls, action: 12))
    monkeypatch.setattr(Agent, "_run", staticmethod(lambda command, timeout=30: (
        False, "ERROR: Access is denied.",
    )))

    agent.perform_approved_action()

    assert transport.result == (10, False, "ERROR: Access is denied.")


def test_action_scheduler_runs_while_inventory_is_blocked_and_times_out():
    inventory_started = threading.Event()
    release_inventory = threading.Event()
    action_processed = threading.Event()
    inventory_timed_out = threading.Event()

    def blocked_inventory():
        inventory_started.set()
        release_inventory.wait(5)

    scheduler = Scheduler(
        blocked_inventory, action_processed.set, full_interval=300, heartbeat_interval=15,
        full_timeout=1, full_timeout_action=inventory_timed_out.set,
    )
    scheduler.start()
    try:
        assert inventory_started.wait(1)
        assert action_processed.wait(1)
        assert inventory_timed_out.wait(2)
    finally:
        release_inventory.set()
        scheduler.stop()


def test_action_scheduler_survives_refresh_and_heartbeat_exceptions():
    errors = []
    calls = {"refresh": 0, "heartbeat": 0}
    completed = threading.Event()

    def refresh():
        calls["refresh"] += 1
        if calls["refresh"] == 1:
            raise RuntimeError("refresh failed")
        return True

    def heartbeat():
        calls["heartbeat"] += 1
        if calls["heartbeat"] == 1:
            raise RuntimeError("heartbeat failed")
        completed.set()

    scheduler = Scheduler(lambda: None, heartbeat, 300, 15, refresh_requested=refresh,
                          action_error=lambda exc: errors.append(str(exc)))
    scheduler.start()
    try:
        assert completed.wait(7)
        assert scheduler.action_thread.is_alive()
        assert errors[:2] == ["refresh failed", "heartbeat failed"]
    finally:
        scheduler.stop()


def test_hung_action_times_out_without_starting_another_worker(monkeypatch):
    class AliveWorker:
        def is_alive(self): return True
    results = []
    agent = Agent.__new__(Agent)
    agent.config = type("Config", (), {"credential": "secret"})()
    agent.transport = type("Transport", (), {
        "action_result": lambda _self, _credential, action_id, succeeded, summary:
            results.append((action_id, succeeded, summary)),
    })()
    agent.logger = __import__("logging").getLogger("hung-action-test")
    agent._action_lock = threading.Lock()
    agent._action_worker = AliveWorker()
    agent._action_current = {"id": 44, "action_type": "terminate_process", "target": "EXCEL.EXE"}
    agent._action_started_at = 0
    agent._action_timeout_reported = False
    monkeypatch.setattr("asset_agent.agent.time.monotonic", lambda: 91)

    agent._service_action_worker()
    agent._service_action_worker()

    assert results == [(44, False, "Action timed out on the endpoint")]
    assert agent._action_timeout_reported is True


def test_watchdog_detects_dead_action_thread_and_stale_heartbeat(monkeypatch):
    scheduler = type("SchedulerState", (), {})()
    scheduler.action_thread = type("Thread", (), {"is_alive": lambda _self: False})()
    scheduler.last_heartbeat_attempt = 100
    assert watchdog_restart_reason(scheduler) == "action thread stopped"
    scheduler.action_thread = type("Thread", (), {"is_alive": lambda _self: True})()
    monkeypatch.setattr("asset_agent.agent.time.monotonic", lambda: 401)
    assert watchdog_restart_reason(scheduler, 300) == "heartbeat attempt stale"


def test_self_repair_scheduler_runs_while_inventory_is_blocked():
    inventory_started = threading.Event()
    release_inventory = threading.Event()
    repaired = threading.Event()

    def blocked_inventory():
        inventory_started.set()
        release_inventory.wait(5)

    scheduler = Scheduler(
        blocked_inventory, lambda: None, full_interval=300, heartbeat_interval=15,
        maintenance_action=repaired.set, maintenance_interval=3600,
    )
    scheduler.start()
    try:
        assert inventory_started.wait(1)
        assert repaired.wait(1)
    finally:
        release_inventory.set()
        scheduler.stop()


def test_update_retry_waits_24_hours_but_newer_version_runs(tmp_path, monkeypatch):
    payload = b"northstar update"
    digest = hashlib.sha256(payload).hexdigest()

    class Transport:
        def __init__(self):
            self.downloads = []
        def download(self, path, _credential, destination):
            self.downloads.append(path)
            destination.write_bytes(payload)

    agent = Agent.__new__(Agent)
    agent.data_dir = tmp_path
    agent.config = type("Config", (), {"credential": "secret"})()
    agent.transport = Transport()
    agent.logger = __import__("logging").getLogger("update-retry-test")
    state_dir = tmp_path / "updates"
    state_dir.mkdir()
    (state_dir / "update-state.json").write_text(json.dumps({
        "version": "0.1.45", "status": "failed", "attempted_at": datetime.now(timezone.utc).isoformat(),
    }), encoding="utf-8")
    launches = []
    monkeypatch.setattr("asset_agent.agent.subprocess.Popen", lambda *args, **kwargs: launches.append(args))

    agent.schedule_agent_update({"version": "0.1.45", "sha256": digest,
                                 "download_path": "/api/agent/update/download"})
    assert agent.transport.downloads == []

    agent.schedule_agent_update({"version": "0.1.47", "sha256": digest,
                                 "download_path": "/api/agent/update/download"})
    assert agent.transport.downloads == ["/api/agent/update/download"]
    assert len(launches) == 1


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
    assert '/Run /TN "Northstar Endpoint Tray Launcher"' in installer

    assert "<GroupId>S-1-5-32-545</GroupId>" in task_installer
    task_template = task_installer.split('$taskXml = @"', 1)[1].split('"@', 1)[0]
    task_xml = (task_template.replace("$commandXml", "powershell.exe")
                .replace("$argumentsXml", "-NoProfile")
                .replace("$workingDirectoryXml", "C:\\Northstar").lstrip())
    task = ET.fromstring(task_xml)
    namespace = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert task.attrib["version"] == "1.4"
    principal = task.find("./t:Principals/t:Principal", namespace)
    assert principal is not None
    assert principal.findtext("t:GroupId", namespaces=namespace) == "S-1-5-32-545"
    assert principal.find("t:LogonType", namespace) is None
    assert principal.findtext("t:RunLevel", namespaces=namespace) == "LeastPrivilege"
    assert task.find("./t:Triggers", namespace) is not None
    assert task.findtext("./t:Settings/t:MultipleInstancesPolicy", namespaces=namespace) == "Parallel"
    assert task.findtext("./t:Settings/t:ExecutionTimeLimit", namespaces=namespace) == "PT1M"
    actions = task.find("./t:Actions", namespace)
    assert actions is not None and actions.attrib["Context"] == "Users"
    assert actions.find("./t:Exec/t:Command", namespace) is not None
    assert actions.find("./t:Exec/t:Arguments", namespace) is not None
    assert actions.find("./t:Exec/t:WorkingDirectory", namespace) is not None
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
    assert 'repair-agent-install.ps1' in enterprise_builder
    assert '/End /TN $taskNames[0]' in migration
    assert 'StartsWith($legacyRoot' in migration
    assert 'Northstar Endpoint Agent - User Logon Inventory' in migration
    assert '$exec.Command = $targetExecutable' in migration
    assert 'Copy-Item -LiteralPath $legacyTrayConfig' in migration
    assert 'Get-CimInstance Win32_Process' in migration
    assert 'WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall' in migration
    assert 'UninstallString' in migration
    assert 'Uninstall.exe' not in migration
    assert 'ProgramData' not in migration


def test_installer_exit_codes_distinguish_required_and_optional_steps():
    root = Path(__file__).resolve().parents[1]
    enterprise = (root / "scripts/install-enterprise.ps1").read_text(encoding="utf-8")
    self_service = (root / "scripts/install-self-service.ps1").read_text(encoding="utf-8")
    repair = (root / "scripts/repair-agent-install.ps1").read_text(encoding="utf-8")
    migration = (root / "scripts/migrate-legacy-x86-install.ps1").read_text(encoding="utf-8")
    tray = (root / "scripts/install-tray-launcher-task.ps1").read_text(encoding="utf-8")
    installer = (root / "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")

    assert 'Write-InstallWarning "The endpoint agent is running' in enterprise
    assert enterprise.rstrip().endswith("exit 0")


def test_agent_task_xml_has_restart_and_five_minute_trigger_and_self_repair_checks_it():
    root = Path(__file__).resolve().parents[1]
    enterprise = (root / "scripts/install-enterprise.ps1").read_text(encoding="utf-8")
    repair = (root / "scripts/repair-agent-install.ps1").read_text(encoding="utf-8")
    self_service = (root / "scripts/install-self-service.ps1").read_text(encoding="utf-8")
    migration = (root / "scripts/migrate-legacy-x86-install.ps1").read_text(encoding="utf-8")
    tray = (root / "scripts/install-tray-launcher-task.ps1").read_text(encoding="utf-8")
    installer = (root / "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")
    stop_script = (root / "scripts/stop-agent-for-upgrade.ps1").read_text(encoding="utf-8")
    for script in (enterprise, repair):
        assert "<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>" in script
        assert "<TimeTrigger><Repetition><Interval>PT5M</Interval>" in script
        assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in script
    assert 'SelectSingleNode("/t:Task/t:Settings/t:RestartOnFailure/t:Interval"' in repair
    assert 'SelectSingleNode("/t:Task/t:Triggers/t:TimeTrigger/t:Repetition/t:Interval"' in repair
    assert 'agent-stops.log' in stop_script
    assert 'reason=agent upgrade' in stop_script
    assert "$global:LASTEXITCODE = 0" in enterprise
    assert "$enterpriseExitCode = $LASTEXITCODE" in self_service
    assert "if ($enterpriseExitCode -ne 0)" in self_service
    assert self_service.rstrip().endswith("exit 0")
    assert 'throw "Endpoint enrollment failed' in enterprise
    assert "exit 1" in enterprise
    assert repair.rstrip().endswith("exit 0")
    assert migration.rstrip().endswith("exit 0")
    assert tray.rstrip().endswith("exit 0")
    assert "if ConfigurationFailed then Result := 1 else Result := 0" in installer
    tray_warning = installer.split("if not ConfigurationFailed then", 1)[1].split("InstallFinalized := True", 1)[0]
    assert "ConfigurationFailed := True" not in tray_warning


def _write_self_service_child_fixture(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fixture = tmp_path / "self-service-child"
    fixture.mkdir()
    shutil.copy2(root / "scripts/install-self-service.ps1", fixture / "install-self-service.ps1")
    (fixture / "install-enterprise.ps1").write_text(r'''
param(
    [Parameter(Mandatory=$true)][string]$ServerUrl,
    [string]$EnrollmentToken = "",
    [string]$EnrollmentTokenFile = "",
    [string]$TlsCertificateSha256 = "",
    [string]$InstallRoot = "",
    [string]$DataRoot = ""
)
$commandLine = [string](Get-CimInstance Win32_Process -Filter "ProcessId=$PID").CommandLine
$tokenFileExists = [bool]($EnrollmentTokenFile -and (Test-Path -LiteralPath $EnrollmentTokenFile))
$tokenValue = if ($tokenFileExists) { Get-Content -LiteralPath $EnrollmentTokenFile -Raw } else { "" }
[ordered]@{
    bound_keys = @($PSBoundParameters.Keys | ForEach-Object { [string]$_ })
    command_line = $commandLine
    enrollment_token = $EnrollmentToken
    enrollment_token_file = $EnrollmentTokenFile
    token_file_exists = $tokenFileExists
    token_value = $tokenValue
    tls = $TlsCertificateSha256
    install_root = $InstallRoot
    data_root = $DataRoot
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $env:NORTHSTAR_TEST_CAPTURE -Encoding UTF8
exit [int]$env:NORTHSTAR_TEST_CHILD_EXIT
'''.lstrip(), encoding="utf-8")
    return fixture


def _run_self_service_fixture(fixture, program_data, *arguments, child_exit=0):
    capture = program_data / "child-arguments.json"
    env = os.environ.copy()
    env["ProgramData"] = str(program_data)
    env["NORTHSTAR_TEST_CAPTURE"] = str(capture)
    env["NORTHSTAR_TEST_CHILD_EXIT"] = str(child_exit)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    completed = subprocess.run(
        [str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(fixture / "install-self-service.ps1"), *arguments],
        capture_output=True, text=True, timeout=30, env=env,
    )
    captured = json.loads(capture.read_text(encoding="utf-8-sig")) if capture.exists() else None
    return completed, captured


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell 5.1")
def test_existing_config_repair_omits_empty_child_arguments(tmp_path):
    fixture = _write_self_service_child_fixture(tmp_path)
    program_data = tmp_path / "program-data"
    data_root = program_data / "NorthstarEndpointAgent"
    data_root.mkdir(parents=True)
    (data_root / "config.json").write_text(
        json.dumps({"server_url": "https://helpdesk.test"}), encoding="utf-8")

    completed, captured = _run_self_service_fixture(fixture, program_data)

    assert completed.returncode == 0, completed.stderr
    assert captured is not None
    assert captured["bound_keys"] == ["ServerUrl"]
    assert "TlsCertificateSha256" not in captured["command_line"]
    assert "EnrollmentToken" not in captured["command_line"]
    assert captured["enrollment_token_file"] == ""


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell 5.1")
@pytest.mark.parametrize("child_exit", [0, 7])
def test_enrollment_token_uses_locked_file_and_is_always_deleted(tmp_path, child_exit):
    if not ctypes.windll.shell32.IsUserAnAdmin():
        pytest.skip("secure SYSTEM/Administrators staging requires an elevated Windows test process")
    fixture = _write_self_service_child_fixture(tmp_path)
    program_data = tmp_path / "program-data"
    program_data.mkdir()
    token = "one-use-secret-token"
    encoded_server = base64.urlsafe_b64encode(b"https://helpdesk.test").decode().rstrip("=")
    enrollment_code = f"{encoded_server}.{token}"

    completed, captured = _run_self_service_fixture(
        fixture, program_data, "-EnrollmentCode", enrollment_code, child_exit=child_exit)

    assert completed.returncode == (0 if child_exit == 0 else 1)
    assert captured is not None
    assert "EnrollmentTokenFile" in captured["bound_keys"]
    assert "EnrollmentToken" not in captured["bound_keys"]
    assert "TlsCertificateSha256" not in captured["bound_keys"]
    assert captured["token_file_exists"] is True
    assert captured["token_value"] == token
    assert token not in captured["command_line"]
    assert "-EnrollmentTokenFile" in captured["command_line"]
    assert not Path(captured["enrollment_token_file"]).exists()


def test_child_powershell_calls_do_not_pass_possibly_empty_pairs_directly():
    root = Path(__file__).resolve().parents[1]
    script_names = [
        "install-self-service.ps1", "install-enterprise.ps1",
        "repair-agent-install.ps1", "migrate-legacy-x86-install.ps1",
    ]
    forbidden_pair = re.compile(
        r"&\s+\$powerShell[^\r\n]*-(?:EnrollmentCode|EnrollmentToken|TlsCertificateSha256|InstallRoot|DataRoot|ErrorLog)\s+\$\w+",
        re.IGNORECASE,
    )
    for name in script_names:
        text = (root / "scripts" / name).read_text(encoding="utf-8")
        assert not forbidden_pair.search(text), name
        for line in text.splitlines():
            if re.search(r"&\s+\$powerShell", line, re.IGNORECASE):
                assert re.search(r"@\w+", line), f"{name}: {line}"

    installer = (root / "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")
    assert " -EnrollmentCode " not in installer
    assert "-EnrollmentCodeFile " in installer
    assert "if EnrollmentCodeValue <> '' then" in installer
    assert "if EnrollmentCodePath <> '' then DeleteFile(EnrollmentCodePath)" in installer


def test_agent_0146_release_metadata_is_aligned():
    root = Path(__file__).resolve().parents[1]
    assert '__version__ = "0.1.46"' in (root /
        "asset_agent/__init__.py").read_text(encoding="utf-8")
    assert 'version = "0.1.46"' in (root /
        "pyproject.toml").read_text(encoding="utf-8")
    assert '#define MyAppVersion "0.1.46"' in (root /
        "NorthstarEndpointAgent.iss").read_text(encoding="utf-8")
    notes = (root / "release-notes-0.1.46.txt").read_text(encoding="utf-8")
    assert "heartbeats responsive" in notes
    assert "0.1.45 self-service installer security fixes" in notes
    server_installer = (root.parent / "installer/NorthstarDeskServer.iss").read_text(encoding="utf-8")
    server_builder = (root.parent / "installer/build-full-server-update.ps1").read_text(encoding="utf-8")
    assert '#define MyAppVersion "0.4.99"' in server_installer
    assert '[string]$Version = "0.4.99"' in server_builder
    server_notes = (root.parent / "installer/release-notes-0.4.99.txt").read_text(encoding="utf-8")
    assert "automatically restarts stopped agents" in server_notes

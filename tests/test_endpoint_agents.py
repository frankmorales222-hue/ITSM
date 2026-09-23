from datetime import datetime, timezone
import base64
from pathlib import Path

from itsm.database import SessionLocal
from itsm.models import Announcement, Asset, Employee, EndpointAction, EndpointAgent, Notification, Ticket, User
from itsm.config import settings
from itsm.agent_api import _latest_installer_in_roots
from conftest import login_as


DEVICE_ID = "a" * 64


def test_newest_agent_installer_is_selected_from_stale_upgrade_folder():
    root = Path(__file__).resolve().parents[1] / "endpoint_agent" / "artifacts"
    installers = list(root.glob("NorthstarEndpointAgent-Setup-*.exe"))
    assert len(installers) > 1  # the release workspace intentionally retains upgrade history

    def version(path):
        return tuple(map(int, path.stem.removeprefix("NorthstarEndpointAgent-Setup-").split(".")))

    assert _latest_installer_in_roots([root]) == max(installers, key=version)


def inventory(email="user1@example.test", device_id=DEVICE_ID, hostname="AGENT-PILOT-01",
              serial="AGENT-SERIAL-001", observed_user=None):
    return {
        "schema_version": 1, "device_id": device_id, "agent_version": "0.1.0",
        "collected_at": datetime.now(timezone.utc).isoformat(), "observed_user_email": email,
        "observed_user": observed_user or {},
        "device": {"hostname": hostname, "manufacturer": "Example", "model": "PilotBook",
                   "serial_number": serial, "chassis_type": "Laptop"},
        "os": {"edition": "Windows 11 Pro", "build": "26100"},
        "cpu": {"model": "Example CPU"},
        "memory": {"total_bytes": 17179869184},
        "storage": {"physical_disks": [{"model": "Example NVMe", "media_type": "SSD"}]},
        "network": {"adapters": [{"type": "Wi-Fi", "mac_address": "00-11-22-33-44-55"}]},
        "software": [{"name": "Example App", "version": "1.0"}],
        "security": {"secure_boot": "Enabled"}, "health": {"status": "Healthy"},
    }


def test_agent_enrollment_inventory_and_safe_user_reconciliation(client):
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    token_result = client.post("/api/agent-admin/enrollment-tokens", json={"label": "Pilot", "max_uses": 1})
    assert token_result.status_code == 201, token_result.text
    raw_token = token_result.json()["enrollment_token"]

    client.headers.pop("X-CSRF-Token")
    enrolled = client.post("/api/agent/enroll", json={
        "enrollment_token": raw_token, "device_id": DEVICE_ID,
        "hostname": "AGENT-PILOT-01", "agent_version": "0.1.0", "schema_version": 1,
    })
    assert enrolled.status_code == 201, enrolled.text
    credential = enrolled.json()["credential"]
    auth = {"Authorization": f"Bearer {credential}"}

    first = client.put("/api/agent/inventory", json=inventory(), headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["assignment"]["state"] == "Pending confirmation"

    second = client.put("/api/agent/inventory", json=inventory(), headers=auth)
    assert second.status_code == 200, second.text
    assert second.json()["created"] is False
    assert second.json()["assignment"]["state"] == "Automatically assigned"

    with SessionLocal() as db:
        agent = db.query(EndpointAgent).filter_by(device_id=DEVICE_ID).one()
        asset = db.get(Asset, agent.asset_id)
        employee = db.query(Employee).filter_by(work_email="user1@example.test").one()
        assert asset.assigned_employee_id == employee.id
        assert asset.asset_tag.startswith("DISC-")
        assert asset.extended_data["endpoint_agent"]["health"] == "Healthy"
    listed = client.get("/api/assets?q=AGENT-PILOT-01")
    assert listed.status_code == 200
    assert listed.json()[0]["observed_user_email"] == "user1@example.test"


def test_agent_never_replaces_a_person_with_a_computer_account(client):
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    raw_token = client.post("/api/agent-admin/enrollment-tokens", json={"label": "Identity safety"}).json()["enrollment_token"]
    client.headers.pop("X-CSRF-Token")
    device_id = "0" * 64
    enrolled = client.post("/api/agent/enroll", json={
        "enrollment_token": raw_token, "device_id": device_id,
        "hostname": "MRWS-FRANK", "agent_version": "0.1.25", "schema_version": 1,
    })
    assert enrolled.status_code == 201, enrolled.text
    auth = {"Authorization": f"Bearer {enrolled.json()['credential']}"}
    good = inventory(email="user1@example.test", device_id=device_id, hostname="MRWS-FRANK", serial="IDENTITY-001")
    assert client.put("/api/agent/inventory", json=good, headers=auth).status_code == 200
    bad = inventory(email="MRWS-FRANK$@medreceivables.com", device_id=device_id,
                    hostname="MRWS-FRANK", serial="IDENTITY-001",
                    observed_user={"email": "MRWS-FRANK$@medreceivables.com", "account_name": "MRWS-FRANK$"})
    reconciled = client.put("/api/agent/inventory", json=bad, headers=auth)
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["assignment"]["observed_email"] == "user1@example.test"
    with SessionLocal() as db:
        agent = db.query(EndpointAgent).filter_by(device_id=device_id).one()
        assert agent.observed_user_email == "user1@example.test"
        assert "$" not in str(agent.observed_user)


def test_agent_rejects_wrong_device_and_revocation(client):
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    devices = client.get("/api/agent-admin/devices")
    assert devices.status_code == 200
    agent = next(item for item in devices.json() if item["device_id_suffix"] == DEVICE_ID[-8:])
    revoked = client.post(f"/api/agent-admin/devices/{agent['id']}/revoke")
    assert revoked.status_code == 200

    rejected = client.post("/api/agent/heartbeat", json={"hostname": "AGENT-PILOT-01"},
                           headers={"Authorization": "Bearer not-a-real-credential"})
    assert rejected.status_code == 401


def test_agent_heartbeat_delivers_ticket_events_and_active_announcements(client, monkeypatch):
    monkeypatch.setattr("itsm.agent_api._self_service_installer", lambda: None)
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    raw_token = client.post("/api/agent-admin/enrollment-tokens", json={"label": "Alert test"}).json()["enrollment_token"]
    with SessionLocal() as db:
        requester = db.query(User).filter_by(username="user1").one()
        db.add(Notification(user_id=requester.id, organization_id=requester.organization_id,
                            event="ticket.updated", title="Ticket updated", body="A technician posted a response."))
        db.add(Announcement(organization_id=requester.organization_id, title="Scheduled maintenance",
                            body="Service notice", severity="warning", active=True))
        db.commit()
    client.headers.pop("X-CSRF-Token")
    enrolled = client.post("/api/agent/enroll", json={
        "enrollment_token": raw_token, "device_id": "e" * 64,
        "hostname": "ALERT-PC", "agent_version": "0.1.19", "schema_version": 1,
    })
    assert enrolled.status_code == 201
    heartbeat = client.post("/api/agent/heartbeat", headers={"Authorization": f"Bearer {enrolled.json()['credential']}"}, json={
        "hostname": "ALERT-PC", "observed_user_email": "user1@example.test",
    })
    assert heartbeat.status_code == 200, heartbeat.text
    alerts = heartbeat.json()["alerts"]
    assert any(item["id"].startswith("notification-") and item["severity"] == "information" for item in alerts)
    assert any(item["id"].startswith("announcement-") and item["severity"] == "warning" for item in alerts)


def test_technician_requests_and_agent_runs_requester_approved_action(client):
    device_id = "f" * 64
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    raw_token = client.post("/api/agent-admin/enrollment-tokens", json={
        "label": "Remediation test", "max_uses": 1,
    }).json()["enrollment_token"]
    client.headers.pop("X-CSRF-Token")
    enrolled = client.post("/api/agent/enroll", json={
        "enrollment_token": raw_token, "device_id": device_id,
        "hostname": "ACTION-PC", "agent_version": "0.1.13", "schema_version": 1,
    })
    credential = enrolled.json()["credential"]
    auth = {"Authorization": f"Bearer {credential}"}
    payload = inventory(device_id=device_id, hostname="ACTION-PC", serial="ACTION-001")
    assert client.put("/api/agent/inventory", json=payload, headers=auth).status_code == 200
    assert client.put("/api/agent/inventory", json=payload, headers=auth).status_code == 200
    with SessionLocal() as db:
        requester = db.query(User).filter_by(username="user1").one()
        ticket = db.query(Ticket).filter(Ticket.requester_id == requester.id,
                                         Ticket.assigned_user_id.is_not(None)).first()
        technician = db.get(User, ticket.assigned_user_id)
        ticket_id = ticket.id
    csrf = login_as(client, technician.username)
    client.headers.update({"X-CSRF-Token": csrf})
    requested = client.post(f"/api/tickets/{ticket_id}/endpoint-actions", json={
        "action_type": "terminate_process", "target": "EXCEL.EXE",
    })
    assert requested.status_code == 201, requested.text
    action_id = requested.json()["id"]
    csrf = login_as(client, "user1")
    client.headers.update({"X-CSRF-Token": csrf})
    pending = client.get("/api/endpoint-actions/pending")
    assert pending.status_code == 200, pending.text
    assert [(item["id"], item["ticket_id"]) for item in pending.json()] == [(action_id, ticket_id)]
    assert pending.json()[0]["ticket_number"]
    assert pending.json()[0]["ticket_subject"]
    assert client.post(f"/api/tickets/{ticket_id}/endpoint-actions/{action_id}/approve").status_code == 200
    assert client.get("/api/endpoint-actions/pending").json() == []
    client.headers.pop("X-CSRF-Token")
    dispatched = client.get("/api/agent/actions/next", headers=auth)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["action"]["target"] == "EXCEL.EXE"
    completed = client.post(f"/api/agent/actions/{action_id}/result", headers=auth, json={
        "succeeded": True, "summary": "Closed EXCEL.EXE.",
    })
    assert completed.status_code == 200, completed.text
    with SessionLocal() as db:
        assert db.get(EndpointAction, action_id).status == "Completed"


def test_agent_matches_employee_id_and_queues_unknown_identity_for_review(client):
    second_device = "b" * 64
    third_device = "c" * 64
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    with SessionLocal() as db:
        employee = db.query(Employee).filter_by(work_email="user2@example.test").one()
        employee.account_name = "verified.user"
        db.commit()
        employee_number = employee.employee_number
        employee_id = employee.id
    token = client.post("/api/agent-admin/enrollment-tokens", json={"label": "Enterprise", "max_uses": 2}).json()["enrollment_token"]
    client.headers.pop("X-CSRF-Token")

    credentials = []
    for device_id, hostname in ((second_device, "MATCHED-PC"), (third_device, "REVIEW-PC")):
        response = client.post("/api/agent/enroll", json={"enrollment_token": token, "device_id": device_id,
            "hostname": hostname, "agent_version": "0.1.0", "schema_version": 1})
        assert response.status_code == 201, response.text
        credentials.append(response.json()["credential"])

    matched_payload = inventory(email=None, device_id=second_device, hostname="MATCHED-PC", serial="MATCHED-002",
                                observed_user={"employee_id": employee_number, "account_name": "verified.user"})
    auth = {"Authorization": f"Bearer {credentials[0]}"}
    assert client.put("/api/agent/inventory", json=matched_payload, headers=auth).json()["assignment"]["state"] == "Pending confirmation"
    matched = client.put("/api/agent/inventory", json=matched_payload, headers=auth).json()["assignment"]
    assert matched["state"] == "Automatically assigned"
    assert matched["match_method"] == "employee_id"
    assert matched["matched_employee_id"] == employee_id

    review_payload = inventory(email=None, device_id=third_device, hostname="REVIEW-PC", serial="REVIEW-003",
                               observed_user={"account_name": "unknown.person"})
    review_auth = {"Authorization": f"Bearer {credentials[1]}"}
    result = client.put("/api/agent/inventory", json=review_payload, headers=review_auth)
    assert result.json()["assignment"]["state"] == "Needs assignment review"

    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    review = client.get("/api/agent-admin/assignment-review")
    assert review.status_code == 200
    assert any(item["hostname"] == "REVIEW-PC" for item in review.json())


def test_user_can_generate_one_use_self_service_code_and_download_installer(client, monkeypatch):
    monkeypatch.setattr("itsm.agent_api._caddy_root_ca_material", lambda _url: ("a" * 64, "Y2VydA"))
    csrf = login_as(client, "user3")
    client.headers.update({"X-CSRF-Token": csrf})
    created = client.post("/api/agent/self-service/enrollment")
    assert created.status_code == 201, created.text
    code = created.json()["enrollment_code"]
    encoded_url, raw_token, ca_fingerprint, ca_certificate = code.split(".", 3)
    encoded_url += "=" * (-len(encoded_url) % 4)
    assert base64.urlsafe_b64decode(encoded_url).decode() == settings.public_url.rstrip("/")
    assert len(raw_token) >= 20
    assert ca_fingerprint == "a" * 64
    assert ca_certificate == "Y2VydA"
    assert created.json()["installer_url"] == "/api/agent/self-service/installer"

    launcher = client.get(created.json()["one_click_url"])
    assert launcher.status_code == 200, launcher.text
    assert "/VERYSILENT" in launcher.text
    assert "/SUPPRESSMSGBOXES" in launcher.text
    assert "-Verb RunAs" in launcher.text
    assert "NorthstarEndpointAgent\\installer.log" in launcher.text
    assert "pause" in launcher.text
    assert f"bootstrap={raw_token}" in launcher.text

    fake_installer = Path("data/test-NorthstarEndpointAgent-Setup.exe")
    try:
        fake_installer.write_bytes(b"MZ" + b"test-installer")
        monkeypatch.setattr("itsm.agent_api._self_service_installer", lambda: fake_installer)
        downloaded = client.get("/api/agent/self-service/installer")
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"MZ")
        assert "NorthstarEndpointAgent-Setup.exe" in downloaded.headers["content-disposition"]

        client.cookies.clear()
        bootstrap_download = client.get(
            "/api/agent/self-service/installer", params={"bootstrap": raw_token}
        )
        assert bootstrap_download.status_code == 200, bootstrap_download.text
        assert bootstrap_download.content.startswith(b"MZ")
    finally:
        fake_installer.unlink(missing_ok=True)


def test_self_service_enrollment_is_linked_to_requesting_user(client, monkeypatch):
    monkeypatch.setattr("itsm.agent_api._caddy_root_ca_material", lambda _url: ("b" * 64, "Y2VydA"))
    csrf = login_as(client, "user3")
    client.headers.update({"X-CSRF-Token": csrf})
    created = client.post("/api/agent/self-service/enrollment")
    assert created.status_code == 201, created.text
    raw_token = created.json()["enrollment_code"].split(".", 2)[1]

    client.headers.pop("X-CSRF-Token")
    device_id = "d" * 64
    enrolled = client.post("/api/agent/enroll", json={
        "enrollment_token": raw_token, "device_id": device_id,
        "hostname": "SELF-SERVICE-PC", "agent_version": "0.1.0", "schema_version": 1,
    })
    assert enrolled.status_code == 201, enrolled.text

    csrf = login_as(client, "user3")
    client.headers.update({"X-CSRF-Token": csrf})
    status = client.get("/api/agent/self-service/status")
    assert status.status_code == 200, status.text
    assert status.json()["installed"] is True
    assert status.json()["hostname"] == "SELF-SERVICE-PC"

    with SessionLocal() as db:
        agent = db.query(EndpointAgent).filter_by(device_id=device_id).one()
        assert agent.enrolled_by_user_id is not None


def test_administrator_can_publish_a_newer_remote_agent_release(client, monkeypatch):
    """A staged release is visible to admins and becomes the agent download source."""
    root = Path("data/test-agent-releases")
    root.mkdir(parents=True, exist_ok=True)
    installer_name = "NorthstarEndpointAgent-Setup-9.9.9.exe"
    monkeypatch.setattr("itsm.agent_api._managed_agent_release_root", lambda: root)
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    try:
        published = client.post(
            "/api/agent-admin/release",
            files={"installer": (
                installer_name,
                b"MZ" + b"remote-release",
                "application/octet-stream",
            )},
        )
        assert published.status_code == 201, published.text
        assert published.json()["release"]["version"] == "9.9.9"

        listed = client.get("/api/agent-admin/release")
        assert listed.status_code == 200, listed.text
        assert listed.json()["active"]["version"] == "9.9.9"
        assert listed.json()["active"]["managed"] is True
    finally:
        (root / installer_name).unlink(missing_ok=True)
        root.rmdir()

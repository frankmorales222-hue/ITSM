from datetime import timedelta

from sqlalchemy import select

from conftest import login_as
from itsm.database import SessionLocal
from itsm.models import Asset, ServiceCategory, Ticket, TicketAttachment


def incident_payload(config, **changes):
    hardware = next(item for item in config["categories"] if item["name"] == "Hardware" and item["parent_id"] is None)
    payload = {
        "client_request_id": "incident_vertical_slice_001",
        "request_type": "Incident", "status": "Open", "mode": "Web Form", "level": "Tier 1",
        "impact": "High", "impact_details": "The user cannot perform scheduled work.", "urgency": "High",
        "category_id": hardware["id"], "subject": "Laptop will not start after update",
        "description": "The assigned laptop displays a blank screen after the approved update and a restart.",
        "emails_to_notify": ["manager@example.test"], "asset_ids": [],
        "form_definition_id": config["default_form"]["id"],
    }
    payload.update(changes)
    return payload


def test_incident_vertical_slice_calculates_routes_selects_sla_and_audits(client):
    csrf = login_as(client, "user1")
    client.headers.update({"X-CSRF-Token": csrf})
    config_response = client.get("/api/incidents/config")
    assert config_response.status_code == 200, config_response.text
    config = config_response.json()
    assets = client.get("/api/lookups/assets").json()
    payload = incident_payload(config, asset_ids=[assets[0]["id"]] if assets else [])
    created = client.post("/api/incidents", json=payload)
    assert created.status_code == 201, created.text
    result = created.json()["ticket"]
    assert result["priority"] == "Critical"
    assert result["calculated_priority"] == "Critical"
    assert result["priority_source"] == "calculated"
    assert "Impact = High" in result["priority_explanation"]
    assert result["sla_policy_key"] == "critical"
    assert result["team"] == "Endpoint Services"
    assert "Route hardware incidents" in result["route_reason"]
    response_due = result["first_response_due"]
    resolution_due = result["resolution_due"]
    from datetime import datetime
    assert datetime.fromisoformat(resolution_due) - datetime.fromisoformat(response_due) == timedelta(minutes=45)

    detail = client.get(f"/api/tickets/{result['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "Open"
    assert body["routing_trace"][0]["matched"] is True
    assert body["sla_explanation"].startswith("Critical SLA")

    duplicate = client.post("/api/incidents", json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["ticket"]["id"] == result["id"]

    with SessionLocal() as db:
        ticket = db.get(Ticket, result["id"])
        assert ticket.priority_source == "calculated"
        assert ticket.requester_snapshot["requested_for_id"] == ticket.requester_id


def test_incident_dependency_asset_and_priority_override_permissions(client):
    csrf = login_as(client, "user2")
    client.headers.update({"X-CSRF-Token": csrf})
    config = client.get("/api/incidents/config").json()
    general = next(item for item in config["categories"] if item["name"] == "General" and item["parent_id"] is None)
    wrong_child = next(item for item in config["categories"] if item["parent_id"])
    invalid_chain = client.post("/api/incidents", json=incident_payload(config, client_request_id="incident_invalid_chain",
                                                                        category_id=general["id"], subcategory_id=wrong_child["id"]))
    assert invalid_chain.status_code == 422
    assert "does not belong" in invalid_chain.text

    forbidden_override = client.post("/api/incidents", json=incident_payload(
        config, client_request_id="incident_override_forbidden", priority_override="Low", priority_override_reason="Manager request"))
    assert forbidden_override.status_code == 403

    assigned = {item["id"] for item in client.get("/api/lookups/assets").json()}
    with SessionLocal() as db:
        another = db.scalar(select(Asset).where(Asset.id.not_in(assigned)))
    forbidden_asset = client.post("/api/incidents", json=incident_payload(
        config, client_request_id="incident_asset_forbidden", asset_ids=[another.id]))
    assert forbidden_asset.status_code == 403


def test_admin_can_override_priority_and_configuration_requires_complete_matrix(admin):
    config = admin.get("/api/incidents/config").json()
    created = admin.post("/api/incidents", json=incident_payload(
        config, client_request_id="incident_admin_override", priority_override="High",
        priority_override_reason="Known executive event requires coordinated response"))
    assert created.status_code == 201, created.text
    assert created.json()["ticket"]["priority"] == "High"
    assert created.json()["ticket"]["calculated_priority"] == "Critical"
    assert created.json()["ticket"]["priority_source"] == "overridden"

    settings = admin.get("/api/admin/incident-settings").json()
    settings["priority_matrix"]["cells"].pop("High|High")
    invalid = admin.put("/api/admin/incident-settings", json=settings)
    assert invalid.status_code == 422
    assert "Complete every priority matrix cell" in invalid.text


def test_incident_attachment_validation_and_storage(client):
    csrf = login_as(client, "user3")
    client.headers.update({"X-CSRF-Token": csrf})
    config = client.get("/api/incidents/config").json()
    created = client.post("/api/incidents", json=incident_payload(config, client_request_id="incident_attachment_test"))
    ticket_id = created.json()["ticket"]["id"]
    rejected = client.post(f"/api/incidents/{ticket_id}/attachments", files={"files": ("payload.exe", b"unsafe", "application/octet-stream")})
    assert rejected.status_code == 422
    uploaded = client.post(f"/api/incidents/{ticket_id}/attachments", files={"files": ("evidence.txt", b"diagnostic output", "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()[0]["id"]
    downloaded = client.get(f"/api/incidents/{ticket_id}/attachments/{attachment_id}")
    assert downloaded.status_code == 200
    assert downloaded.content == b"diagnostic output"
    with SessionLocal() as db:
        item = db.get(TicketAttachment, attachment_id)
        path = __import__("pathlib").Path("data/attachments") / item.storage_name
        path.unlink(missing_ok=True)

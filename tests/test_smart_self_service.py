from datetime import timedelta

from conftest import login_as
from sqlalchemy import select

from itsm.database import SessionLocal
from itsm.models import ConfigItem, KnowledgeArticle, KnowledgeArticleVersion, SelfServiceAttempt, Ticket, TicketMessage, TicketStatus, now
from itsm.self_service import email_outcome_command, exclusion_reason, policy_for, return_unanswered_to_it
from itsm.worker import smart_self_service_job


def test_smart_self_service_is_safe_versioned_and_end_to_end(client, admin):
    overview = admin.get("/api/admin/smart-self-service")
    assert overview.status_code == 200, overview.text
    assert overview.json()["settings"]["enabled"] is False

    created = admin.post("/api/admin/smart-self-service/articles", json={
        "title": "Excel application frozen recovery",
        "summary": "Safely close and reopen a frozen Excel application.",
        "steps": ["Save other open work.", "Close Excel from Task Manager, then reopen it."],
        "category": "General",
        "status": "draft",
        "tags": ["excel", "frozen", "not responding"],
        "applicability": {"categories": ["General"]},
        "risk_level": "low",
        "auto_send_allowed": True,
    })
    assert created.status_code == 201, created.text
    article = created.json()
    assert article["status"] == "draft"
    assert article["version"] == 1

    published = admin.post(f"/api/admin/smart-self-service/articles/{article['id']}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["version"] == 2
    versions = admin.get(f"/api/admin/smart-self-service/articles/{article['id']}/versions")
    assert [row["version"] for row in versions.json()] == [2, 1]

    saved = admin.put("/api/admin/smart-self-service", json={
        "enabled": True,
        "mode": "suggest_to_tech",
        "confidence_threshold": 45,
        "waiting_hours": 48,
        "safe_categories": ["General", "Hardware", "Software", "Network"],
        "excluded_categories": ["Security", "Access", "Change", "Outage"],
    })
    assert saved.status_code == 200, saved.text

    client.cookies.clear()
    csrf = login_as(client, "user1")
    client.headers.update({"X-CSRF-Token": csrf})
    ticket_response = client.post("/api/tickets", json={
        "request_type": "Report an issue",
        "subject": "Excel is frozen and not responding",
        "description": "Excel freezes when I open my normal workbook.",
        "asset_ids": [],
        "impact": "Low",
        "urgency": "Low",
    })
    assert ticket_response.status_code == 201, ticket_response.text
    ticket_id = ticket_response.json()["ticket"]["id"]

    # Requesters must not see an internal technician suggestion.
    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        db.info["organization_id"] = ticket.organization_id
        assert smart_self_service_job(db) >= 1
        db.commit()
        attempt = db.scalar(select(SelfServiceAttempt).where(SelfServiceAttempt.ticket_id == ticket_id))
        assert attempt and attempt.status == "suggested"
        attempt_id = attempt.id
    hidden = client.get(f"/api/tickets/{ticket_id}/self-service")
    assert hidden.status_code == 200
    assert hidden.json()["suggestion"] is None

    client.cookies.clear()
    csrf = login_as(client, "admin")
    client.headers.update({"X-CSRF-Token": csrf})
    sent = client.post(f"/api/tickets/{ticket_id}/self-service/{attempt_id}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "offered"

    client.cookies.clear()
    csrf = login_as(client, "user1")
    client.headers.update({"X-CSRF-Token": csrf})
    offered = client.get(f"/api/tickets/{ticket_id}/self-service")
    assert offered.status_code == 200
    assert offered.json()["suggestion"]["title"] == "Excel application frozen recovery"
    outcome = client.post(f"/api/tickets/{ticket_id}/self-service", json={"outcome": "not_fixed"})
    assert outcome.status_code == 200, outcome.text
    assert outcome.json()["status"] == "not_fixed"

    with SessionLocal() as db:
        ticket = db.get(Ticket, ticket_id)
        assert ticket.status in (TicketStatus.IN_PROGRESS, TicketStatus.NEW)
        article_row = db.get(KnowledgeArticle, article["id"])
        assert article_row is not None
        assert len(db.scalars(select(KnowledgeArticleVersion).where(
            KnowledgeArticleVersion.article_id == article_row.id)).all()) == 2
        high_risk = dict(policy_for(db)); high_risk["enabled"] = True
        ticket.restricted = True
        assert exclusion_reason(ticket, high_risk) == "restricted_ticket"
        ticket.restricted = False
        policy = db.scalar(select(ConfigItem).where(
            ConfigItem.section == "smart_self_service", ConfigItem.name == "Smart Self-Service"))
        policy.value = {**policy.value, "enabled": False}
        article_row.status = "archived"
        db.commit()


def test_end_user_cannot_manage_smart_self_service(client):
    client.cookies.clear()
    csrf = login_as(client, "user2")
    client.headers.update({"X-CSRF-Token": csrf})
    assert client.get("/api/admin/smart-self-service").status_code == 403
    assert client.put("/api/admin/smart-self-service", json={
        "enabled": True, "mode": "auto_send", "confidence_threshold": 1,
        "waiting_hours": 1, "safe_categories": [], "excluded_categories": [],
    }).status_code == 403


def test_email_outcome_commands_are_explicit_and_fail_closed():
    assert email_outcome_command("DID NOT WORK\n\nSent from Outlook") == "not_fixed"
    assert email_outcome_command("REQUEST LIVE HELP.") == "live_help"
    assert email_outcome_command("FIXED") == "fixed"
    assert email_outcome_command("I think this might be fixed, but I am not sure") is None
    assert email_outcome_command("Please do not close this request") is None


def test_unanswered_offer_returns_to_it_once(client, admin):
    admin.put("/api/admin/smart-self-service", json={
        "enabled": True, "mode": "suggest_to_tech", "confidence_threshold": 60,
        "waiting_hours": 1, "safe_categories": ["General"],
        "excluded_categories": ["Security", "Access", "Change", "Outage"],
    })
    with SessionLocal() as db:
        ticket = db.scalar(select(Ticket).where(Ticket.category == "General"))
        db.info["organization_id"] = ticket.organization_id
        ticket.status = TicketStatus.WAITING_USER
        article = KnowledgeArticle(
            title="Safe guidance", problem_summary="Safe requester guidance for testing.",
            steps=["Try again."], tags=["safe"], category="General", applicability={},
            risk_level="low", status="published", auto_send_allowed=False,
        )
        db.add(article); db.flush()
        attempt = SelfServiceAttempt(
            ticket_id=ticket.id, article_id=article.id, article_version=1, score=90,
            match_reason={}, article_snapshot={"title": "Safe guidance", "steps": ["Try again."]},
            status="offered", offered_at=now() - timedelta(hours=2),
        )
        db.add(attempt); db.commit(); attempt_id = attempt.id; ticket_id = ticket.id
        assert return_unanswered_to_it(db) == 1
        db.commit()
        assert db.get(SelfServiceAttempt, attempt_id).status == "timed_out"
        assert db.get(Ticket, ticket_id).status in (TicketStatus.IN_PROGRESS, TicketStatus.NEW)
        assert db.scalar(select(TicketMessage).where(
            TicketMessage.ticket_id == ticket_id,
            TicketMessage.source == "self_service",
        )) is not None
        assert return_unanswered_to_it(db) == 0

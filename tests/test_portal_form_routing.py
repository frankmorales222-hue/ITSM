from sqlalchemy import select

from itsm.database import SessionLocal
from itsm.models import (
    Organization,
    QueueTeamEligibility,
    Role,
    RoutingRule,
    SupportQueue,
    Team,
    TeamMembership,
    User,
)


def test_published_portal_form_uses_configured_domain_queue_and_round_robin(admin):
    """The Create New Ticket/Form Studio path must use the same routing engine as email."""
    with SessionLocal() as db:
        organization_id = db.scalar(select(Organization.id).order_by(Organization.id))
        db.info["organization_id"] = organization_id
        tech = db.scalar(select(User).where(User.role == Role.TECHNICIAN, User.active.is_(True)).order_by(User.id))
        assert tech is not None
        tech.availability = "Available"
        team = Team(
            organization_id=organization_id,
            name="Portal Routing Regression Team",
            queue_name="Portal Routing Regression Team",
            active=True,
        )
        db.add(team)
        db.flush()
        queue = SupportQueue(
            organization_id=organization_id,
            name="Portal Routing Regression Queue",
            team_id=team.id,
            assignment_strategy="round_robin",
            active=True,
        )
        db.add(queue)
        db.flush()
        db.add(TeamMembership(
            organization_id=organization_id,
            team_id=team.id,
            user_id=tech.id,
            active=True,
        ))
        db.add(QueueTeamEligibility(
            organization_id=organization_id,
            queue_id=queue.id,
            team_id=team.id,
            active=True,
        ))
        rule = RoutingRule(
            organization_id=organization_id,
            name="Portal Routing Regression Rule",
            priority_order=-100000,
            trigger="ticket.created",
            status="active",
            active=True,
            stop_processing=True,
            conditions={"logic": "OR", "conditions": [
                {"field": "channel", "operator": "equals", "value": "email"},
                {"field": "requester_domain", "operator": "equals", "value": "example.test"},
            ]},
            actions={"queue_id": queue.id, "team_id": None, "assignment_strategy": "round_robin"},
        )
        db.add(rule)
        db.commit()
        expected_team_id = team.id
        expected_tech_id = tech.id
        rule_id = rule.id

    form = admin.post("/api/admin/forms", json={
        "name": "Portal Routing Regression Form",
        "slug": "portal-routing-regression-form",
        "description": "Regression coverage for the Create New Ticket workflow",
        "category": "General",
        "icon": "support",
        "active": True,
        "published": True,
        "fields": [{
            "id": "details", "key": "details", "label": "Details", "type": "long_text",
            "required": True, "help": "", "options": [],
        }],
    })
    assert form.status_code == 201, form.text
    submitted = admin.post(f"/api/forms/{form.json()['id']}/submit", json={
        "subject": "Portal routing regression request",
        "values": {"details": "Created through the same endpoint used by Create New Ticket."},
        "impact": "Medium",
        "urgency": "Medium",
    })
    assert submitted.status_code == 201, submitted.text
    ticket = submitted.json()["ticket"]
    assert ticket["team_id"] == expected_team_id
    assert ticket["assigned_user_id"] == expected_tech_id
    assert "Portal Routing Regression Rule" in ticket["route_reason"]
    assert any(item.get("rule_id") == rule_id and item.get("matched") for item in ticket["routing_trace"])

    with SessionLocal() as db:
        db.info["organization_id"] = db.scalar(select(Organization.id).order_by(Organization.id))
        stored_rule = db.get(RoutingRule, rule_id)
        assert stored_rule.match_count == 1
        # Keep this session-scoped test database from affecting later routing tests.
        stored_rule.active = False
        stored_rule.status = "draft"
        db.commit()

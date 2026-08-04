import re
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .models import (ApprovalWorkflow, AuditEvent, AutomationFailure, ConfigItem, EmailMessage, FormDefinition,
                     Notification, Role, Sequence, SystemState, Team, Ticket, TicketHistory, TicketMessage,
                     TicketStatus, User, now)

PRIORITY_HOURS = {
    "Critical": (1, 4), "High": (4, 16), "Medium": (8, 40), "Low": (16, 80)
}
PRIORITY_MATRIX = {
    ("High", "High"): "Critical", ("High", "Medium"): "High", ("High", "Low"): "Medium",
    ("Medium", "High"): "High", ("Medium", "Medium"): "Medium", ("Medium", "Low"): "Low",
    ("Low", "High"): "Medium", ("Low", "Medium"): "Low", ("Low", "Low"): "Low",
}


def audit(db: Session, action: str, record_type: str, record_id=None, actor_id=None,
          previous=None, new=None, source_ip=None, correlation_id=None):
    db.add(AuditEvent(actor_id=actor_id, action=action, record_type=record_type,
                      record_id=str(record_id) if record_id is not None else None,
                      previous_value=previous, new_value=new, source_ip=source_ip,
                      correlation_id=correlation_id or str(uuid.uuid4())))


def next_ticket_number(db: Session, request_type: str) -> str:
    lowered = request_type.lower()
    prefix = "CHG" if "change" in lowered else "INC" if request_type == "Report an issue" or "incident" in lowered else "HR" if request_type == "New employee request" else "REQ"
    seq = db.get(Sequence, prefix)
    if not seq:
        seq = Sequence(prefix=prefix, value=0)
        db.add(seq)
    seq.value += 1
    db.flush()
    return f"{prefix}-{seq.value:06d}"


def priority_for(impact: str, urgency: str) -> str:
    return PRIORITY_MATRIX.get((impact, urgency), "Medium")


def sla_dates(priority: str, start: datetime | None = None) -> tuple[datetime, datetime]:
    start = start or now()
    first, resolution = PRIORITY_HOURS[priority]
    return start + timedelta(hours=first), start + timedelta(hours=resolution)


def route_ticket(db: Session, category: str, requester: User) -> tuple[Team, User | None, str]:
    teams = db.scalars(select(Team).order_by(Team.id)).all()
    team = next((t for t in teams if category.lower() in [s.lower() for s in (t.skills or [])]), None)
    reason = f"Skill match: {category}" if team else "Default queue fallback"
    team = team or next((t for t in teams if t.is_default), teams[0])
    techs = db.scalars(select(User).where(User.team_id == team.id, User.role.in_([Role.TECHNICIAN, Role.TEAM_LEAD]), User.active.is_(True), User.availability == "Available")).all()
    if not techs:
        return team, None, reason + "; no available technician"
    config = db.scalar(select(ConfigItem).where(ConfigItem.section == "assignment"))
    team_config = db.scalar(select(ConfigItem).where(ConfigItem.section == "teams"))
    method = (config.value or {}).get("method") if config else None
    method = method or ((team_config.value or {}).get("routing_mode") if team_config else None) or "least_active"
    if method == "manual":
        return team, None, reason + "; manual assignment configured"
    counts = dict(db.execute(select(Ticket.assigned_user_id, func.count(Ticket.id)).where(
        Ticket.assigned_user_id.in_([t.id for t in techs]),
        Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])
    ).group_by(Ticket.assigned_user_id)).all())
    if method == "round_robin":
        techs = sorted(techs, key=lambda t: t.id)
        state_key = f"round_robin_team_{team.id}"
        state = db.get(SystemState, state_key)
        last_id = (state.value or {}).get("last_user_id") if state else None
        eligible_ids = [t.id for t in techs]
        next_index = (eligible_ids.index(last_id) + 1) % len(techs) if last_id in eligible_ids else 0
        tech = techs[next_index]
        if not state:
            state = SystemState(key=state_key, value={})
            db.add(state)
        state.value = {"last_user_id": tech.id, "last_assigned_at": now().isoformat()}
        return team, tech, reason + f"; round-robin selected {tech.display_name}"
    tech = min(techs, key=lambda t: (counts.get(t.id, 0), t.id))
    return team, tech, reason + f"; least-active selected {tech.display_name} ({counts.get(tech.id, 0)} active)"


def can_view_ticket(user: User, ticket: Ticket) -> bool:
    if user.role == Role.END_USER:
        return ticket.requester_id == user.id
    if user.role == Role.AUDITOR:
        return not ticket.restricted
    if ticket.restricted and user.role not in (Role.ADMIN, Role.MANAGER):
        return ticket.assigned_user_id == user.id
    if user.role in (Role.TECHNICIAN, Role.TEAM_LEAD):
        return ticket.team_id == user.team_id
    return True


def visible_ticket_filter(user: User):
    if user.role == Role.END_USER:
        return Ticket.requester_id == user.id
    if user.role == Role.AUDITOR:
        return Ticket.restricted.is_(False)
    if user.role in (Role.TECHNICIAN, Role.TEAM_LEAD):
        return or_(Ticket.team_id == user.team_id, Ticket.assigned_user_id == user.id)
    return True


def notify(db: Session, user_id: int | None, event: str, title: str, body: str, ticket_id=None, email=False):
    if user_id:
        db.add(Notification(user_id=user_id, ticket_id=ticket_id, event=event, title=title, body=body,
                            delivery_status="pending_email" if email else "in_app"))
        audit(db, "notification.created", "notification", ticket_id,
              new={"event": event, "user_id": user_id, "email_requested": email})


FORM_FIELD_TYPES = {"short_text", "long_text", "select", "multi_select", "date", "number",
                    "checkbox", "email", "asset", "user", "section"}


def validate_form_fields(fields: list[dict]) -> list[dict]:
    clean: list[dict] = []
    keys: set[str] = set()
    for index, raw in enumerate(fields):
        field_type = str(raw.get("type", "short_text"))
        key = str(raw.get("key", "")).strip().lower()
        label = str(raw.get("label", "")).strip()
        if field_type not in FORM_FIELD_TYPES:
            raise ValueError(f"Unsupported field type at position {index + 1}")
        if field_type != "section" and (not re.fullmatch(r"[a-z][a-z0-9_]{1,59}", key) or key in keys):
            raise ValueError(f"Field {index + 1} needs a unique key using letters, numbers, and underscores")
        if not label or len(label) > 160:
            raise ValueError(f"Field {index + 1} needs a label")
        options = [str(item).strip()[:120] for item in raw.get("options", []) if str(item).strip()]
        if field_type in {"select", "multi_select"} and not options:
            raise ValueError(f"{label} needs at least one option")
        if field_type != "section":
            keys.add(key)
        clean.append({"id": str(raw.get("id") or uuid.uuid4()), "key": key, "label": label,
                      "type": field_type, "required": bool(raw.get("required", False)),
                      "help": str(raw.get("help", ""))[:500], "options": options})
    return clean


def validate_form_submission(form: FormDefinition, values: dict) -> dict:
    result: dict = {}
    allowed = {field["key"]: field for field in form.fields if field.get("type") != "section"}
    for key, field in allowed.items():
        value = values.get(key)
        empty = value is None or value == "" or value == []
        if field.get("required") and empty:
            raise ValueError(f"{field['label']} is required")
        if empty:
            continue
        field_type = field["type"]
        if field_type == "checkbox":
            result[key] = bool(value)
        elif field_type == "number":
            try: result[key] = float(value)
            except (TypeError, ValueError): raise ValueError(f"{field['label']} must be a number")
        elif field_type == "email":
            text_value = str(value).strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text_value):
                raise ValueError(f"{field['label']} must be an email address")
            result[key] = text_value[:255]
        elif field_type == "multi_select":
            selected = value if isinstance(value, list) else [value]
            if any(item not in field.get("options", []) for item in selected):
                raise ValueError(f"{field['label']} contains an invalid option")
            result[key] = selected
        elif field_type == "select":
            if value not in field.get("options", []): raise ValueError(f"{field['label']} contains an invalid option")
            result[key] = value
        else:
            result[key] = str(value)[:20000 if field_type == "long_text" else 500]
    return result


def workflow_approver(db: Session, workflow: ApprovalWorkflow, step_index: int) -> User | None:
    if step_index >= len(workflow.steps):
        return None
    step = workflow.steps[step_index]
    if step.get("approver_user_id"):
        user = db.get(User, int(step["approver_user_id"]))
        return user if user and user.active else None
    role_name = step.get("approver_role", "manager")
    try: role = Role(role_name)
    except ValueError: return None
    return db.scalar(select(User).where(User.role == role, User.active.is_(True)).order_by(User.id))


def sensitive_warnings(text: str) -> list[str]:
    warnings = []
    patterns = {
        "Possible Social Security number": r"\b\d{3}-\d{2}-\d{4}\b",
        "Possible password or credential": r"(?i)\b(password|passwd|api[_ -]?key|secret)\s*[:=]",
        "Possible medical information": r"(?i)\b(diagnosis|patient|medical record|medication|treatment)\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, text): warnings.append(label)
    return warnings


def is_automated_email(headers: dict[str, str], subject: str) -> bool:
    blob = " ".join(f"{k}:{v}" for k, v in headers.items()).lower()
    return any(x in blob for x in ["auto-submitted:auto-replied", "x-autoreply:", "precedence:bulk", "mailer-daemon"]) or subject.lower().startswith(("out of office", "automatic reply", "undeliverable"))


def fail_automation(db: Session, kind: str, summary: str, details: dict, related_type=None, related_id=None):
    safe = {k: v for k, v in details.items() if not any(s in k.lower() for s in ["password", "token", "secret"])}
    failure = AutomationFailure(failure_type=kind, summary=summary, safe_details=safe,
                                related_type=related_type, related_id=str(related_id) if related_id else None)
    db.add(failure)
    audit(db, "automation.failed", "automation_failure", None, new={"type": kind, "summary": summary})
    return failure

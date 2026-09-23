import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from .config import settings
from .models import (ApprovalRequest, ApprovalWorkflow, AuditEvent, AutomationFailure, ConfigItem, EmailMessage, Employee, FormDefinition,
                     Notification, NotificationRule, QueueTeamEligibility, Role, RoutingRule, Sequence, SupportQueue, SystemState,
                     Team, TeamMembership, Ticket, TicketChatSession, TicketHistory, TicketMessage, TicketStatus, User, UserGroupMembership, now)

PRIORITY_HOURS = {
    "Critical": (1, 4), "High": (4, 16), "Medium": (8, 40), "Low": (16, 80)
}
PRIORITY_MATRIX = {
    ("High", "High"): "Critical", ("High", "Medium"): "High", ("High", "Low"): "Medium",
    ("Medium", "High"): "High", ("Medium", "Medium"): "Medium", ("Medium", "Low"): "Low",
    ("Low", "High"): "Medium", ("Low", "Medium"): "Low", ("Low", "Low"): "Low",
}
TICKET_REFERENCE_PATTERN = re.compile(r"(?<![A-Z0-9])(?:REQ|INC|CHG|HR)-\d+(?![A-Z0-9])", re.IGNORECASE)


def ticket_number_from_email_subject(subject: str | None) -> str | None:
    """Return the stable Northstar ticket reference carried in an email subject."""
    match = TICKET_REFERENCE_PATTERN.search(subject or "")
    return match.group(0).upper() if match else None


def ticket_from_email_subject(db: Session, subject: str | None) -> Ticket | None:
    number = ticket_number_from_email_subject(subject)
    return db.scalar(select(Ticket).where(Ticket.number == number)) if number else None


def ticket_from_reply_subject(db: Session, subject: str | None, requester_id: int) -> Ticket | None:
    """Safely recover a thread when an older mail client omitted reply headers.

    This fallback is intentionally narrow: the inbound subject must contain a
    recognized reply prefix and must match exactly one ticket for the same
    requester.  A normal new email, or an ambiguous repeated subject, remains
    a new ticket.
    """
    raw = " ".join((subject or "").split())
    reply_prefix = re.compile(r"^(?:(?:re|aw|sv)\s*:\s*)+", re.IGNORECASE)
    if not reply_prefix.match(raw):
        return None
    normalized = reply_prefix.sub("", raw).strip().casefold()
    if not normalized:
        return None
    candidates = db.scalars(
        select(Ticket).where(Ticket.requester_id == requester_id)
        .order_by(Ticket.created_at.desc()).limit(200)
    ).all()
    matches = [ticket for ticket in candidates
               if " ".join((ticket.subject or "").split()).strip().casefold() == normalized]
    return matches[0] if len(matches) == 1 else None


def ticket_email_subject(ticket: Ticket | None, requested_subject: str | None) -> str:
    """Guarantee that every ticket email carries the reference used for reply threading."""
    subject = " ".join((requested_subject or (ticket.subject if ticket else "Northstar Desk notification")).split())
    if not ticket:
        return subject[:240]
    if ticket.number.lower() not in subject.lower():
        subject = f"[{ticket.number}] {subject}"
    return subject[:240]


def inbound_email_routing_sample(db: Session, requester: User, sender: str, subject: str, body: str) -> dict:
    """Build the same routing facts for mailbox tickets that portal tickets use."""
    normalized_email = (sender or requester.email or "").strip().lower()
    domain = normalized_email.rsplit("@", 1)[1] if "@" in normalized_email else ""
    employee = db.scalar(select(Employee).where(func.lower(Employee.work_email) == normalized_email)) if normalized_email else None
    return {
        "organization": str(requester.organization_id),
        "requester": normalized_email,
        "requester_email": normalized_email,
        "requester_domain": domain,
        "requester_department": employee.department.name if employee and employee.department else "",
        "location_name": employee.location.name if employee and employee.location else "",
        "vip": bool(employee.vip) if employee else False,
        "channel": "email",
        "request_type": "Report an issue",
        "category": "General",
        "priority": "Medium",
        "impact": "Medium",
        "urgency": "Medium",
        "keywords": f"{subject}\n{body}".strip(),
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


def configured_priority(db: Session, impact: str, urgency: str) -> tuple[str, str]:
    config = db.scalar(select(ConfigItem).where(ConfigItem.section == "incident_priority_matrix"))
    cells = (config.value or {}).get("cells", {}) if config else {}
    priority = cells.get(f"{impact}|{urgency}") or priority_for(impact, urgency)
    return priority, f"{priority} because Impact = {impact} and Urgency = {urgency}."


def configured_sla_dates(db: Session, priority: str, start: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    start = start or now()
    config = db.scalar(select(ConfigItem).where(ConfigItem.section == "incident_sla"))
    policies = (config.value or {}).get("policies", []) if config else []
    policy = next((item for item in policies if item.get("active", True) and item.get("priority") == priority), None)
    if not policy:
        first, resolution = sla_dates(priority if priority in PRIORITY_HOURS else "Medium", start)
        return first, resolution, "legacy-default", f"Default SLA selected for {priority}."
    response_minutes = max(1, int(policy.get("response_minutes", 60)))
    resolution_minutes = max(response_minutes, int(policy.get("resolution_minutes", 240)))
    calendar_key = str(policy.get("calendar") or "24x7")
    calendar = next((item for item in (config.value or {}).get("calendars", []) if item.get("key") == calendar_key), None) if config else None
    if not calendar and calendar_key not in {"", "24x7"}:
        legacy = db.scalar(select(ConfigItem).where(ConfigItem.section == "calendar"))
        calendar = legacy.value if legacy else None
    first = add_operational_minutes(start, response_minutes, calendar)
    resolution = add_operational_minutes(start, resolution_minutes, calendar)
    calendar_name = (calendar or {}).get("name") or calendar_key
    explanation = f"{policy.get('name', priority)} SLA: respond in {response_minutes} operational minutes and resolve in {resolution_minutes} operational minutes using {calendar_name}."
    return first, resolution, str(policy.get("key") or priority.lower()), explanation


def add_operational_minutes(start: datetime, minutes: int, calendar: dict | None) -> datetime:
    """Add working minutes using a time-zone aware weekly calendar and holiday list."""
    if not calendar or calendar.get("always_open") or calendar.get("key") == "24x7":
        return start + timedelta(minutes=minutes)
    try: zone = ZoneInfo(str(calendar.get("timezone") or "UTC"))
    except ZoneInfoNotFoundError: zone = timezone.utc
    current = (start if start.tzinfo else start.replace(tzinfo=timezone.utc)).astimezone(zone)
    day_names = calendar.get("days") or ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    allowed = {str(day).lower() for day in day_names}
    holidays = {str(day) for day in (calendar.get("holidays") or [])}
    start_parts = [int(part) for part in str(calendar.get("start") or "08:00").split(":")[:2]]
    end_parts = [int(part) for part in str(calendar.get("end") or "17:00").split(":")[:2]]
    remaining = max(0, int(minutes))
    for _ in range(3700):
        working_day = current.strftime("%A").lower() in allowed and current.date().isoformat() not in holidays
        opening = current.replace(hour=start_parts[0], minute=start_parts[1], second=0, microsecond=0)
        closing = current.replace(hour=end_parts[0], minute=end_parts[1], second=0, microsecond=0)
        if working_day and closing > opening:
            if current < opening: current = opening
            if current < closing:
                available = max(0, int((closing-current).total_seconds() // 60))
                if remaining <= available: return (current + timedelta(minutes=remaining)).astimezone(timezone.utc)
                remaining -= available
        current = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError("SLA calendar has no usable operational time")


def sla_pause_transition(db: Session, ticket: Ticket, previous_status: str, next_status: str) -> None:
    config = db.scalar(select(ConfigItem).where(ConfigItem.section == "incident_sla"))
    policies = (config.value or {}).get("policies", []) if config else []
    policy = next((item for item in policies if item.get("key") == ticket.sla_policy_key), {})
    configured_pauses = policy.get("pause_statuses") or [value for item in policies for value in item.get("pause_statuses", [])]
    paused_statuses = {str(value).lower() for value in (configured_pauses or ["On Hold", "Waiting on User", "Waiting on Vendor", "Waiting on Approval"])}
    data = dict(ticket.custom_data or {})
    was_paused = previous_status.lower() in paused_statuses
    is_paused = next_status.lower() in paused_statuses
    if is_paused and not was_paused and not data.get("sla_paused_at"):
        data["sla_paused_at"] = now().isoformat()
        data.setdefault("sla_pause_events", []).append({"started_at": data["sla_paused_at"], "status": next_status})
    elif was_paused and not is_paused and data.get("sla_paused_at"):
        paused_at = datetime.fromisoformat(data["sla_paused_at"])
        paused_at = paused_at if paused_at.tzinfo else paused_at.replace(tzinfo=timezone.utc)
        duration = max(timedelta(0), now() - paused_at)
        ticket.first_response_due += duration
        ticket.resolution_due += duration
        data["sla_total_paused_minutes"] = int(data.get("sla_total_paused_minutes", 0)) + int(duration.total_seconds() // 60)
        data.setdefault("sla_pause_events", [])[-1]["ended_at"] = now().isoformat()
        data.pop("sla_paused_at", None)
    ticket.custom_data = data


def route_incident(db: Session, sample: dict, requester: User) -> tuple[Team, User | None, str, list[dict]]:
    # Import here to keep the generic rule evaluator independent of ticket services.
    from .admin_services import evaluate_group
    trace: list[dict] = []
    selected_queue: SupportQueue | None = None
    selected_team: Team | None = None
    selected_actions: dict = {}
    for rule in db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True), RoutingRule.status == "active",
                                                       RoutingRule.trigger == "ticket.created").order_by(RoutingRule.priority_order, RoutingRule.id)).all():
        effective_from = rule.effective_from if not rule.effective_from or rule.effective_from.tzinfo else rule.effective_from.replace(tzinfo=timezone.utc)
        effective_until = rule.effective_until if not rule.effective_until or rule.effective_until.tzinfo else rule.effective_until.replace(tzinfo=timezone.utc)
        if (effective_from and effective_from > now()) or (effective_until and effective_until < now()):
            trace.append({"rule_id": rule.id, "rule": rule.name, "matched": False,
                          "conditions": ["Rule is outside its effective date window"]})
            continue
        matched, lines = evaluate_group(rule.conditions or [], sample)
        trace.append({"rule_id": rule.id, "rule": rule.name, "matched": matched, "conditions": lines})
        if not matched:
            continue
        actions = rule.actions or {}
        selected_actions = actions
        selected_queue = db.get(SupportQueue, actions.get("queue_id")) if actions.get("queue_id") else None
        selected_team = db.get(Team, actions.get("team_id")) if actions.get("team_id") else None
        rule.match_count += 1
        rule.last_matched_at = now()
        if selected_queue or selected_team or rule.stop_processing:
            break
    if not selected_queue and not selected_team:
        team, tech, reason = route_ticket(db, sample.get("category", "General"), requester)
        trace.append({"rule": "Fallback routing", "matched": True, "conditions": [reason]})
        return team, tech, reason, trace
    if selected_queue and not selected_team:
        selected_team = db.get(Team, selected_queue.team_id)
    if not selected_team:
        raise ValueError("The matching routing rule does not resolve to an active team")
    team_ids = [selected_team.id]
    if selected_queue:
        eligible = db.scalars(select(QueueTeamEligibility).where(QueueTeamEligibility.queue_id == selected_queue.id,
                                                                  QueueTeamEligibility.active.is_(True)).order_by(QueueTeamEligibility.eligibility_priority)).all()
        team_ids = [item.team_id for item in eligible] or team_ids
    memberships = db.scalars(select(TeamMembership).where(TeamMembership.team_id.in_(team_ids), TeamMembership.active.is_(True))).all()
    member_ids = [item.user_id for item in memberships]
    techs = db.scalars(select(User).where(User.id.in_(member_ids), User.active.is_(True), User.availability == "Available",
                                           User.role.in_([Role.TECHNICIAN, Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN])).order_by(User.id)).all() if member_ids else []
    strategy = (selected_actions.get("assignment_strategy") or
                (selected_queue.assignment_strategy if selected_queue else None) or "round_robin").replace(" ", "_")
    tech = None
    if techs:
        counts = dict(db.execute(select(Ticket.assigned_user_id, func.count(Ticket.id)).where(
            Ticket.assigned_user_id.in_([item.id for item in techs]),
            Ticket.status.notin_([TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED])
        ).group_by(Ticket.assigned_user_id)).all())
        if strategy in {"least_active", "lowest_workload"}:
            tech = min(techs, key=lambda item: (counts.get(item.id, 0), item.id))
        elif strategy != "manual":
            state_key = f"round_robin_queue_{selected_queue.id if selected_queue else selected_team.id}"
            state = db.get(SystemState, state_key)
            last_id = (state.value or {}).get("last_user_id") if state else None
            ids = [item.id for item in techs]
            tech = techs[(ids.index(last_id) + 1) % len(ids)] if last_id in ids else techs[0]
            if not state:
                state = SystemState(key=state_key, value={})
                db.add(state)
            state.value = {"last_user_id": tech.id, "last_assigned_at": now().isoformat()}
    queue_name = selected_queue.name if selected_queue else selected_team.queue_name
    matched_name = next((item["rule"] for item in trace if item["matched"]), "Routing rule")
    reason = f"Assigned to {queue_name} by {matched_name}"
    if tech:
        reason += f"; {strategy.replace('_', ' ')} selected {tech.display_name}"
    else:
        reason += "; no available technician"
    return selected_team, tech, reason, trace


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
        # A direct assignment grants the technician access even when the
        # ticket is owned by a different team. This mirrors the list/count
        # visibility filter and supports cross-team escalation and handoff.
        return ticket.team_id == user.team_id or ticket.assigned_user_id == user.id
    return True


def visible_ticket_filter(user: User):
    if user.role == Role.END_USER:
        return Ticket.requester_id == user.id
    if user.role == Role.AUDITOR:
        return Ticket.restricted.is_(False)
    if user.role in (Role.TECHNICIAN, Role.TEAM_LEAD):
        return or_(Ticket.team_id == user.team_id, Ticket.assigned_user_id == user.id)
    return True


def notification_context(db:Session,ticket:Ticket|None,event:str,message_preview:str="")->dict:
    requester=db.get(User,ticket.requester_id) if ticket else None;assignee=db.get(User,ticket.assigned_user_id) if ticket and ticket.assigned_user_id else None
    team=db.get(Team,ticket.team_id) if ticket else None;approval=db.scalar(select(ApprovalRequest).where(ApprovalRequest.ticket_id==ticket.id)) if ticket else None
    approver=db.get(User,approval.current_approver_id) if approval and approval.current_approver_id else None
    actor=requester if event in {"ticket.requester_reply","user.replied"} else assignee
    return {"event":{"key":event},"ticket":{"number":ticket.number if ticket else "TEST-000001","subject":ticket.subject if ticket else "Notification preview","status":ticket.status.value if ticket else "New","priority":ticket.priority if ticket else "Medium","created_at_local":ticket.created_at.isoformat() if ticket else now().isoformat(),"resolution_summary":ticket.resolution_summary if ticket else "Resolution details","url":f"{settings.public_url.rstrip('/')}/#ticket/{ticket.id}" if ticket else f"{settings.public_url.rstrip('/')}/#tickets"},
            "requester":{"name":requester.display_name if requester else "Requester","first_name":(requester.display_name.split()[0] if requester else "Requester")},
            "assignee":{"name":assignee.display_name if assignee else "Unassigned","first_name":(assignee.display_name.split()[0] if assignee else "Technician")},
            "actor":{"name":actor.display_name if actor else "Service Desk"},"message":{"preview":message_preview},
            "approver":{"name":approver.display_name if approver else "Approver","first_name":(approver.display_name.split()[0] if approver else "Approver")},
            "queue":{"name":team.name if team else "Service Desk","manager":db.get(User,team.lead_user_id).display_name if team and team.lead_user_id and db.get(User,team.lead_user_id) else "Service Desk Manager"},"organization":{"support_name":"Service Desk"}}


def render_notification_text(value:str,context:dict)->str:
    def replace(match):
        current=context
        for part in match.group(1).strip().split("."):
            current=current.get(part,"") if isinstance(current,dict) else ""
        return str(current or "")
    return re.sub(r"{{\s*([a-zA-Z0-9_.]+)\s*}}",replace,str(value or ""))


def configured_notification_recipients(db:Session,rule:NotificationRule,ticket:Ticket|None,fallback_user_id:int|None)->list[tuple[int,bool]]:
    ids=[];team=db.get(Team,ticket.team_id) if ticket else None;requester=db.get(User,ticket.requester_id) if ticket else None
    approval=db.scalar(select(ApprovalRequest).where(ApprovalRequest.ticket_id==ticket.id)) if ticket else None
    for recipient in rule.recipients or []:
        kind=recipient.get("type");user_id=None
        if kind=="requester" and ticket:user_id=ticket.requester_id
        elif kind=="opener" and ticket:user_id=ticket.opened_by_id
        elif kind=="assignee" and ticket:user_id=ticket.assigned_user_id
        elif kind in {"team_lead","queue_manager"} and team:user_id=team.lead_user_id
        elif kind=="approver" and approval:user_id=approval.current_approver_id
        elif kind=="manager" and requester:user_id=requester.manager_user_id
        elif kind=="explicit_address":
            account=db.scalar(select(User).where(func.lower(User.email)==str(recipient.get("value","")).lower(),User.active.is_(True)));user_id=account.id if account else None
        elif kind=="group" and recipient.get("value"):
            try: group_id=int(recipient["value"])
            except (TypeError,ValueError): group_id=0
            ids.extend((member_id,recipient.get("channel") in {"to","cc","bcc"}) for member_id in db.scalars(select(UserGroupMembership.user_id).where(UserGroupMembership.group_id==group_id)).all())
        if user_id: ids.append((user_id,recipient.get("channel") in {"to","cc","bcc"}))
    # Configured recipients add to the product's standard event recipient;
    # they never accidentally replace the requester, assignee, or approver.
    if fallback_user_id: ids.append((fallback_user_id,False))
    merged:dict[int,bool]={}
    for recipient_id,wants_email in ids:merged[recipient_id]=merged.get(recipient_id,False) or wants_email
    return list(merged.items())


def notification_delivery_enabled(db: Session) -> bool:
    control=db.scalar(select(ConfigItem).where(ConfigItem.section=="notification_controls",
                                                ConfigItem.name=="Global notification delivery"))
    return bool((control.value or {}).get("enabled",True)) if control else True


def outbound_email_delivery_enabled(db: Session) -> bool:
    control=db.scalar(select(ConfigItem).where(ConfigItem.section=="notification_controls",
                                                ConfigItem.name=="Outbound email delivery"))
    return bool((control.value or {}).get("enabled",settings.outbound_email_enabled)) if control else settings.outbound_email_enabled


def notification_delivery_status(db: Session, email_requested: bool) -> str:
    return "pending_email" if email_requested and outbound_email_delivery_enabled(db) else "in_app"


def _notification_audit_details(db:Session,user_id:int,event:str,title:str,email:bool,ticket:Ticket|None,**extra)->dict:
    recipient=db.get(User,user_id) if user_id else None
    return {"event":event,"recipient_user_id":user_id,"recipient_name":recipient.display_name if recipient else "Unavailable",
            "recipient_email":recipient.email if recipient else "","email_requested":bool(email),"subject":title,
            "ticket_id":ticket.id if ticket else None,"ticket_number":ticket.number if ticket else "",**extra}


def notify(db: Session, user_id: int | None, event: str, title: str, body: str, ticket_id=None, email=False):
    ticket=db.get(Ticket,ticket_id) if ticket_id else None
    if not notification_delivery_enabled(db):
        audit(db,"notification.suppressed","notification",ticket_id,new=_notification_audit_details(
            db,user_id,event,title,email,ticket,reason="Global notification delivery is disabled"))
        return
    rules=db.scalars(select(NotificationRule).where(NotificationRule.trigger==event,NotificationRule.active.is_(True),NotificationRule.status=="active")).all()
    if rules:
        from .admin_services import evaluate_group
        context=notification_context(db,ticket,event,body);sample={**context.get("ticket",{}),"ticket":context.get("ticket",{}),"requester":context.get("requester",{})}
        for rule in rules:
            conditions=rule.conditions or []
            matched,_=evaluate_group(conditions,sample) if conditions else (True,[])
            if not matched: continue
            rendered_title=render_notification_text((rule.template or {}).get("subject") or title,context)
            rendered_body=render_notification_text((rule.template or {}).get("text_body") or (rule.template or {}).get("body") or body,context)
            dedupe=max(0,int((rule.rate_limit or {}).get("dedupe_minutes",0)))
            for recipient_id,wants_email in configured_notification_recipients(db,rule,ticket,user_id):
                if dedupe and db.scalar(select(Notification.id).where(Notification.user_id==recipient_id,Notification.ticket_id==ticket_id,Notification.event==event,Notification.created_at>=now()-timedelta(minutes=dedupe))): continue
                email_requested=bool(email or wants_email)
                notification=Notification(user_id=recipient_id,ticket_id=ticket_id,event=event,title=rendered_title[:240],body=rendered_body,delivery_status=notification_delivery_status(db,email_requested))
                db.add(notification);db.flush()
                audit(db,"notification.created","notification",notification.id,new=_notification_audit_details(
                    db,recipient_id,event,rendered_title,email_requested,ticket,rule_id=rule.id,delivery_status=notification.delivery_status,
                    email_suppressed=email_requested and notification.delivery_status!="pending_email"))
        return
    if user_id:
        notification=Notification(user_id=user_id, ticket_id=ticket_id, event=event, title=title, body=body,
                                  delivery_status=notification_delivery_status(db,bool(email)))
        db.add(notification);db.flush()
        audit(db,"notification.created","notification",notification.id,new=_notification_audit_details(
            db,user_id,event,title,email,ticket,delivery_status=notification.delivery_status,
            email_suppressed=bool(email) and notification.delivery_status!="pending_email"))


_REQUESTER_CLOSE_PATTERNS = (
    r"please close (?:this|the|my) ticket",
    r"(?:it is |it'?s )?(?:ok|okay) to close (?:this|the|my) ticket",
    r"you can close (?:this|the|my) ticket",
    r"close (?:this|the|my) ticket please",
    r"(?:this|the) issue is resolved[,. ]+(?:please )?close (?:this|the) ticket",
)


def close_ticket_from_requester_message(db: Session, ticket: Ticket, requester: User, body: str,
                                        source: str) -> bool:
    """Honor an explicit requester closure instruction without interpreting vague replies."""
    if requester.id != ticket.requester_id or ticket.status in {
        TicketStatus.CLOSED, TicketStatus.CANCELLED,
    }:
        return False
    first_line = next((line.strip() for line in str(body or "").splitlines()
                       if line.strip() and not line.lstrip().startswith(">")), "")[:240]
    normalized = re.sub(r"\s+", " ", first_line).strip().lower()
    if not any(re.fullmatch(pattern, normalized, flags=re.IGNORECASE) for pattern in _REQUESTER_CLOSE_PATTERNS):
        return False
    closed_at = now()
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = closed_at
    # A closed request cannot continue to accept live-chat messages. Close any
    # open chat session as part of the same transaction so both participants see
    # the final transcript consistently.
    for session in db.scalars(select(TicketChatSession).where(
        TicketChatSession.ticket_id == ticket.id,
        TicketChatSession.status.in_(["requested", "active"]),
    )).all():
        session.status = "closed"
        session.closed_at = closed_at
        session.last_activity_at = closed_at
    ticket.next_action_owner = "Completed"
    ticket.next_action = "Closed at requester instruction"
    note = (f"{requester.display_name} closed the ticket at their request on "
            f"{closed_at.strftime('%Y-%m-%d %H:%M UTC')} via {source.replace('_', ' ')}.")
    db.add(TicketMessage(ticket_id=ticket.id, author_id=None, body=note, kind="public", source="system"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="closed_by_requester", actor_id=requester.id,
                         new_value={"status": TicketStatus.CLOSED.value, "source": source}, reason="Requester instruction"))
    audit(db, "ticket.closed_by_requester", "ticket", ticket.id, requester.id,
          new={"status": TicketStatus.CLOSED.value, "source": source})
    notify(db, ticket.assigned_user_id, "ticket.requester_closed",
           f"[{ticket.number}] Closed by requester: {ticket.subject}",
           f"{requester.display_name} requested that this ticket be closed.", ticket.id, email=True)
    notify(db, ticket.requester_id, "ticket.closed", f"[{ticket.number}] Closed: {ticket.subject}",
           "Your request has been closed as instructed.", ticket.id, email=True)
    return True


FORM_FIELD_TYPES = {"short_text", "long_text", "select", "multi_select", "choice_cards", "radio",
                    "date", "time", "number", "phone", "checkbox", "email", "asset", "user", "section", "attachment"}


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
        if field_type in {"select", "multi_select", "choice_cards", "radio"} and not options:
            raise ValueError(f"{label} needs at least one option")
        if field_type != "section":
            keys.add(key)
        width = str(raw.get("width", "full"))
        if width not in {"third", "half", "two_thirds", "full"}:
            width = "full"
        max_length = raw.get("max_length")
        if field_type in {"short_text", "long_text", "email", "phone"} and max_length not in (None, ""):
            try: max_length = int(max_length)
            except (TypeError, ValueError): raise ValueError(f"{label} needs a valid character limit")
            maximum = 20000 if field_type == "long_text" else 500
            if max_length < 1 or max_length > maximum:
                raise ValueError(f"{label} character limit must be between 1 and {maximum}")
        else:
            max_length = None
        visibility = str(raw.get("visibility", "visible"))
        if visibility not in {"visible", "hidden", "technician_only"}:
            visibility = "visible"
        show_when = raw.get("show_when") if isinstance(raw.get("show_when"), dict) else None
        if show_when:
            show_when = {"key": str(show_when.get("key", ""))[:60], "value": str(show_when.get("value", ""))[:120]}
            if not show_when["key"] or not show_when["value"]:
                show_when = None
        required_when = raw.get("required_when") if isinstance(raw.get("required_when"), dict) else None
        if required_when:
            required_when = {"key": str(required_when.get("key", ""))[:60], "value": str(required_when.get("value", ""))[:120]}
            if not required_when["key"] or not required_when["value"]:
                required_when = None
        default_value = raw.get("default_value")
        if isinstance(default_value, str):
            default_value = default_value[:20000]
        elif default_value is not None and not isinstance(default_value, (bool, int, float, list)):
            default_value = None
        classification = str(raw.get("classification", "public"))
        if classification not in {"public", "internal", "restricted"}: classification = "public"
        access_roles = [str(role) for role in raw.get("access_roles", []) if str(role) in {item.value for item in Role}]
        retention_days = raw.get("retention_days")
        if retention_days not in (None, ""):
            try: retention_days = max(1, min(3650, int(retention_days)))
            except (TypeError, ValueError): raise ValueError(f"{label} needs a valid retention period")
        else: retention_days = None
        clean.append({"id": str(raw.get("id") or uuid.uuid4()), "key": key, "label": label,
                      "type": field_type, "required": bool(raw.get("required", False)),
                      "help": str(raw.get("help", ""))[:500], "options": options,
                      "placeholder": str(raw.get("placeholder", ""))[:240], "width": width,
                      "icon": str(raw.get("icon", ""))[:30], "max_length": max_length,
                    "visibility": visibility, "read_only": bool(raw.get("read_only", False)),
                    "default_value": default_value, "show_when": show_when,
                    "required_when": required_when,"classification":classification,
                    "mask_value":bool(raw.get("mask_value",False)),"access_roles":access_roles,
                    "retention_days":retention_days,"reportable":bool(raw.get("reportable",True))})
    valid_keys = {field["key"] for field in clean if field["type"] != "section"}
    for field in clean:
        for rule_name in ("show_when", "required_when"):
            rule = field.get(rule_name)
            if rule and (rule["key"] not in valid_keys or rule["key"] == field.get("key")):
                raise ValueError(f"{field['label']} has an invalid {rule_name.replace('_', ' ')} field")
    return clean


def validate_form_submission(form: FormDefinition, values: dict) -> dict:
    result: dict = {}
    allowed = {field["key"]: field for field in form.fields if field.get("type") != "section"}
    for key, field in allowed.items():
        if field.get("visibility") in {"hidden", "technician_only"}:
            continue
        condition = field.get("show_when") or {}
        if condition and str(values.get(condition.get("key"), "")) != str(condition.get("value", "")):
            continue
        value = values.get(key, field.get("default_value"))
        empty = value is None or value == "" or value == []
        required_condition = field.get("required_when") or {}
        conditionally_required = bool(required_condition) and str(values.get(required_condition.get("key"), "")) == str(required_condition.get("value", ""))
        if (field.get("required") or conditionally_required) and empty:
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
            max_length = field.get("max_length") or 255
            if len(text_value) > max_length:
                raise ValueError(f"{field['label']} must be {max_length} characters or fewer")
            result[key] = text_value
        elif field_type == "multi_select":
            selected = value if isinstance(value, list) else [value]
            if any(item not in field.get("options", []) for item in selected):
                raise ValueError(f"{field['label']} contains an invalid option")
            result[key] = selected
        elif field_type in {"select", "choice_cards", "radio"}:
            if value not in field.get("options", []): raise ValueError(f"{field['label']} contains an invalid option")
            result[key] = value
        else:
            text_value = str(value)
            max_length = field.get("max_length") or (20000 if field_type == "long_text" else 500)
            if len(text_value) > max_length:
                raise ValueError(f"{field['label']} must be {max_length} characters or fewer")
            result[key] = text_value
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

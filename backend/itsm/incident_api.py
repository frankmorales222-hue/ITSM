import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .assetpilot import ensure_asset_employee_user
from .config import settings
from .database import get_db
from .models import (Asset, ConfigItem, DomainEvent, Employee, FormDefinition, Role, ServiceCategory,
                     Team, TeamMembership, Ticket, TicketAsset, TicketAttachment, TicketHistory, TicketMessage,
                     TicketStatus, User)
from .schemas import IncidentCreate, IncidentSettingsUpdate
from .security import current_user, has_permission, require_permission, require_roles
from .services import (add_operational_minutes, audit, configured_priority, configured_sla_dates, next_ticket_number, notify,
                       route_incident, sensitive_warnings)

router = APIRouter(prefix="/api", tags=["incidents"])
UPLOAD_ROOT = Path(settings.data_directory) / "attachments"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".zip"}
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def config_value(db: Session, section: str, fallback: dict) -> dict:
    item = db.scalar(select(ConfigItem).where(ConfigItem.section == section))
    return item.value or fallback if item else fallback


def option_names(taxonomy: dict, key: str) -> set[str]:
    return {str(item.get("name")) for item in taxonomy.get(key, []) if item.get("active", True)}


def category_dict(item: ServiceCategory) -> dict:
    return {"id": item.id, "name": item.name, "parent_id": item.parent_id, "level": item.level,
            "description": item.description, "sort_order": item.sort_order}


def profile_for(db: Session, user: User) -> dict:
    employee = db.scalar(select(Employee).where(or_(Employee.user_id == user.id, func.lower(Employee.work_email) == user.email.lower())))
    return {"id": user.id, "display_name": user.display_name, "email": user.email,
            "department": employee.department.name if employee and employee.department else user.department_name,
            "location": employee.location.name if employee and employee.location else user.location_name,
            "employee_id": employee.employee_number if employee else user.employee_number}


def can_submit_for(db: Session, actor: User, requester_id: int) -> bool:
    return requester_id == actor.id or has_permission(db, actor, "incidents.submit_on_behalf")


@router.get("/incidents/config")
def incident_config(user: User = Depends(require_permission("incidents.submit")), db: Session = Depends(get_db)):
    taxonomy = config_value(db, "incident_taxonomy", {})
    matrix = config_value(db, "incident_priority_matrix", {"cells": {}})
    sla = config_value(db, "incident_sla", {"policies": []})
    categories = db.scalars(select(ServiceCategory).where(ServiceCategory.active.is_(True)).order_by(ServiceCategory.sort_order, ServiceCategory.name)).all()
    teams = db.scalars(select(Team).where(Team.active.is_(True)).order_by(Team.name)).all()
    default_form = db.scalar(select(FormDefinition).where(FormDefinition.form_type == "incident", FormDefinition.default_for_type.is_(True),
                                                           FormDefinition.active.is_(True), FormDefinition.published.is_(True)))
    return {"taxonomy": taxonomy, "priority_matrix": matrix, "sla": sla,
            "categories": [category_dict(item) for item in categories], "requester": profile_for(db, user),
            "teams": [{"id": item.id, "name": item.name, "region": item.region,
                       "supported_locations": item.supported_locations or []} for item in teams],
            "permissions": {"submit_on_behalf": has_permission(db, user, "incidents.submit_on_behalf"),
                            "assign": has_permission(db, user, "incidents.assign"),
                            "override_priority": has_permission(db, user, "incidents.override_priority")},
            "default_form": {"id": default_form.id, "name": default_form.name, "fields": default_form.fields or []} if default_form else None}


@router.get("/incidents/priority-preview")
def priority_preview(impact: str, urgency: str, user: User = Depends(require_permission("incidents.submit")), db: Session = Depends(get_db)):
    priority, reason = configured_priority(db, impact, urgency)
    first, resolution, key, sla_reason = configured_sla_dates(db, priority)
    return {"priority": priority, "reason": reason, "sla_policy_key": key, "sla_reason": sla_reason,
            "response_due": first, "resolution_due": resolution}


@router.get("/lookups/users")
def user_lookup(q: str = Query(default="", max_length=120), limit: int = Query(default=20, ge=1, le=50),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not has_permission(db, user, "incidents.submit_on_behalf"):
        return [profile_for(db, user)]
    # Cached employee records live in the ITSM database and remain safe to use
    # even when the optional AssetPilot application is disabled or offline.
    employee_stmt = select(Employee).where(Employee.employment_status == "Active")
    if q.strip():
        term = f"%{q.strip().lower()}%"
        employee_stmt = employee_stmt.where(or_(
            func.lower(Employee.first_name + " " + Employee.last_name).like(term),
            func.lower(Employee.work_email).like(term),
            func.lower(Employee.employee_number).like(term),
        ))
    for employee in db.scalars(employee_stmt.limit(limit)).all():
        ensure_asset_employee_user(db, employee)
    db.commit()
    stmt = select(User).where(User.active.is_(True))
    if q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.display_name).like(term), func.lower(User.email).like(term), func.lower(User.username).like(term)))
    return [profile_for(db, item) for item in db.scalars(stmt.order_by(User.display_name).limit(limit)).all()]


@router.get("/lookups/assets")
def asset_lookup(requester_id: int | None = None, q: str = Query(default="", max_length=120),
                 limit: int = Query(default=30, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    target_id = requester_id or user.id
    if not can_submit_for(db, user, target_id):
        raise HTTPException(403, "You may only view assets assigned to you")
    requester = db.get(User, target_id)
    if not requester or not requester.active:
        raise HTTPException(404, "Requester not found")
    stmt = select(Asset).join(Employee, Asset.assigned_employee_id == Employee.id).where(
        func.lower(Employee.work_email) == requester.email.lower(), Asset.is_archived.is_(False))
    if q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Asset.asset_tag).like(term), func.lower(Asset.hostname).like(term), func.lower(Asset.serial_number).like(term)))
    return [{"id": item.id, "asset_tag": item.asset_tag, "hostname": item.hostname, "serial_number": item.serial_number,
             "device_type": item.asset_type, "status": item.status, "location": item.location.name if item.location else ""}
            for item in db.scalars(stmt.order_by(Asset.asset_tag).limit(limit)).all()]


@router.get("/lookups/technicians")
def technician_lookup(team_id: int, site: str = "", q: str = Query(default="", max_length=120),
                      user: User = Depends(require_permission("incidents.assign")), db: Session = Depends(get_db)):
    team = db.get(Team, team_id)
    if not team or not team.active:
        raise HTTPException(404, "Assignment group not found")
    if site and team.supported_locations and site not in team.supported_locations:
        return []
    membership_ids = db.scalars(select(TeamMembership.user_id).where(TeamMembership.team_id == team_id, TeamMembership.active.is_(True))).all()
    ids = set(membership_ids)
    ids.update(db.scalars(select(User.id).where(User.team_id == team_id)).all())
    stmt = select(User).where(User.id.in_(ids), User.active.is_(True), User.role.in_([Role.TECHNICIAN, Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN]))
    if q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.display_name).like(term), func.lower(User.email).like(term)))
    return [{"id": item.id, "display_name": item.display_name, "email": item.email, "availability": item.availability,
             "location": item.location_name} for item in db.scalars(stmt.order_by(User.display_name).limit(50)).all()]


def validate_category_chain(db: Session, category_id: int, subcategory_id: int | None, item_id: int | None):
    category = db.get(ServiceCategory, category_id)
    if not category or not category.active or category.parent_id is not None:
        raise HTTPException(422, "Choose a valid category")
    subcategory = db.get(ServiceCategory, subcategory_id) if subcategory_id else None
    if subcategory and (not subcategory.active or subcategory.parent_id != category.id):
        raise HTTPException(422, "The selected subcategory does not belong to the category")
    item = db.get(ServiceCategory, item_id) if item_id else None
    if item and (not subcategory or not item.active or item.parent_id != subcategory.id):
        raise HTTPException(422, "The selected item does not belong to the subcategory")
    return category, subcategory, item


@router.post("/incidents", status_code=201)
def create_incident(payload: IncidentCreate, request: Request, actor: User = Depends(require_permission("incidents.submit")), db: Session = Depends(get_db)):
    if any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address.strip()) for address in payload.emails_to_notify):
        raise HTTPException(422, "Emails to notify contains an invalid address")
    existing_event = db.scalar(select(DomainEvent).where(DomainEvent.idempotency_key == f"incident-submit:{payload.client_request_id}"))
    if existing_event and existing_event.aggregate_id:
        existing = db.get(Ticket, int(existing_event.aggregate_id))
        if existing:
            return {"ticket": {"id": existing.id, "number": existing.number}, "duplicate": True}
    requester_id = payload.on_behalf_of_id or payload.requester_id or actor.id
    if not can_submit_for(db, actor, requester_id):
        raise HTTPException(403, "You do not have permission to submit for another requester")
    requester = db.get(User, requester_id)
    if not requester or not requester.active:
        raise HTTPException(422, "Requester is not active")
    taxonomy = config_value(db, "incident_taxonomy", {})
    checks = {"request_types": payload.request_type, "modes": payload.mode, "levels": payload.level,
              "impacts": payload.impact, "urgencies": payload.urgency, "statuses": payload.status}
    for kind, value in checks.items():
        if value not in option_names(taxonomy, kind):
            raise HTTPException(422, f"Choose a valid {kind.replace('_', ' ')[:-1]}")
    category, subcategory, item = validate_category_chain(db, payload.category_id, payload.subcategory_id, payload.item_id)
    profile = profile_for(db, requester)
    site = payload.site_location.strip() or profile.get("location", "")
    if payload.site_location.strip() and payload.site_location.strip() != profile.get("location", "") and not has_permission(db, actor, "incidents.submit_on_behalf"):
        raise HTTPException(403, "You do not have permission to override the requester location")
    calculated, priority_reason = configured_priority(db, payload.impact, payload.urgency)
    priority, source, override_reason = calculated, "calculated", None
    if payload.priority_override and payload.priority_override != calculated:
        if not has_permission(db, actor, "incidents.override_priority"):
            raise HTTPException(403, "You do not have permission to override priority")
        if not payload.priority_override_reason or len(payload.priority_override_reason.strip()) < 4:
            raise HTTPException(422, "Explain why the calculated priority is being overridden")
        if payload.priority_override not in option_names(taxonomy, "priorities"):
            raise HTTPException(422, "Choose a valid override priority")
        priority, source, override_reason = payload.priority_override, "overridden", payload.priority_override_reason.strip()
        priority_reason += f" Overridden to {priority}: {override_reason}"
    first_due, resolution_due, sla_key, sla_reason = configured_sla_dates(db, priority)
    requester_email = (requester.email or "").strip().lower()
    requester_domain = requester_email.rsplit("@", 1)[1] if "@" in requester_email else ""
    sample = {"request_type": payload.request_type, "status": payload.status, "mode": payload.mode, "level": payload.level,
              "impact": payload.impact, "urgency": payload.urgency, "priority": priority, "category": category.name,
              "subcategory": subcategory.name if subcategory else "", "item": item.name if item else "", "location_name": site,
              "requester_department": profile.get("department", ""), "requester_email": requester_email,
              "requester": requester_email, "requester_domain": requester_domain,
              "organization": str(requester.organization_id),
              "channel": payload.mode.lower().replace(" ", "_")}
    try:
        team, technician, route_reason, route_trace = route_incident(db, sample, requester)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if payload.team_id or payload.assigned_user_id:
        if not has_permission(db, actor, "incidents.assign"):
            raise HTTPException(403, "You do not have permission to override assignment")
        if payload.team_id:
            team = db.get(Team, payload.team_id)
            if not team or not team.active:
                raise HTTPException(422, "Choose an active assignment group")
        if payload.assigned_user_id:
            candidate = db.get(User, payload.assigned_user_id)
            membership = db.scalar(select(TeamMembership).where(TeamMembership.team_id == team.id,
                                                                 TeamMembership.user_id == payload.assigned_user_id,
                                                                 TeamMembership.active.is_(True)))
            if not candidate or not candidate.active or (candidate.team_id != team.id and not membership):
                raise HTTPException(422, "The technician is not an active member of the selected group")
            technician = candidate
        route_reason = f"Assignment manually selected by {actor.display_name}."
        route_trace.append({"rule": "Manual assignment override", "matched": True, "conditions": [route_reason]})
    employee = db.scalar(select(Employee).where(or_(Employee.user_id == requester.id, func.lower(Employee.work_email) == requester.email.lower())))
    assets = db.scalars(select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.is_archived.is_(False))).all() if payload.asset_ids else []
    if len(assets) != len(set(payload.asset_ids)):
        raise HTTPException(422, "One or more selected assets are unavailable")
    if actor.id == requester.id:
        employee_id = employee.id if employee else -1
        if any(asset.assigned_employee_id != employee_id for asset in assets):
            raise HTTPException(403, "You may only attach assets assigned to you")
    form = db.get(FormDefinition, payload.form_definition_id) if payload.form_definition_id else db.scalar(
        select(FormDefinition).where(FormDefinition.form_type == "incident", FormDefinition.default_for_type.is_(True),
                                     FormDefinition.active.is_(True), FormDefinition.published.is_(True)))
    custom_data = dict(payload.custom_data)
    custom_data.update({"category_id": category.id, "subcategory_id": subcategory.id if subcategory else None,
                        "item_id": item.id if item else None, "configuration_item_ids": payload.configuration_item_ids,
                        "priority_explanation": priority_reason})
    ticket = Ticket(number=next_ticket_number(db, "Incident"), request_type=payload.request_type, subject=payload.subject.strip(),
                    description=payload.description.strip(), requester_id=requester.id, opened_by_id=actor.id,
                    employee_id=employee.id if employee else None, assigned_user_id=technician.id if technician else None,
                    team_id=team.id, status=TicketStatus.OPEN, priority=priority, impact=payload.impact, urgency=payload.urgency,
                    mode=payload.mode, level=payload.level, impact_details=payload.impact_details.strip(), site_location=site,
                    emails_to_notify=[str(email).lower() for email in payload.emails_to_notify], calculated_priority=calculated,
                    priority_source=source, priority_override_reason=override_reason, category=category.name,
                    subcategory=subcategory.name if subcategory else None, item=item.name if item else None,
                    route_reason=route_reason, routing_trace=route_trace, first_response_due=first_due,
                    resolution_due=resolution_due, sla_policy_key=sla_key, sla_explanation=sla_reason,
                    form_definition_id=form.id if form else None, custom_data=custom_data,
                    requester_snapshot={**profile, "opened_by_id": actor.id, "opened_by_name": actor.display_name,
                                        "opened_by_email": actor.email, "requested_for_id": requester.id,
                                        "submitted_at": datetime.now(timezone.utc).isoformat()})
    ticket.assets = assets
    db.add(ticket); db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=actor.id, body=ticket.description, kind="public", source="web"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="incident.created", actor_id=actor.id,
                         new_value={"status": "Open", "priority": priority, "calculated_priority": calculated,
                                    "sla_policy": sla_key, "team_id": team.id, "assigned_user_id": technician.id if technician else None},
                         reason=route_reason))
    db.add(DomainEvent(event_key="ticket.created", aggregate_type="ticket", aggregate_id=str(ticket.id), actor_id=actor.id,
                       idempotency_key=f"incident-submit:{payload.client_request_id}", payload={"priority": priority, "team_id": team.id}))
    notify(db, requester.id, "ticket.created", f"{ticket.number} created", f"Your incident was submitted with {priority} priority.", ticket.id, email=True)
    notify(db, technician.id if technician else None, "ticket.assigned", f"[{ticket.number}] Assigned: {ticket.subject}",
           f"Incident submitted by {requester.display_name}.",ticket.id,email=True)
    audit(db, "incident.created", "ticket", ticket.id, actor.id,
          new={"number": ticket.number, "priority": priority, "calculated_priority": calculated, "priority_source": source,
               "sla_policy": sla_key, "route_reason": route_reason},
          source_ip=request.client.host if request.client else None, correlation_id=getattr(request.state, "correlation_id", None))
    warnings = sensitive_warnings(f"{payload.subject} {payload.description} {payload.impact_details}")
    db.commit()
    return {"ticket": {"id": ticket.id, "number": ticket.number, "priority": priority, "calculated_priority": calculated,
                       "priority_source": source, "priority_explanation": priority_reason, "team": team.name,
                       "assignee": technician.display_name if technician else None, "route_reason": route_reason,
                       "sla_policy_key": sla_key, "sla_explanation": sla_reason,
                       "first_response_due": first_due, "resolution_due": resolution_due},
            "warnings": warnings, "duplicate": False}


@router.post("/incidents/{ticket_id}/attachments", status_code=201)
async def upload_incident_attachments(ticket_id: int, files: list[UploadFile] = File(...),
                                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or (ticket.requester_id != user.id and not has_permission(db, user, "incidents.view_group")):
        raise HTTPException(404, "Incident not found")
    if not files or len(files) > 10:
        raise HTTPException(422, "Attach between 1 and 10 files")
    created = []
    for upload in files:
        original = Path(upload.filename or "attachment").name[:255]
        extension = Path(original).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(422, f"{original} uses a file type that is not allowed")
        data = await upload.read(MAX_ATTACHMENT_BYTES + 1)
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(422, f"{original} exceeds the 25 MB limit")
        storage_name = f"{ticket.organization_id}-{ticket.id}-{uuid.uuid4().hex}{extension}"
        destination = UPLOAD_ROOT / storage_name
        destination.write_bytes(data)
        item = TicketAttachment(ticket_id=ticket.id, original_name=original, storage_name=storage_name,
                                content_type=(upload.content_type or "application/octet-stream")[:120],
                                size_bytes=len(data), uploaded_by_id=user.id)
        db.add(item); db.flush(); created.append({"id": item.id, "name": original, "size_bytes": len(data)})
        audit(db, "incident.attachment_added", "ticket_attachment", item.id, user.id,
              new={"ticket_id": ticket.id, "name": original, "size_bytes": len(data)})
    db.commit()
    return created


@router.get("/incidents/{ticket_id}/attachments/{attachment_id}")
def download_incident_attachment(ticket_id: int, attachment_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    item = db.get(TicketAttachment, attachment_id)
    if not ticket or not item or item.ticket_id != ticket.id or (ticket.requester_id != user.id and not has_permission(db, user, "incidents.view_group")):
        raise HTTPException(404, "Attachment not found")
    path = UPLOAD_ROOT / item.storage_name
    if not path.exists():
        raise HTTPException(404, "Attachment file is unavailable")
    return FileResponse(path, media_type=item.content_type, filename=item.original_name)


def validate_incident_settings(payload: IncidentSettingsUpdate):
    taxonomy = payload.taxonomy
    for key in ["request_types", "modes", "levels", "impacts", "urgencies", "priorities", "statuses"]:
        values = taxonomy.get(key)
        if not isinstance(values, list) or not values:
            raise HTTPException(422, f"{key.replace('_', ' ').title()} must contain at least one active option")
        names = [str(item.get("name", "")).strip() for item in values]
        if any(not name for name in names) or len(set(name.lower() for name in names)) != len(names):
            raise HTTPException(422, f"{key.replace('_', ' ').title()} contains a blank or duplicate name")
    cells = payload.priority_matrix.get("cells", {})
    missing = [f"{impact}|{urgency}" for impact in option_names(taxonomy, "impacts") for urgency in option_names(taxonomy, "urgencies")
               if not cells.get(f"{impact}|{urgency}")]
    if missing:
        raise HTTPException(422, "Complete every priority matrix cell before publishing: " + ", ".join(sorted(missing)))
    priorities = option_names(taxonomy, "priorities")
    if any(value not in priorities for value in cells.values()):
        raise HTTPException(422, "Every matrix result must use an active priority")
    policies = payload.sla.get("policies", [])
    calendars = payload.sla.get("calendars", [])
    calendar_keys = {item.get("key") for item in calendars} | {"24x7", "default_business_hours"}
    for calendar in calendars:
        if not calendar.get("key") or not calendar.get("name"): raise HTTPException(422, "Every SLA calendar needs a key and name")
        try: ZoneInfo(str(calendar.get("timezone") or "UTC"))
        except ZoneInfoNotFoundError: raise HTTPException(422, f"{calendar.get('name')} has an invalid time zone")
        if not calendar.get("always_open") and (not calendar.get("days") or not calendar.get("start") or not calendar.get("end")):
            raise HTTPException(422, f"{calendar.get('name')} needs working days, opening time, and closing time")
    covered = {item.get("priority") for item in policies if item.get("active", True)}
    if not priorities.issubset(covered):
        raise HTTPException(422, "Every active priority needs an active SLA policy")
    for policy in policies:
        if int(policy.get("response_minutes", 0)) <= 0 or int(policy.get("resolution_minutes", 0)) < int(policy.get("response_minutes", 0)):
            raise HTTPException(422, f"{policy.get('name', 'SLA')} needs valid response and resolution targets")
        if policy.get("calendar") not in calendar_keys:
            raise HTTPException(422, f"{policy.get('name', 'SLA')} references an unknown operational-hours calendar")
        for escalation in policy.get("escalations", []):
            if not 1 <= int(escalation.get("percent", 0)) <= 100 or not escalation.get("recipients"):
                raise HTTPException(422, f"{policy.get('name', 'SLA')} has an invalid escalation threshold or recipient")


@router.post("/admin/sla/simulate")
def simulate_sla(payload: dict, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    priority = str(payload.get("priority") or "Medium")
    start = datetime.fromisoformat(payload["start"]) if payload.get("start") else datetime.now(timezone.utc)
    response, resolution, key, explanation = configured_sla_dates(db, priority, start)
    return {"priority": priority, "policy_key": key, "start": start, "first_response_due": response,
            "resolution_due": resolution, "explanation": explanation}


@router.get("/admin/incident-settings")
def admin_incident_settings(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return {"taxonomy": config_value(db, "incident_taxonomy", {}),
            "priority_matrix": config_value(db, "incident_priority_matrix", {"cells": {}}),
            "sla": config_value(db, "incident_sla", {"policies": []})}


@router.put("/admin/incident-settings")
def update_incident_settings(payload: IncidentSettingsUpdate, request: Request,
                             user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    validate_incident_settings(payload)
    previous = {}
    for section, value in [("incident_taxonomy", payload.taxonomy), ("incident_priority_matrix", payload.priority_matrix), ("incident_sla", payload.sla)]:
        item = db.scalar(select(ConfigItem).where(ConfigItem.section == section))
        if not item:
            item = ConfigItem(section=section, name=section.replace("_", " ").title(), value=value)
            db.add(item)
        else:
            previous[section] = item.value
            item.value = value
    audit(db, "incident.configuration_updated", "incident_configuration", None, user.id, previous=previous,
          new={"sections": ["taxonomy", "priority_matrix", "sla"]},
          source_ip=request.client.host if request.client else None, correlation_id=getattr(request.state, "correlation_id", None))
    db.commit()
    return admin_incident_settings(user, db)

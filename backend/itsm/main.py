import csv
import enum
import io
import json
import os
import secrets
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import __version__
from .assetpilot import assetpilot_preview, ensure_asset_employee_user, import_assetpilot
from .assetpilot_runtime import assetpilot_healthy, ensure_assetpilot_running
from .admin_api import router as administration_router
from .agent_api import router as agent_router
from .chat_api import router as chat_router
from .incident_api import router as incident_router
from .update_api import router as update_router
from .certificate_api import router as certificate_router
from .self_service_api import router as self_service_router
from .config import settings
from .credential_store import clear_integration_secret, integration_secret_status, set_integration_secret
from .database import Base, engine, get_db
from .models import *
from .models import Session as LoginSession
from .schemas import *
from .security import *
from .services import *
from .microsoft_sso import microsoft_authorization_url, microsoft_sign_in_status

app = FastAPI(title="Northstar Desk API", version=__version__, docs_url="/api/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
app.include_router(administration_router)
app.include_router(incident_router)
app.include_router(agent_router)
app.include_router(chat_router)
app.include_router(update_router)
app.include_router(certificate_router)
app.include_router(self_service_router)
started_at = now()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
        "X-Correlation-ID": correlation_id,
    })
    return response


def user_dict(user: User, db: Session | None = None):
    return {"id": user.id, "username": user.username, "email": user.email, "display_name": user.display_name,
            "role": user.role.value, "active": user.active, "must_change_password": user.must_change_password,
            "availability": user.availability, "team_id": user.team_id, "team": user.team.name if user.team else None,
            "last_login_at": user.last_login_at, "organization_id": user.organization_id,
            "ringcentral_extension_id": user.ringcentral_extension_id,
            "ringcentral_extension_number": user.ringcentral_extension_number, "phone": user.phone or "",
            "can_administrate": has_administration_access(db, user) if db else user.role == Role.ADMIN}


def ticket_assets_for_email(db: Session, email: str, requested_ids: list[int] | None = None) -> list[Asset]:
    """Combine explicit assets with active inventory assignments matching the requester email."""
    normalized = (email or "").strip().lower()
    automatic = db.scalars(select(Asset).join(Employee, Asset.assigned_employee_id == Employee.id).where(
        func.lower(Employee.work_email) == normalized, Asset.is_archived.is_(False)).order_by(Asset.asset_tag)).all() if normalized else []
    explicit = db.scalars(select(Asset).where(Asset.id.in_(requested_ids))).all() if requested_ids else []
    return list({asset.id: asset for asset in [*automatic, *explicit]}.values())


def asset_dict(asset: Asset, detail=False, observed_user_email: str | None = None):
    data = {"id": asset.id, "asset_tag": asset.asset_tag, "hostname": asset.hostname,
            "serial_number": asset.serial_number, "name": asset.name, "manufacturer": asset.manufacturer,
            "model": asset.model, "category": asset.category, "asset_type": asset.asset_type,
            "status": asset.status, "condition": asset.condition,
            "assigned_employee_id": asset.assigned_employee_id,
            "assigned_employee": f"{asset.assigned_employee.first_name} {asset.assigned_employee.last_name}" if asset.assigned_employee else None,
            "assigned_employee_email": asset.assigned_employee.work_email if asset.assigned_employee else None,
            "observed_user_email": observed_user_email,
            "location": asset.location.name if asset.location else None,
            "department": asset.department.name if asset.department else None,
            "source": asset.source, "source_id": asset.source_id, "is_archived": asset.is_archived,
            "assetpilot_url": f"{settings.assetpilot_url.rstrip('/')}/Assets/Edit?id={asset.source_id}" if settings.assetpilot_enabled and asset.source == "AssetPilot" and asset.source_id is not None else None}
    if detail:
        data.update({"location_id": asset.location_id, "department_id": asset.department_id,
                     "vendor": asset.vendor, "purpose": asset.purpose, "company": asset.company,
                     "project": asset.project, "mac_address": asset.mac_address,
                     "purchase_date": asset.purchase_date, "purchase_cost_cents": asset.purchase_cost_cents,
                     "warranty_expiration": asset.warranty_expiration, "notes": asset.notes,
                     "source_reference": asset.source_reference, "extended_data": asset.extended_data})
    return data


def requester_profile_dict(db: Session, user: User) -> dict:
    employee = db.scalar(select(Employee).where(or_(Employee.user_id == user.id,
                                                     func.lower(Employee.work_email) == user.email.lower())))
    manager = db.get(Employee, employee.manager_id) if employee and employee.manager_id else None
    assets = ticket_assets_for_email(db, user.email)
    agent_conditions = [EndpointAgent.enrolled_by_user_id == user.id]
    if user.email:
        agent_conditions.append(func.lower(EndpointAgent.observed_user_email) == user.email.strip().lower())
    if employee:
        agent_conditions.append(EndpointAgent.matched_employee_id == employee.id)
    endpoint_agent = db.scalar(select(EndpointAgent).where(
        EndpointAgent.revoked_at.is_(None), or_(*agent_conditions)
    ).order_by(EndpointAgent.last_seen_at.desc()))
    latest_snapshot = db.scalar(select(AssetInventorySnapshot).where(
        AssetInventorySnapshot.agent_id == endpoint_agent.id
    ).order_by(AssetInventorySnapshot.received_at.desc())) if endpoint_agent else None
    inventory = latest_snapshot.inventory if latest_snapshot else {}
    device = inventory.get("device") or {}
    cpu = inventory.get("cpu") or {}
    memory = inventory.get("memory") or {}
    endpoint_summary = {
        "hostname": endpoint_agent.hostname or device.get("hostname") or "This computer",
        "status": endpoint_agent.status,
        "last_seen_at": endpoint_agent.last_seen_at,
        "cpu_percent": cpu.get("utilization_percent"),
        "memory_percent": memory.get("percent_used"),
    } if endpoint_agent else None
    return {
        "id": user.id, "display_name": user.display_name, "email": user.email,
        "phone": user.phone or user.ringcentral_extension_number or "",
        "employee_id": employee.employee_number if employee else "",
        "department": employee.department.name if employee and employee.department else "",
        "location": employee.location.name if employee and employee.location else "",
        "job_title": employee.job_title if employee else "",
        "manager": f"{manager.preferred_name or manager.first_name} {manager.last_name}" if manager else "",
        "source": employee.source if employee else "Local",
        "assets": [asset_dict(asset, True) for asset in assets],
        "endpoint_agent": endpoint_summary,
    }


def requester_snapshot(db: Session, requester: User, opened_by: User, assets: list[Asset]) -> dict:
    profile = requester_profile_dict(db, requester)
    profile["assets"] = [asset_dict(asset, True) for asset in assets]
    profile.update({
        "opened_by_id": opened_by.id, "opened_by_name": opened_by.display_name,
        "opened_by_email": opened_by.email, "requested_for_id": requester.id,
        "submitted_at": now().isoformat(),
    })
    def json_safe(value):
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [json_safe(item) for item in value]
        return value
    return json_safe(profile)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def secure_custom_data(ticket:Ticket,viewer:User|None,db:Session|None):
    values=dict(ticket.custom_data or {})
    if not ticket.form_definition_id or not db or not viewer:return values
    form=db.get(FormDefinition,ticket.form_definition_id);fields={field.get("key"):field for field in (form.fields or [])} if form else {}
    secured={}
    for key,value in values.items():
        field=fields.get(key,{}) ;classification=field.get("classification","internal" if field.get("visibility")=="technician_only" else "public")
        roles=field.get("access_roles") or []
        if viewer.role==Role.END_USER and classification!="public":continue
        if classification=="restricted" and viewer.role not in {Role.MANAGER,Role.ADMIN,Role.AUDITOR}:continue
        if roles and viewer.role.value not in roles:continue
        if field.get("mask_value") and value not in (None,""):
            text=str(value);secured[key]="••••"+text[-4:] if len(text)>4 else "••••"
        else:secured[key]=value
    return secured


def asset_device_health(db: Session | None, asset: Asset) -> dict:
    snapshot = db.scalar(select(AssetInventorySnapshot).where(
        AssetInventorySnapshot.asset_id == asset.id).order_by(
        AssetInventorySnapshot.collected_at.desc()).limit(1)) if db else None
    inventory = snapshot.inventory if snapshot else {}
    device = inventory.get("device") or {}
    network = inventory.get("network") or {}
    storage = inventory.get("storage") or {}
    adapters = network.get("adapters") or []
    primary_adapter = next((adapter for adapter in adapters if (adapter.get("ipv4") or [])), {})
    volumes = storage.get("volumes") or []
    return {
        "hostname": device.get("hostname") or asset.hostname,
        "ip_address": (primary_adapter.get("ipv4") or [None])[0],
        "uptime_started_at": (inventory.get("os") or {}).get("last_boot"),
        "cpu_percent": (inventory.get("cpu") or {}).get("utilization_percent"),
        "memory_percent": (inventory.get("memory") or {}).get("percent_used"),
        "manufacturer": device.get("manufacturer") or asset.manufacturer,
        "model": device.get("model") or asset.model,
        "drives": [{"name": volume.get("drive"), "label": volume.get("label"),
                    "total_bytes": volume.get("total_bytes"), "free_bytes": volume.get("free_bytes"),
                    "percent_free": volume.get("percent_free")} for volume in volumes],
        "collected_at": snapshot.collected_at if snapshot else None,
    }


def ticket_dict(ticket: Ticket, detail=False,viewer:User|None=None,db:Session|None=None):
    data = {"id": ticket.id, "number": ticket.number, "request_type": ticket.request_type, "subject": ticket.subject,
            "description": ticket.description, "requester_id": ticket.requester_id,
            "requester": ticket.requester.display_name, "requester_email": ticket.requester.email,
            "opened_by_id": ticket.opened_by_id or ticket.requester_id,
            "opened_by": ticket.opened_by.display_name if ticket.opened_by else ticket.requester.display_name,
            "requester_department": ticket.employee.department.name if ticket.employee and ticket.employee.department else None,
            "requester_location": ticket.employee.location.name if ticket.employee and ticket.employee.location else None,
            "employee_id": ticket.employee_id,
            "assigned_user_id": ticket.assigned_user_id,
            "assigned_user": ticket.assigned_user.display_name if ticket.assigned_user else None,
            "team_id": ticket.team_id, "team": ticket.team.name, "status": ticket.status.value,
            "priority": ticket.priority, "impact": ticket.impact, "urgency": ticket.urgency,
            "calculated_priority": ticket.calculated_priority, "priority_source": ticket.priority_source,
            "priority_override_reason": ticket.priority_override_reason, "impact_details": ticket.impact_details,
            "mode": ticket.mode, "level": ticket.level, "site_location": ticket.site_location,
            "category": ticket.category, "subcategory": ticket.subcategory, "restricted": ticket.restricted,
            "item": ticket.item, "emails_to_notify": ticket.emails_to_notify or [],
            "next_action_owner": ticket.next_action_owner, "next_action": ticket.next_action,
            "waiting_reason": ticket.waiting_reason, "route_reason": ticket.route_reason,
            "routing_trace": ticket.routing_trace or [], "sla_policy_key": ticket.sla_policy_key,
            "sla_explanation": ticket.sla_explanation,
            "first_response_due": ticket.first_response_due, "resolution_due": ticket.resolution_due,
            "first_responded_at": ticket.first_responded_at, "resolved_at": ticket.resolved_at,
            "resolution_summary": ticket.resolution_summary, "reopened_count": ticket.reopened_count,
            "created_at": ticket.created_at, "updated_at": ticket.updated_at,
            "form_definition_id": ticket.form_definition_id,
            "requester_snapshot": ticket.requester_snapshot or {},
            "sla_state": "breached" if aware(ticket.resolution_due) < now() and ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED)
                         else "warning" if aware(ticket.resolution_due) < now() + timedelta(hours=4) and ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED)
                         else "on_track"}
    if detail:
        data["assets"] = [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname,
                           "serial_number": a.serial_number, "manufacturer": a.manufacturer, "model": a.model,
                           "asset_type": a.asset_type, "status": a.status, "condition": a.condition,
                           "location": a.location.name if a.location else None,
                           "assigned_to": f"{a.assigned_employee.first_name} {a.assigned_employee.last_name}" if a.assigned_employee else None,
                           "assigned_email": a.assigned_employee.work_email if a.assigned_employee else None,
                           "warranty_expiration": a.warranty_expiration,
                           "device_health": asset_device_health(db, a)} for a in ticket.assets]
        allowed_message_kinds = {
            Role.END_USER: {"public"},
            Role.TECHNICIAN: {"public", "internal"},
            Role.TEAM_LEAD: {"public", "internal"},
            Role.MANAGER: {"public", "internal", "restricted"},
            Role.ADMIN: {"public", "internal", "restricted"},
            Role.AUDITOR: {"public", "internal", "restricted"},
        }.get(viewer.role, set()) if viewer else set()
        data["messages"] = [{"id": m.id, "body": m.body, "kind": m.kind, "source": m.source,
                             "author": m.author.display_name if m.author else "Email requester", "created_at": m.created_at}
                            for m in sorted(ticket.messages, key=lambda x: x.created_at)
                            if m.kind in allowed_message_kinds]
        data["custom_data"] = secure_custom_data(ticket,viewer,db)
        data["attachments"] = [{"id": item.id, "name": item.original_name, "content_type": item.content_type,
                                "size_bytes": item.size_bytes, "created_at": item.created_at}
                               for item in sorted(ticket.attachments, key=lambda row: row.created_at)]
        if ticket.form_definition_id:
            form = getattr(ticket, "_form_definition", None)
            data["form"] = {"id": form.id, "name": form.name, "fields": form.fields} if form else None
    return data


@app.get("/api/health/live")
def live(): return {"status": "ok", "version": __version__}


@app.get("/api/health/ready")
def ready(db: Session = Depends(get_db)):
    """Load-balancer readiness probe. It intentionally exposes no configuration details."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "Application database is unavailable")
    return {"status": "ready", "version": __version__}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = payload.username.strip().lower()
    user = db.scalar(select(User).where(or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier)))
    if not user:
        audit(db, "login.failed", "user", None, source_ip=request.client.host if request.client else None,
              new={"identifier": identifier, "reason": "unknown account"})
        db.commit(); time.sleep(.15)
        raise HTTPException(401, "Invalid username or password")
    db.info["organization_id"] = user.organization_id
    locked = user.locked_until and user.locked_until.replace(tzinfo=user.locked_until.tzinfo or timezone.utc) > now()
    if locked or not user.active:
        audit(db, "login.failed", "user", user.id, source_ip=request.client.host if request.client else None,
              new={"reason": "account unavailable"}); db.commit()
        raise HTTPException(423, "Account is temporarily unavailable")
    if user.auth_source == "Microsoft Entra ID" and user.role != Role.ADMIN:
        audit(db, "login.failed", "user", user.id, source_ip=request.client.host if request.client else None,
              new={"reason": "Microsoft sign-in required"}); db.commit()
        raise HTTPException(401, "Use Sign in with Microsoft for this account")
    if not verify_password(user.password_hash, payload.password):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.login_attempts:
            user.locked_until = now() + timedelta(minutes=settings.lockout_minutes)
        audit(db, "login.failed", "user", user.id, source_ip=request.client.host if request.client else None,
              new={"failed_attempts": user.failed_attempts}); db.commit()
        raise HTTPException(401, "Invalid username or password")
    user.failed_attempts = 0; user.locked_until = None; user.last_login_at = now()
    raw, csrf, _ = create_session(db, user)
    audit(db, "login.succeeded", "user", user.id, actor_id=user.id,
          source_ip=request.client.host if request.client else None)
    db.commit()
    response.set_cookie("itsm_session", raw, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.session_minutes * 60, path="/")
    response.headers["X-CSRF-Token"] = csrf
    return {"user": user_dict(user, db), "csrf_token": csrf}


@app.get("/api/auth/microsoft/status")
def microsoft_status(db: Session = Depends(get_db)):
    """Expose only whether the deployment is ready for Microsoft sign-in."""
    return microsoft_sign_in_status(db)


@app.get("/api/auth/microsoft/start")
def microsoft_start(db: Session = Depends(get_db)):
    return RedirectResponse(microsoft_authorization_url(db), status_code=303)


@app.get("/api/auth/me")
def me(session: Session = Depends(get_current_session), db: Session = Depends(get_db)):
    return {"user": user_dict(session.user, db), "csrf_token": session.csrf_token}


@app.patch("/api/auth/profile")
def update_own_profile(payload: SelfProfileUpdate, session: Session = Depends(get_current_session), db: Session = Depends(get_db)):
    user = session.user; email = str(payload.email).strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email, User.id != user.id)):
        raise HTTPException(409, "That email address is already used by another account")
    previous = {"display_name": user.display_name, "email": user.email, "phone": user.phone or ""}
    user.display_name = payload.display_name.strip(); user.email = email; user.phone = payload.phone.strip()
    employee = db.scalar(select(Employee).where(or_(Employee.user_id == user.id, func.lower(Employee.work_email) == previous["email"].lower())))
    if employee:
        employee.work_email = email
    audit(db, "profile.updated", "user", user.id, user.id, previous,
          {"display_name": user.display_name, "email": email, "phone": user.phone})
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "That email address is already used by another account")
    return user_dict(user, db)


@app.post("/api/auth/logout")
def logout(response: Response, session: Session = Depends(get_current_session), db: Session = Depends(get_db)):
    audit(db, "logout", "user", session.user_id, actor_id=session.user_id); db.delete(session); db.commit()
    response.delete_cookie("itsm_session", path="/")
    return {"ok": True}


@app.post("/api/auth/change-password")
def change_password(payload: PasswordChangeIn, session: Session = Depends(get_current_session), db: Session = Depends(get_db)):
    if not verify_password(session.user.password_hash, payload.current_password):
        raise HTTPException(400, "Current password is incorrect")
    errors = validate_password(payload.new_password)
    if errors: raise HTTPException(422, errors)
    session.user.password_hash = hash_password(payload.new_password); session.user.must_change_password = False
    audit(db, "password.changed", "user", session.user_id, actor_id=session.user_id); db.commit()
    return {"ok": True}


@app.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordIn, request: Request, db: Session = Depends(get_db)):
    """Issue an expiring, single-use reset link without revealing account existence."""
    email = str(payload.email).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        employee = db.scalar(select(Employee).where(func.lower(Employee.work_email) == email,
                                                      Employee.employment_status == "Active"))
        if employee:
            db.info["organization_id"] = employee.organization_id
            user = ensure_asset_employee_user(db, employee)
    if user and user.active and user.auth_source in {"Local", "AssetPilot"}:
        db.info["organization_id"] = user.organization_id
        for existing in db.scalars(select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))).all():
            existing.used_at = now()
        raw = secrets.token_urlsafe(48)
        reset = PasswordResetToken(user_id=user.id, token_hash=token_hash(raw),
                                   expires_at=now() + timedelta(minutes=30),
                                   requested_ip=request.client.host if request.client else "")
        db.add(reset)
        link = f"{settings.public_url.rstrip('/')}/?reset_token={raw}#reset-password"
        db.add(Notification(user_id=user.id, event="password.reset_requested",
                            title="Reset your Northstar Desk password",
                            body=f"Use this secure link within 30 minutes to choose a password:\n{link}",
                            delivery_status="pending_email"))
        audit(db, "password.reset_requested", "user", user.id,
              source_ip=request.client.host if request.client else None)
    db.commit()
    return {"ok": True, "message": "If that email belongs to an active local account, a password setup link has been sent."}


@app.post("/api/auth/reset-password")
def reset_password(payload: PasswordResetIn, request: Request, db: Session = Depends(get_db)):
    reset = db.scalar(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash(payload.token), PasswordResetToken.used_at.is_(None)))
    expiry = reset.expires_at.replace(tzinfo=reset.expires_at.tzinfo or timezone.utc) if reset else None
    if not reset or not expiry or expiry <= now():
        raise HTTPException(400, "This password link is invalid or has expired. Request a new link.")
    errors = validate_password(payload.new_password)
    if errors:
        raise HTTPException(422, errors)
    user = db.get(User, reset.user_id)
    if not user or not user.active:
        raise HTTPException(400, "This password link is invalid or has expired. Request a new link.")
    db.info["organization_id"] = user.organization_id
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.failed_attempts = 0
    user.locked_until = None
    reset.used_at = now()
    db.query(LoginSession).filter(LoginSession.user_id == user.id).delete(synchronize_session=False)
    audit(db, "password.reset_completed", "user", user.id, actor_id=user.id,
          source_ip=request.client.host if request.client else None)
    db.commit()
    return {"ok": True, "message": "Password saved. You can now sign in with your email address."}


@app.get("/api/bootstrap")
def bootstrap(user: User = Depends(current_user), db: Session = Depends(get_db)):
    teams = db.scalars(select(Team).order_by(Team.name)).all()
    # Keep the assignment selector aligned with the routing engine. Managers and
    # administrators can be eligible team members and must remain selectable when
    # a ticket is assigned to them.
    techs = db.scalars(select(User).where(User.role.in_(STAFF_ROLES), User.active.is_(True))).all()
    queues = db.scalars(select(SupportQueue).where(SupportQueue.active.is_(True)).order_by(SupportQueue.name)).all()
    memberships = db.scalars(select(TeamMembership).where(TeamMembership.active.is_(True))).all()
    membership_team_ids: dict[int, set[int]] = {}
    for membership in memberships:
        membership_team_ids.setdefault(membership.user_id, set()).add(membership.team_id)
    queue_eligibility = db.scalars(select(QueueTeamEligibility).where(QueueTeamEligibility.active.is_(True))).all()
    eligible_team_ids: dict[int, set[int]] = {}
    for item in queue_eligibility:
        eligible_team_ids.setdefault(item.queue_id, set()).add(item.team_id)
    assets_query = select(Asset).order_by(Asset.asset_tag)
    if user.role == Role.END_USER:
        employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
        assets_query = assets_query.where(Asset.assigned_employee_id == (employee.id if employee else -1))
    requesters = db.scalars(select(User).where(User.active.is_(True)).order_by(User.display_name)).all() if user.role in STAFF_ROLES else [user]
    routing_config = db.scalar(select(ConfigItem).where(ConfigItem.section == "assignment"))
    team_config = db.scalar(select(ConfigItem).where(ConfigItem.section == "teams"))
    routing_method = ((routing_config.value or {}).get("method") if routing_config else None) or ((team_config.value or {}).get("routing_mode") if team_config else None) or "least_active"
    organization = db.get(Organization, user.organization_id)
    return {"user": user_dict(user, db), "organization": {"id": organization.id, "name": organization.name, "timezone": organization.timezone, "logo_url": organization.logo_url} if organization else None,
            "teams": [{"id": t.id, "name": t.name, "queue": t.queue_name} for t in teams],
            "queues": [{"id": queue.id, "name": queue.name, "team_id": queue.team_id,
                        "team": queue.team.name if queue.team else None,
                        "technician_ids": [tech.id for tech in techs if membership_team_ids.get(tech.id, set()) & (eligible_team_ids.get(queue.id) or {queue.team_id})]}
                       for queue in queues],
            "technicians": [user_dict(t, db) for t in techs],
            "requesters": [{"id": r.id, "display_name": r.display_name, "email": r.email, "role": r.role.value} for r in requesters],
            "requester_profiles": [requester_profile_dict(db, r) for r in requesters],
            "routing_method": routing_method,
            "assets": [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname, "model": a.model,
                        "asset_type": a.asset_type, "status": a.status,
                        "location": a.location.name if a.location else None,
                        "assigned_to": f"{a.assigned_employee.first_name} {a.assigned_employee.last_name}" if a.assigned_employee else None,
                        "assigned_email": a.assigned_employee.work_email if a.assigned_employee else None}
                       for a in db.scalars(assets_query).all()],
            "announcements": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity} for a in db.scalars(select(Announcement).where(Announcement.active.is_(True))).all()]}


@app.get("/api/tickets")
def list_tickets(view: str = "all", q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Ticket).where(visible_ticket_filter(user))
    closed = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
    filters = {
        "open": Ticket.status.notin_(closed), "unassigned": Ticket.assigned_user_id.is_(None) & Ticket.status.notin_(closed),
        "mine": (Ticket.assigned_user_id == user.id) & Ticket.status.notin_(closed), "team": (Ticket.team_id == user.team_id) & Ticket.status.notin_(closed),
        "new": Ticket.status == TicketStatus.NEW, "high": Ticket.priority.in_(["Critical", "High"]) & Ticket.status.notin_(closed),
        "waiting_user": Ticket.status == TicketStatus.WAITING_USER,
        "waiting_vendor": Ticket.status == TicketStatus.WAITING_VENDOR,
        "waiting_approval": Ticket.status == TicketStatus.WAITING_APPROVAL,
        "resolved": Ticket.status == TicketStatus.RESOLVED, "closed": Ticket.status == TicketStatus.CLOSED,
        "breached": (Ticket.resolution_due < now()) & Ticket.status.notin_(closed),
        "approaching": (Ticket.resolution_due >= now()) & (Ticket.resolution_due < now() + timedelta(hours=4)) & Ticket.status.notin_(closed),
    }
    if view in filters: stmt = stmt.where(filters[view])
    if q:
        term = f"%{q}%"; stmt = stmt.join(User, Ticket.requester_id == User.id).where(or_(
            Ticket.number.ilike(term), Ticket.subject.ilike(term), Ticket.description.ilike(term),
            User.display_name.ilike(term), User.email.ilike(term), Ticket.category.ilike(term)))
    return [ticket_dict(t) for t in db.scalars(stmt.order_by(Ticket.updated_at.desc()).limit(250)).unique().all()]


@app.get("/api/tickets/counts")
def ticket_counts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    closed = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
    filters = {
        "open": Ticket.status.notin_(closed), "unassigned": Ticket.assigned_user_id.is_(None) & Ticket.status.notin_(closed),
        "mine": (Ticket.assigned_user_id == user.id) & Ticket.status.notin_(closed), "team": (Ticket.team_id == user.team_id) & Ticket.status.notin_(closed),
        "new": Ticket.status == TicketStatus.NEW, "high": Ticket.priority.in_(["Critical", "High"]) & Ticket.status.notin_(closed),
        "waiting_user": Ticket.status == TicketStatus.WAITING_USER, "waiting_vendor": Ticket.status == TicketStatus.WAITING_VENDOR,
        "waiting_approval": Ticket.status == TicketStatus.WAITING_APPROVAL, "resolved": Ticket.status == TicketStatus.RESOLVED,
        "closed": Ticket.status == TicketStatus.CLOSED,
        "breached": (Ticket.resolution_due < now()) & Ticket.status.notin_(closed),
        "approaching": (Ticket.resolution_due >= now()) & (Ticket.resolution_due < now() + timedelta(hours=4)) & Ticket.status.notin_(closed),
    }
    base = visible_ticket_filter(user)
    counts = {name: db.scalar(select(func.count(Ticket.id)).where(base, clause)) or 0 for name, clause in filters.items()}
    # End users get a complete, searchable history of their own requests.  The
    # visibility predicate still limits this count to tickets they may view.
    if user.role == Role.END_USER:
        counts["history"] = db.scalar(select(func.count(Ticket.id)).where(base)) or 0
    counts["reopened"] = db.scalar(
        select(func.count(Ticket.id)).where(base, Ticket.reopened_count > 0, Ticket.status.notin_(closed))
    ) or 0
    return counts


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.form_definition_id:
        raise HTTPException(422, "Custom forms must be submitted through the form submission endpoint")
    warnings = sensitive_warnings(payload.subject + " " + payload.description)
    priority = priority_for(payload.impact, payload.urgency)
    category = {"Request access": "Access", "Request software": "Software", "Request equipment": "Hardware",
                "New employee request": "Onboarding"}.get(payload.request_type, "General")
    requester = user
    if payload.requester_id is not None and payload.requester_id != user.id:
        if user.role not in STAFF_ROLES: raise HTTPException(403, "Only IT staff can create requests for another user")
        requester = db.get(User, payload.requester_id)
        if not requester or not requester.active: raise HTTPException(422, "Requester is not an active application user")
    employee = db.scalar(select(Employee).where(Employee.user_id == requester.id))
    matched_assets = ticket_assets_for_email(db, requester.email, payload.asset_ids)
    requester_email = (requester.email or "").strip().lower()
    requester_domain = requester_email.rsplit("@", 1)[1] if "@" in requester_email else ""
    routing_sample = {
        "request_type": payload.request_type, "status": "New", "mode": "Portal", "level": "User",
        "impact": payload.impact, "urgency": payload.urgency, "priority": priority,
        "category": category, "subcategory": "", "item": "", "location_name": "",
        "requester": requester_email, "requester_email": requester_email,
        "requester_domain": requester_domain, "requester_department": "",
        "organization": str(requester.organization_id), "channel": "portal",
        "keywords": f"{payload.subject}\n{payload.description}".strip(),
    }
    team, tech, reason, route_trace = route_incident(db, routing_sample, requester)
    first_due, resolution_due = sla_dates(priority)
    ticket = Ticket(number=next_ticket_number(db, payload.request_type), request_type=payload.request_type,
                    subject=payload.subject, description=payload.description, requester_id=requester.id, opened_by_id=user.id,
                    employee_id=employee.id if employee else None,
                    team_id=team.id, assigned_user_id=tech.id if tech else None,
                    status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW, priority=priority,
                    impact=payload.impact, urgency=payload.urgency, category=category, restricted=payload.restricted,
                    route_reason=reason, routing_trace=route_trace,
                    first_response_due=first_due, resolution_due=resolution_due,
                    requester_snapshot=requester_snapshot(db, requester, user, matched_assets))
    ticket.assets = matched_assets
    db.add(ticket); db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id, body=payload.description, kind="public"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="created", actor_id=user.id,
                         new_value={"status": ticket.status.value, "team": team.name, "assignee": tech.display_name if tech else None}))
    audit(db, "ticket.created", "ticket", ticket.id, user.id, new={"number": ticket.number, "route_reason": reason},
          source_ip=request.client.host if request.client else None)
    notify(db, requester.id, "ticket.created", f"[{ticket.number}] Request received: {ticket.subject}", "Your request was received.", ticket.id, email=True)
    notify(db, tech.id if tech else None, "ticket.assigned", f"[{ticket.number}] Assigned: {ticket.subject}", ticket.subject, ticket.id, email=True)
    if not tech: fail_automation(db, "assignment", "No available technician", {"ticket_number": ticket.number}, "ticket", ticket.id)
    db.commit(); db.refresh(ticket)
    return {"ticket": ticket_dict(ticket, True,user,db), "warnings": warnings}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket): raise HTTPException(404, "Ticket not found")
    history = db.scalars(select(TicketHistory).where(TicketHistory.ticket_id == ticket.id).order_by(TicketHistory.created_at)).all()
    result = ticket_dict(ticket, True,user,db)
    if ticket.form_definition_id:
        form = db.get(FormDefinition, ticket.form_definition_id)
        result["form"] = {"id": form.id, "name": form.name, "fields": form.fields} if form else None
    approval = db.scalar(select(ApprovalRequest).where(ApprovalRequest.ticket_id == ticket.id))
    if approval:
        result["approval"] = approval_dict(approval, db)
    checklists = db.scalars(select(TicketChecklist).where(TicketChecklist.ticket_id == ticket.id).order_by(TicketChecklist.id)).all()
    result["checklists"] = [{"id": item.id, "name": item.name, "items": item.items or [], "status": item.status,
                              "required_for_closure": item.required_for_closure, "completed_at": item.completed_at} for item in checklists]
    if user.role != Role.END_USER:
        result["history"] = [{"event_type": h.event_type, "previous": h.previous_value, "new": h.new_value,
                              "reason": h.reason, "created_at": h.created_at} for h in history]
    return result


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketUpdate, user: User = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket): raise HTTPException(404, "Ticket not found")
    changes = payload.model_dump(exclude_none=True); previous = {}
    if "status" in changes:
        try: changes["status"] = TicketStatus(changes["status"])
        except ValueError: raise HTTPException(422, "Invalid status")
    if "priority" in changes and changes["priority"] != ticket.priority and not changes.get("priority_override_reason"):
        raise HTTPException(422, "A reason is required for a manual priority override")
    if "priority" in changes and changes["priority"] != ticket.priority and not has_permission(db, user, "incidents.override_priority"):
        raise HTTPException(403, "You do not have permission to override priority")
    if changes.get("assigned_user_id") is not None and not db.get(User, changes["assigned_user_id"]):
        raise HTTPException(422, "Assigned technician is not in this organization")
    if changes.get("team_id") is not None and not db.get(Team, changes["team_id"]):
        raise HTTPException(422, "Team is not in this organization")
    for field, value in changes.items():
        old = getattr(ticket, field); previous[field] = old.value if isinstance(old, enum.Enum) else old
        setattr(ticket, field, value)
    if "priority" in changes and changes["priority"] != ticket.calculated_priority:
        ticket.priority_source = "overridden"
    if "status" in changes:
        old_status = str(previous.get("status", ticket.status.value))
        sla_pause_transition(db, ticket, old_status, changes["status"].value)
        if ticket.status == TicketStatus.RESOLVED:
            if not ticket.resolution_summary: raise HTTPException(422, "Resolution summary is required")
            incomplete = db.scalars(select(TicketChecklist).where(TicketChecklist.ticket_id == ticket.id,
                                    TicketChecklist.required_for_closure.is_(True), TicketChecklist.status != "Completed")).all()
            if incomplete: raise HTTPException(422, "Complete required checklists before resolving: " + ", ".join(item.name for item in incomplete))
            ticket.resolved_at = now(); ticket.next_action_owner = "Requester"; ticket.next_action = "Confirm resolution"
            notify(db, ticket.requester_id, "ticket.resolved", f"[{ticket.number}] Resolved: {ticket.subject}", ticket.resolution_summary or "Resolved", ticket.id, email=True)
        elif ticket.status == TicketStatus.CLOSED:
            ticket.closed_at = now()
            notify(db,ticket.requester_id,"ticket.closed",f"[{ticket.number}] Closed: {ticket.subject}","Your request is now closed.",ticket.id,email=True)
    if "assigned_user_id" in changes: notify(db, ticket.assigned_user_id, "ticket.assigned", f"[{ticket.number}] Assigned: {ticket.subject}", ticket.subject, ticket.id, email=True)
    db.add(TicketHistory(ticket_id=ticket.id, event_type="updated", actor_id=user.id, previous_value=previous,
                         new_value={k: v.value if isinstance(v, enum.Enum) else v for k, v in changes.items()},
                         reason=changes.get("priority_override_reason")))
    audit(db, "ticket.updated", "ticket", ticket.id, user.id, previous, {k: str(v) for k, v in changes.items()})
    db.commit(); db.refresh(ticket); return ticket_dict(ticket, True,user,db)


@app.post("/api/tickets/{ticket_id}/reassign")
def reassign_ticket(ticket_id: int, payload: TicketReassignment, user: User = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)):
    """Transfer a ticket through an explicit queue choice, with an auditable owner change."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket):
        raise HTTPException(404, "Ticket not found")
    if ticket.status in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED):
        raise HTTPException(422, "Reopen the ticket before assigning it to another queue")
    queue = db.get(SupportQueue, payload.queue_id)
    if not queue or not queue.active:
        raise HTTPException(422, "Select an active queue")

    eligible_links = db.scalars(select(QueueTeamEligibility).where(
        QueueTeamEligibility.queue_id == queue.id, QueueTeamEligibility.active.is_(True))).all()
    eligible_team_ids = {link.team_id for link in eligible_links} or {queue.team_id}
    assignee = None
    if payload.assigned_user_id is not None:
        assignee = db.get(User, payload.assigned_user_id)
        if not assignee or not assignee.active or assignee.role not in STAFF_ROLES:
            raise HTTPException(422, "Select an active IT technician")
        is_eligible = db.scalar(select(TeamMembership.id).where(
            TeamMembership.user_id == assignee.id,
            TeamMembership.team_id.in_(eligible_team_ids),
            TeamMembership.active.is_(True),
        ))
        if not is_eligible:
            raise HTTPException(422, "The selected technician is not eligible for this queue")

    previous = {
        "team_id": ticket.team_id,
        "team": ticket.team.name if ticket.team else None,
        "assigned_user_id": ticket.assigned_user_id,
        "assigned_user": ticket.assigned_user.display_name if ticket.assigned_user else None,
        "status": ticket.status.value,
    }
    ticket.team_id = queue.team_id
    ticket.assigned_user_id = assignee.id if assignee else None
    if assignee and ticket.status == TicketStatus.NEW:
        ticket.status = TicketStatus.ASSIGNED
    ticket.next_action_owner = assignee.display_name if assignee else queue.team.name
    ticket.next_action = "Manual assignment"
    ticket.route_reason = f"Manually reassigned by {user.display_name} to {queue.name}"
    if assignee:
        ticket.route_reason += f"; assigned to {assignee.display_name}"
    if payload.reason:
        ticket.route_reason += f". {payload.reason}"
    current = {"queue_id": queue.id, "queue": queue.name, "team_id": ticket.team_id,
               "team": queue.team.name, "assigned_user_id": ticket.assigned_user_id,
               "assigned_user": assignee.display_name if assignee else None,
               "status": ticket.status.value}
    db.add(TicketHistory(ticket_id=ticket.id, event_type="reassigned", actor_id=user.id,
                         previous_value=previous, new_value=current, reason=payload.reason))
    audit(db, "ticket.reassigned", "ticket", ticket.id, user.id, previous, current)
    if assignee:
        notify(db, assignee.id, "ticket.assigned", f"[{ticket.number}] Assigned: {ticket.subject}",
               f"This ticket was manually assigned to you from {queue.name}.", ticket.id, email=True)
    db.commit(); db.refresh(ticket)
    return ticket_dict(ticket, True, user, db)


@app.post("/api/tickets/{ticket_id}/messages")
def add_message(ticket_id: int, payload: MessageCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket): raise HTTPException(404, "Ticket not found")
    if payload.kind != "public" and user.role == Role.END_USER: raise HTTPException(403, "Internal notes are for IT staff")
    if payload.kind == "restricted" and user.role not in (Role.MANAGER, Role.ADMIN): raise HTTPException(403, "Restricted note permission required")
    message = TicketMessage(ticket_id=ticket.id, author_id=user.id, body=payload.body, kind=payload.kind)
    db.add(message)
    if payload.kind == "public":
        if user.role == Role.END_USER:
            closed = close_ticket_from_requester_message(db, ticket, user, payload.body, "web")
            if not closed:
                notify(db, ticket.assigned_user_id, "user.replied", f"[{ticket.number}] Requester replied: {ticket.subject}", payload.body[:200], ticket.id, email=True)
            if not closed and ticket.status == TicketStatus.WAITING_USER: ticket.status = TicketStatus.IN_PROGRESS
        else:
            ticket.first_responded_at = ticket.first_responded_at or now()
            notify(db, ticket.requester_id, "technician.replied", f"[{ticket.number}] New response: {ticket.subject}", payload.body[:200], ticket.id, email=True)
    db.add(TicketHistory(ticket_id=ticket.id, event_type=f"{payload.kind}_message", actor_id=user.id))
    audit(db, f"ticket.{payload.kind}_message", "ticket", ticket.id, user.id)
    db.commit(); return {"ok": True, "warnings": sensitive_warnings(payload.body)}


@app.post("/api/tickets/{ticket_id}/confirm")
def confirm_resolution(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.requester_id != user.id or ticket.status != TicketStatus.RESOLVED: raise HTTPException(400, "Ticket is not eligible")
    ticket.status = TicketStatus.CLOSED; ticket.closed_at = now()
    notify(db,ticket.requester_id,"ticket.closed",f"[{ticket.number}] Closed: {ticket.subject}","You confirmed that this request is resolved.",ticket.id,email=True)
    audit(db, "ticket.closed_by_requester", "ticket", ticket.id, user.id); db.commit(); return {"ok": True}


@app.post("/api/tickets/{ticket_id}/reopen")
def reopen(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    resolved_at = ticket.resolved_at.replace(tzinfo=ticket.resolved_at.tzinfo or timezone.utc) if ticket and ticket.resolved_at else None
    if not ticket or not can_view_ticket(user, ticket) or ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED) or not resolved_at or resolved_at < now() - timedelta(days=settings.reopen_days):
        raise HTTPException(400, "Ticket is not eligible to reopen")
    ticket.status = TicketStatus.IN_PROGRESS; ticket.closed_at = None; ticket.reopened_count += 1
    audit(db, "ticket.reopened", "ticket", ticket.id, user.id); notify(db, ticket.assigned_user_id, "ticket.reopened", f"{ticket.number} reopened", ticket.subject, ticket.id,email=True)
    db.commit(); return {"ok": True}


@app.post("/api/tickets/bulk")
def bulk_update(payload: BulkUpdate, user: User = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)):
    if payload.assigned_user_id is not None and not db.get(User, payload.assigned_user_id):
        raise HTTPException(422, "Assigned technician is not in this organization")
    changed = 0
    for ticket in db.scalars(select(Ticket).where(Ticket.id.in_(payload.ticket_ids))).all():
        if not can_view_ticket(user, ticket): continue
        if payload.status: ticket.status = TicketStatus(payload.status)
        if payload.assigned_user_id is not None:
            ticket.assigned_user_id = payload.assigned_user_id
            notify(db,ticket.assigned_user_id,"ticket.assigned",f"[{ticket.number}] Assigned: {ticket.subject}",ticket.subject,ticket.id,email=True)
        audit(db, "ticket.bulk_updated", "ticket", ticket.id, user.id); changed += 1
    db.commit(); return {"updated": changed}


@app.get("/api/dashboard")
def dashboard(user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    base = visible_ticket_filter(user); open_status = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
    def count(*clauses): return db.scalar(select(func.count(Ticket.id)).where(base, *clauses)) or 0
    metrics = {"open": count(Ticket.status.notin_(open_status)), "unassigned": count(Ticket.assigned_user_id.is_(None), Ticket.status.notin_(open_status)),
               "high": count(Ticket.priority.in_(["Critical", "High"]), Ticket.status.notin_(open_status)),
               "approaching": count(Ticket.resolution_due.between(now(), now()+timedelta(hours=4)), Ticket.status.notin_(open_status)),
               "breached": count(Ticket.resolution_due < now(), Ticket.status.notin_(open_status)),
               "waiting_user": count(Ticket.status == TicketStatus.WAITING_USER), "waiting_vendor": count(Ticket.status == TicketStatus.WAITING_VENDOR),
               "created_today": count(Ticket.created_at >= now().replace(hour=0, minute=0, second=0, microsecond=0)),
               "resolved_today": count(Ticket.resolved_at >= now().replace(hour=0, minute=0, second=0, microsecond=0)),
               "reopened": db.scalar(select(func.sum(Ticket.reopened_count)).where(base)) or 0}
    categories = db.execute(select(Ticket.category, func.count(Ticket.id)).where(base).group_by(Ticket.category).order_by(func.count(Ticket.id).desc())).all()
    workload = db.execute(select(User.display_name, func.count(Ticket.id)).join(Ticket, Ticket.assigned_user_id == User.id).where(Ticket.status.notin_(open_status)).group_by(User.display_name)).all()
    oldest = db.scalars(select(Ticket).where(base, Ticket.status.notin_(open_status)).order_by(Ticket.created_at).limit(8)).all()
    responded = db.scalars(select(Ticket).where(base, Ticket.first_responded_at.is_not(None))).all()
    resolved = db.scalars(select(Ticket).where(base, Ticket.resolved_at.is_not(None))).all()
    def avg_hours(items, end):
        vals = [((getattr(t, end).replace(tzinfo=getattr(t, end).tzinfo or timezone.utc) - t.created_at.replace(tzinfo=t.created_at.tzinfo or timezone.utc)).total_seconds()/3600) for t in items]
        return round(sum(vals)/len(vals), 1) if vals else 0
    return {"metrics": metrics, "by_category": [{"label": a, "value": b} for a,b in categories],
            "workload": [{"label": a, "value": b} for a,b in workload], "oldest": [ticket_dict(t) for t in oldest],
            "average_first_response_hours": avg_hours(responded, "first_responded_at"), "average_resolution_hours": avg_hours(resolved, "resolved_at")}


@app.get("/api/reports/support")
def support_reports(user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    """Operational IT support scorecards and drill-down datasets."""
    current = now(); closed = {TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED}
    tickets = list(db.scalars(select(Ticket).where(visible_ticket_filter(user)).order_by(Ticket.updated_at.desc())).unique().all())
    opened = [t for t in tickets if t.status not in closed]
    resolved = [t for t in tickets if t.resolved_at]
    thirty_days_ago = current - timedelta(days=30)
    recent_resolved = [t for t in resolved if aware(t.resolved_at) >= thirty_days_ago]
    overdue = [t for t in opened if aware(t.resolution_due) < current]
    at_risk = [t for t in opened if current <= aware(t.resolution_due) < current + timedelta(hours=4)]

    def hours(ticket, end_field):
        end = getattr(ticket, end_field)
        return (aware(end) - aware(ticket.created_at)).total_seconds() / 3600 if end else None
    def average(values):
        useful = [value for value in values if value is not None]
        return round(sum(useful) / len(useful), 1) if useful else 0
    def distribution(items, getter):
        counts = {}
        for item in items:
            key = getter(item) or "Not specified"; counts[key] = counts.get(key, 0) + 1
        return [{"label": key, "value": value} for key, value in sorted(counts.items(), key=lambda row: (-row[1], row[0]))]
    def row(ticket):
        data = ticket_dict(ticket)
        data["age_days"] = max(0, (current - aware(ticket.created_at)).days)
        data["overdue_days"] = max(0, (current - aware(ticket.resolution_due)).days) if ticket.status not in closed else 0
        return data

    sla_met = [t for t in recent_resolved if aware(t.resolved_at) <= aware(t.resolution_due)]
    reopened_recent = [t for t in recent_resolved if t.reopened_count > 0]
    technicians = list(db.scalars(select(User).where(User.role.in_([Role.TECHNICIAN, Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN]))).all())
    technician_rows = []
    for tech in technicians:
        assigned_open = [t for t in opened if t.assigned_user_id == tech.id]
        completed = [t for t in recent_resolved if t.assigned_user_id == tech.id]
        technician_rows.append({"id": tech.id, "name": tech.display_name, "email": tech.email,
            "team": tech.team.name if tech.team else "Not assigned", "availability": tech.availability,
            "open": len(assigned_open), "high_priority": sum(t.priority in ("Critical", "High") for t in assigned_open),
            "overdue": sum(aware(t.resolution_due) < current for t in assigned_open), "resolved_30d": len(completed),
            "average_resolution_hours": average([hours(t, "resolved_at") for t in completed]),
            "sla_met_percent": round(sum(aware(t.resolved_at) <= aware(t.resolution_due) for t in completed) * 100 / len(completed), 1) if completed else 0})
    technician_rows.sort(key=lambda item: (-item["resolved_30d"], item["name"]))

    age_buckets = [{"label": "0–1 day", "value": 0}, {"label": "2–5 days", "value": 0},
                   {"label": "6–10 days", "value": 0}, {"label": "11–30 days", "value": 0}, {"label": "Over 30 days", "value": 0}]
    for ticket in opened:
        age = (current - aware(ticket.created_at)).days
        age_buckets[0 if age <= 1 else 1 if age <= 5 else 2 if age <= 10 else 3 if age <= 30 else 4]["value"] += 1
    trend = []
    for offset in range(29, -1, -1):
        day = (current - timedelta(days=offset)).date()
        trend.append({"date": day.isoformat(),
            "created": sum(aware(t.created_at).date() == day for t in tickets),
            "resolved": sum(t.resolved_at is not None and aware(t.resolved_at).date() == day for t in tickets)})

    return {
        "generated_at": current,
        "kpis": {"open": len(opened), "unassigned": sum(t.assigned_user_id is None for t in opened),
            "overdue": len(overdue), "at_risk": len(at_risk),
            "high_priority": sum(t.priority in ("Critical", "High") for t in opened),
            "created_today": sum(aware(t.created_at).date() == current.date() for t in tickets),
            "resolved_today": sum(t.resolved_at is not None and aware(t.resolved_at).date() == current.date() for t in tickets),
            "average_first_response_hours": average([hours(t, "first_responded_at") for t in tickets]),
            "average_resolution_hours": average([hours(t, "resolved_at") for t in recent_resolved]),
            "sla_met_percent": round(len(sla_met) * 100 / len(recent_resolved), 1) if recent_resolved else 0,
            "reopened_percent": round(len(reopened_recent) * 100 / len(recent_resolved), 1) if recent_resolved else 0},
        "open_items": [row(t) for t in sorted(opened, key=lambda t: aware(t.created_at))],
        "expired_items": [row(t) for t in sorted(overdue, key=lambda t: aware(t.resolution_due))],
        "technicians": technician_rows, "backlog_age": age_buckets, "volume_trend": trend,
        "by_status": distribution(tickets, lambda t: t.status.value),
        "by_priority": distribution(tickets, lambda t: t.priority),
        "by_category": distribution(tickets, lambda t: t.category),
        "by_team": distribution(opened, lambda t: t.team.name if t.team else None),
        "by_requester": distribution(tickets, lambda t: t.requester.display_name if t.requester else None)[:20],
    }


@app.get("/api/assets")
def assets(q: str = "", include_archived: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Asset)
    if not include_archived: stmt = stmt.where(Asset.is_archived.is_(False))
    if user.role == Role.END_USER:
        emp = db.scalar(select(Employee).where(Employee.user_id == user.id)); stmt = stmt.where(Asset.assigned_employee_id == (emp.id if emp else -1))
    if q: stmt = stmt.where(or_(Asset.asset_tag.ilike(f"%{q}%"), Asset.hostname.ilike(f"%{q}%"), Asset.serial_number.ilike(f"%{q}%")))
    records = db.scalars(stmt.order_by(Asset.asset_tag)).unique().all()
    asset_ids = [asset.id for asset in records]
    observed_users: dict[int, str] = {}
    if asset_ids:
        agents = db.scalars(select(EndpointAgent).where(
            EndpointAgent.asset_id.in_(asset_ids),
            EndpointAgent.revoked_at.is_(None),
        ).order_by(EndpointAgent.asset_id, EndpointAgent.last_seen_at.desc())).all()
        for agent in agents:
            if agent.asset_id not in observed_users and agent.observed_user_email:
                observed_users[agent.asset_id] = agent.observed_user_email
    return [asset_dict(asset, observed_user_email=observed_users.get(asset.id)) for asset in records]


@app.get("/api/assets/summary")
def asset_summary(user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    current = Asset.is_archived.is_(False)
    statuses = db.execute(select(Asset.status, func.count(Asset.id)).where(current).group_by(Asset.status)).all()
    return {"total": db.scalar(select(func.count(Asset.id)).where(current)) or 0,
            "assigned": db.scalar(select(func.count(Asset.id)).where(current, Asset.assigned_employee_id.is_not(None))) or 0,
            "unassigned": db.scalar(select(func.count(Asset.id)).where(current, Asset.assigned_employee_id.is_(None))) or 0,
            "archived": db.scalar(select(func.count(Asset.id)).where(Asset.is_archived.is_(True))) or 0,
            "warranty_expiring": db.scalar(select(func.count(Asset.id)).where(current, Asset.warranty_expiration.between(date.today(), date.today()+timedelta(days=90)))) or 0,
            "by_status": [{"label": label, "value": count} for label,count in statuses],
            "inventory_source": "Northstar Desk + AssetPilot" if settings.assetpilot_enabled else "Northstar Desk",
            "integration_status": "Unified inventory" if settings.assetpilot_enabled else "Native ITSM inventory",
            "assetpilot_url": settings.assetpilot_url.rstrip("/") if settings.assetpilot_enabled else None}


@app.get("/api/assets/metadata")
def asset_metadata(user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    return {"employees": [{"id": e.id, "name": f"{e.preferred_name or e.first_name} {e.last_name}", "email": e.work_email, "employee_number": e.employee_number}
                           for e in db.scalars(select(Employee).where(Employee.employment_status == "Active").order_by(Employee.last_name)).all()],
            "departments": [{"id": d.id, "name": d.name} for d in db.scalars(select(Department).order_by(Department.name)).all()],
            "locations": [{"id": item.id, "name": item.name} for item in db.scalars(select(Location).order_by(Location.name)).all()]}


@app.get("/api/assets/import/assetpilot/preview")
def preview_assetpilot(user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    if not settings.assetpilot_enabled:
        raise HTTPException(503, "AssetPilot integration is disabled. Northstar Desk inventory remains available.")
    try:
        result = assetpilot_preview()
        result["imported_assets"] = db.scalar(select(func.count(Asset.id)).where(Asset.source == "AssetPilot")) or 0
        result["imported_employees"] = db.scalar(select(func.count(Employee.id)).where(Employee.source == "AssetPilot")) or 0
        return result
    except FileNotFoundError as exc: raise HTTPException(404, str(exc))


@app.post("/api/assets/import/assetpilot")
def run_assetpilot_import(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if not settings.assetpilot_enabled:
        raise HTTPException(503, "AssetPilot integration is disabled. Northstar Desk inventory remains available.")
    try: result = import_assetpilot(db, actor_id=user.id)
    except FileNotFoundError as exc: raise HTTPException(404, str(exc))
    audit(db, "assetpilot.imported", "inventory", None, user.id, new=result); db.commit(); return result


@app.get("/api/integrations/assetpilot/status")
def assetpilot_status(user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR))):
    if not settings.assetpilot_enabled:
        return {"enabled": False, "running": False, "url": None, "message": "Optional integration is disabled"}
    return {"enabled": True, "running": assetpilot_healthy(), "url": settings.assetpilot_url.rstrip("/")}


@app.post("/api/integrations/assetpilot/create")
def open_assetpilot_create(user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER))):
    if not settings.assetpilot_enabled:
        raise HTTPException(503, "AssetPilot integration is disabled. Add the asset directly in Northstar Desk.")
    try: ensure_assetpilot_running()
    except (FileNotFoundError, TimeoutError) as exc: raise HTTPException(503, str(exc))
    return {"url": f"{settings.assetpilot_url.rstrip('/')}/Assets/Create"}


@app.post("/api/integrations/assetpilot/open/{asset_id}")
def open_assetpilot_asset(asset_id: int, user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    if not settings.assetpilot_enabled:
        raise HTTPException(503, "AssetPilot integration is disabled. This asset can be managed in Northstar Desk.")
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(404, "Asset not found")
    if asset.source != "AssetPilot" or asset.source_id is None: raise HTTPException(422, "This asset is maintained in ITSM")
    try: ensure_assetpilot_running()
    except (FileNotFoundError, TimeoutError) as exc: raise HTTPException(503, str(exc))
    return {"url": f"{settings.assetpilot_url.rstrip('/')}/Assets/Edit?id={asset.source_id}"}


@app.get("/api/assets/{asset_id}")
def asset_detail(asset_id: int, user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(404, "Asset not found")
    history = db.scalars(select(AssetHistory).where(AssetHistory.asset_id == asset.id).order_by(AssetHistory.created_at.desc())).all()
    related = db.scalars(select(Ticket).join(TicketAsset, Ticket.id == TicketAsset.ticket_id).where(TicketAsset.asset_id == asset.id, visible_ticket_filter(user)).order_by(Ticket.updated_at.desc())).all()
    result = asset_dict(asset, detail=True)
    result.update({"employee": {"id": asset.assigned_employee.id, "name": f"{asset.assigned_employee.first_name} {asset.assigned_employee.last_name}", "email": asset.assigned_employee.work_email} if asset.assigned_employee else None,
                   "history": [{"id": h.id, "event_type": h.event_type, "previous": h.previous_value, "new": h.new_value, "created_at": h.created_at} for h in history],
                   "tickets": [ticket_dict(t) for t in related]})
    return result


@app.post("/api/assets", status_code=201)
def create_asset(payload: AssetCreate, user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    if payload.assigned_employee_id is not None and not db.get(Employee, payload.assigned_employee_id): raise HTTPException(422, "Employee is not in this organization")
    if payload.location_id is not None and not db.get(Location, payload.location_id): raise HTTPException(422, "Location is not in this organization")
    if payload.department_id is not None and not db.get(Department, payload.department_id): raise HTTPException(422, "Department is not in this organization")
    asset = Asset(**payload.model_dump()); db.add(asset)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Asset tag, hostname, and serial number must be unique when provided")
    db.add(AssetHistory(asset_id=asset.id, event_type="created", new_value=payload.model_dump(mode="json"), actor_id=user.id))
    audit(db, "asset.created", "asset", asset.id, user.id, new={"asset_tag": asset.asset_tag}); db.commit(); return {"id": asset.id}


@app.patch("/api/assets/{asset_id}")
def update_asset(asset_id: int, payload: AssetUpdate, user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(404, "Asset not found")
    changes = payload.model_dump(exclude_unset=True); previous = {key: getattr(asset, key) for key in changes}
    if changes.get("location_id") is not None and not db.get(Location, changes["location_id"]): raise HTTPException(422, "Location is not in this organization")
    if changes.get("department_id") is not None and not db.get(Department, changes["department_id"]): raise HTTPException(422, "Department is not in this organization")
    for key,value in changes.items(): setattr(asset, key, value)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Asset tag, hostname, and serial number must be unique when provided")
    serialized = payload.model_dump(mode="json", exclude_unset=True)
    db.add(AssetHistory(asset_id=asset.id, event_type="updated", previous_value={k: str(v) if isinstance(v,date) else v for k,v in previous.items()}, new_value=serialized, actor_id=user.id))
    audit(db, "asset.updated", "asset", asset.id, user.id, previous={k: str(v) for k,v in previous.items()}, new=serialized); db.commit()
    return asset_dict(asset, detail=True)


@app.post("/api/assets/{asset_id}/assign")
def assign_asset(asset_id: int, payload: AssetAssign, user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.TECHNICIAN, Role.TEAM_LEAD)), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(404, "Asset not found")
    if payload.employee_id is not None and not db.get(Employee, payload.employee_id): raise HTTPException(422, "Employee not found")
    previous = {"employee_id": asset.assigned_employee_id, "status": asset.status}
    asset.assigned_employee_id = payload.employee_id; asset.status = payload.status
    new = {"employee_id": payload.employee_id, "status": payload.status}
    db.add(AssetHistory(asset_id=asset.id, event_type="assignment", previous_value=previous, new_value=new, actor_id=user.id))
    audit(db, "asset.assigned", "asset", asset.id, user.id, previous, new); db.commit(); return {"ok": True}


@app.get("/api/employees")
def employees(q: str = "", user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    stmt = select(Employee)
    if q: stmt = stmt.where(or_(Employee.first_name.ilike(f"%{q}%"), Employee.last_name.ilike(f"%{q}%"), Employee.work_email.ilike(f"%{q}%"), Employee.employee_number.ilike(f"%{q}%")))
    return [{"id": e.id, "employee_number": e.employee_number, "name": f"{e.preferred_name or e.first_name} {e.last_name}", "email": e.work_email,
             "department": e.department.name if e.department else None, "location": e.location.name if e.location else None,
             "job_title": e.job_title, "status": e.employment_status, "vip": e.vip, "source": e.source} for e in db.scalars(stmt.order_by(Employee.last_name)).all()]


@app.get("/api/employees/{employee_id}")
def employee_detail(employee_id: int, user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    employee = db.get(Employee, employee_id)
    if not employee: raise HTTPException(404, "Employee not found")
    assets = db.scalars(select(Asset).where(Asset.assigned_employee_id == employee.id).order_by(Asset.asset_tag)).all()
    tickets = db.scalars(select(Ticket).where(or_(Ticket.employee_id == employee.id, Ticket.requester_id == employee.user_id), visible_ticket_filter(user)).order_by(Ticket.updated_at.desc())).all()
    open_status = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
    return {"id": employee.id, "employee_number": employee.employee_number,
            "name": f"{employee.preferred_name or employee.first_name} {employee.last_name}", "email": employee.work_email,
            "department": employee.department.name if employee.department else None, "location": employee.location.name if employee.location else None,
            "job_title": employee.job_title, "employment_status": employee.employment_status, "support_region": employee.support_region,
            "vip": employee.vip, "source": employee.source, "start_date": employee.start_date, "end_date": employee.end_date,
            "assets": [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname, "model": a.model, "status": a.status} for a in assets],
            "open_tickets": [ticket_dict(t) for t in tickets if t.status not in open_status],
            "previous_tickets": [ticket_dict(t) for t in tickets if t.status in open_status]}


@app.get("/api/admin/users")
def users(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [user_dict(u, db) for u in db.scalars(select(User).order_by(User.display_name)).all()]


@app.post("/api/admin/users", status_code=201)
def create_user(payload: UserCreate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    errors = validate_password(payload.temporary_password)
    if errors: raise HTTPException(422, errors)
    if payload.team_id is not None and not db.get(Team, payload.team_id): raise HTTPException(422, "Team is not in this organization")
    account = User(username=payload.username.lower(), email=payload.email.lower(), display_name=payload.display_name,
                   role=Role(payload.role), team_id=payload.team_id, password_hash=hash_password(payload.temporary_password), must_change_password=True,
                   ringcentral_extension_number=payload.ringcentral_extension_number)
    db.add(account)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Username or email already exists")
    audit(db, "user.created", "user", account.id, user.id, new={"role": account.role.value}); db.commit(); return user_dict(account, db)


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: PasswordReset, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    account = db.get(User, user_id)
    if not account: raise HTTPException(404, "User not found")
    errors = validate_password(payload.temporary_password)
    if errors: raise HTTPException(422, errors)
    account.password_hash = hash_password(payload.temporary_password); account.must_change_password = True
    account.failed_attempts = 0; account.locked_until = None
    audit(db, "password.admin_reset", "user", account.id, user.id); db.commit(); return {"ok": True}


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    account = db.get(User, user_id)
    if not account: raise HTTPException(404, "User not found")
    changes = payload.model_dump(exclude_none=True); previous = {}
    if changes.get("team_id") is not None and not db.get(Team, changes["team_id"]): raise HTTPException(422, "Team is not in this organization")
    if "role" in changes: changes["role"] = Role(changes["role"])
    for field,value in changes.items():
        old = getattr(account, field); previous[field] = old.value if isinstance(old, enum.Enum) else old; setattr(account, field, value)
    audit(db, "user.updated", "user", account.id, user.id, previous, {k: str(v) for k,v in changes.items()}); db.commit()
    return user_dict(account, db)


@app.get("/api/admin/organization")
def get_organization(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organization = db.get(Organization, user.organization_id)
    if not organization: raise HTTPException(404, "Organization not found")
    return {"id": organization.id, "name": organization.name, "slug": organization.slug,
            "timezone": organization.timezone, "support_email": organization.support_email,
            "support_phone": organization.support_phone, "logo_url": organization.logo_url,
            "active": organization.active}


@app.patch("/api/admin/organization")
def update_organization(payload: OrganizationUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    organization = db.get(Organization, user.organization_id)
    if not organization: raise HTTPException(404, "Organization not found")
    previous = {key: getattr(organization, key) for key in type(payload).model_fields}
    for key, value in payload.model_dump().items(): setattr(organization, key, value)
    audit(db, "organization.updated", "organization", organization.id, user.id, previous, payload.model_dump())
    db.commit()
    return {"ok": True}


def group_dict(item: UserGroup, db: Session):
    memberships = db.execute(select(UserGroupMembership.user_id, UserGroupMembership.membership_role).where(UserGroupMembership.group_id == item.id)).all()
    return {"id": item.id, "name": item.name, "group_type": item.group_type, "description": item.description,
            "source": item.source, "active": item.active,
            "member_ids": [user_id for user_id, role in memberships if role == "member"],
            "owner_ids": [user_id for user_id, role in memberships if role == "owner"],
            "member_count": len(memberships), "created_at": item.created_at, "updated_at": item.updated_at}


@app.get("/api/admin/groups")
def admin_groups(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [group_dict(item, db) for item in db.scalars(select(UserGroup).order_by(UserGroup.name)).all()]


@app.post("/api/admin/groups", status_code=201)
def create_group(payload: GroupIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = UserGroup(**payload.model_dump(exclude={"member_ids", "owner_ids"})); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "A group with this name already exists")
    valid = set(db.scalars(select(User.id).where(User.id.in_([*payload.member_ids, *payload.owner_ids]))).all())
    db.add_all([UserGroupMembership(group_id=item.id, user_id=value, membership_role="owner" if value in payload.owner_ids else "member") for value in valid])
    audit(db, "group.created", "group", item.id, user.id, new={"name": item.name, "members": len(valid)}); db.commit(); return group_dict(item, db)


@app.patch("/api/admin/groups/{item_id}")
def update_group(item_id: int, payload: GroupIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(UserGroup, item_id)
    if not item: raise HTTPException(404, "Group not found")
    previous = group_dict(item, db)
    for key, value in payload.model_dump(exclude={"member_ids", "owner_ids"}).items(): setattr(item, key, value)
    db.query(UserGroupMembership).filter(UserGroupMembership.group_id == item.id).delete()
    valid = set(db.scalars(select(User.id).where(User.id.in_([*payload.member_ids, *payload.owner_ids]))).all())
    db.add_all([UserGroupMembership(group_id=item.id, user_id=value, membership_role="owner" if value in payload.owner_ids else "member") for value in valid])
    audit(db, "group.updated", "group", item.id, user.id, previous, {"name": item.name, "members": len(valid)}); db.commit(); return group_dict(item, db)


@app.delete("/api/admin/groups/{item_id}")
def delete_group(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(UserGroup, item_id)
    if not item: raise HTTPException(404, "Group not found")
    item.active = False; audit(db, "group.deactivated", "group", item.id, user.id); db.commit(); return {"ok": True, "archived": True}


def category_dict(item: ServiceCategory):
    return {"id": item.id, "name": item.name, "parent_id": item.parent_id, "level": item.level, "description": item.description,
            "sort_order": item.sort_order, "configuration": item.configuration or {}, "active": item.active}


@app.get("/api/admin/categories")
def admin_categories(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [category_dict(item) for item in db.scalars(select(ServiceCategory).order_by(ServiceCategory.sort_order, ServiceCategory.name)).all()]


@app.post("/api/admin/categories", status_code=201)
def create_category(payload: CategoryIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if payload.parent_id and not db.get(ServiceCategory, payload.parent_id): raise HTTPException(422, "Parent category not found")
    item = ServiceCategory(**payload.model_dump()); db.add(item); db.flush(); audit(db, "category.created", "category", item.id, user.id, new=payload.model_dump()); db.commit(); return category_dict(item)


@app.patch("/api/admin/categories/{item_id}")
def update_category(item_id: int, payload: CategoryIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(ServiceCategory, item_id)
    if not item: raise HTTPException(404, "Category not found")
    previous = category_dict(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, "category.updated", "category", item.id, user.id, previous, payload.model_dump()); db.commit(); return category_dict(item)


@app.delete("/api/admin/categories/{item_id}")
def delete_category(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(ServiceCategory, item_id)
    if not item: raise HTTPException(404, "Category not found")
    item.active = False; audit(db, "category.archived", "category", item.id, user.id); db.commit(); return {"ok": True, "archived": True}


def queue_dict(item: SupportQueue):
    return {"id": item.id, "name": item.name, "team_id": item.team_id, "team": item.team.name if item.team else None,
            "description": item.description, "assignment_strategy": item.assignment_strategy,
            "configuration": item.configuration or {}, "active": item.active}


@app.get("/api/admin/queues")
def admin_queues(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [queue_dict(item) for item in db.scalars(select(SupportQueue).order_by(SupportQueue.name)).all()]


@app.post("/api/admin/queues", status_code=201)
def create_queue(payload: QueueIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if not db.get(Team, payload.team_id): raise HTTPException(422, "Team not found")
    item = SupportQueue(**payload.model_dump()); db.add(item); db.flush(); audit(db, "queue.created", "queue", item.id, user.id, new=payload.model_dump()); db.commit(); return queue_dict(item)


@app.patch("/api/admin/queues/{item_id}")
def update_queue(item_id: int, payload: QueueIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(SupportQueue, item_id)
    if not item: raise HTTPException(404, "Queue not found")
    previous = queue_dict(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, "queue.updated", "queue", item.id, user.id, previous, payload.model_dump()); db.commit(); return queue_dict(item)


@app.delete("/api/admin/queues/{item_id}")
def delete_queue(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(SupportQueue, item_id)
    if not item: raise HTTPException(404, "Queue not found")
    item.active = False; audit(db, "queue.deactivated", "queue", item.id, user.id); db.commit(); return {"ok": True, "archived": True}


def routing_dict(item: RoutingRule):
    return {"id": item.id, "name": item.name, "priority_order": item.priority_order, "conditions": item.conditions or [], "actions": item.actions or {}, "active": item.active}


@app.get("/api/admin/routing-rules")
def admin_routing_rules(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [routing_dict(item) for item in db.scalars(select(RoutingRule).order_by(RoutingRule.priority_order, RoutingRule.name)).all()]


@app.post("/api/admin/routing-rules", status_code=201)
def create_routing_rule(payload: RoutingRuleIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = RoutingRule(**payload.model_dump()); db.add(item); db.flush(); audit(db, "routing_rule.created", "routing_rule", item.id, user.id, new=payload.model_dump()); db.commit(); return routing_dict(item)


@app.patch("/api/admin/routing-rules/{item_id}")
def update_routing_rule(item_id: int, payload: RoutingRuleIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(RoutingRule, item_id)
    if not item: raise HTTPException(404, "Routing rule not found")
    previous = routing_dict(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, "routing_rule.updated", "routing_rule", item.id, user.id, previous, payload.model_dump()); db.commit(); return routing_dict(item)


@app.post("/api/admin/routing-rules/test")
def test_routing_rule(sample: dict, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    for item in db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True)).order_by(RoutingRule.priority_order)).all():
        matched = all(str(sample.get(condition.get("field"), "")).lower() == str(condition.get("value", "")).lower() for condition in item.conditions)
        if matched: return {"matched": True, "rule": routing_dict(item), "result": item.actions}
    return {"matched": False, "rule": None, "result": {}}


@app.delete("/api/admin/routing-rules/{item_id}")
def delete_routing_rule(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(RoutingRule, item_id)
    if not item: raise HTTPException(404, "Routing rule not found")
    item.active = False; audit(db, "routing_rule.deactivated", "routing_rule", item.id, user.id); db.commit(); return {"ok": True}


def notification_rule_dict(item: NotificationRule):
    return {"id": item.id, "name": item.name, "trigger": item.trigger, "conditions": item.conditions or [],
            "recipients": item.recipients or [], "template": item.template or {}, "active": item.active}


@app.get("/api/admin/notification-rules")
def admin_notification_rules(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [notification_rule_dict(item) for item in db.scalars(select(NotificationRule).order_by(NotificationRule.name)).all()]


@app.post("/api/admin/notification-rules", status_code=201)
def create_notification_rule(payload: NotificationRuleIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = NotificationRule(**payload.model_dump()); db.add(item); db.flush(); audit(db, "notification_rule.created", "notification_rule", item.id, user.id, new={"name": item.name, "trigger": item.trigger}); db.commit(); return notification_rule_dict(item)


@app.patch("/api/admin/notification-rules/{item_id}")
def update_notification_rule(item_id: int, payload: NotificationRuleIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(NotificationRule, item_id)
    if not item: raise HTTPException(404, "Notification rule not found")
    previous = notification_rule_dict(item)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    audit(db, "notification_rule.updated", "notification_rule", item.id, user.id, previous, {"name": item.name, "trigger": item.trigger}); db.commit(); return notification_rule_dict(item)


@app.delete("/api/admin/notification-rules/{item_id}")
def delete_notification_rule(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(NotificationRule, item_id)
    if not item: raise HTTPException(404, "Notification rule not found")
    item.active = False; audit(db, "notification_rule.deactivated", "notification_rule", item.id, user.id); db.commit(); return {"ok": True}


def integration_dict(item: IntegrationConnection):
    return {"id": item.id, "kind": item.kind, "name": item.name, "provider": item.provider, "enabled": item.enabled,
            "configuration": item.configuration or {}, "status": item.status, "last_attempt_at": item.last_attempt_at,
            "last_success_at": item.last_success_at, "last_error": item.last_error, "records_processed": item.records_processed}


@app.get("/api/admin/integrations")
def admin_integrations(kind: str | None = None, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    stmt = select(IntegrationConnection)
    if kind: stmt = stmt.where(IntegrationConnection.kind == kind)
    return [integration_dict(item) for item in db.scalars(stmt.order_by(IntegrationConnection.kind, IntegrationConnection.name)).all()]


@app.post("/api/admin/integrations", status_code=201)
def create_integration(payload: IntegrationConnectionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = IntegrationConnection(**payload.model_dump(), status="Disabled" if not payload.enabled else "Disconnected"); db.add(item); db.flush()
    audit(db, "integration.created", "integration", item.id, user.id, new={"kind": item.kind, "provider": item.provider, "enabled": item.enabled}); db.commit(); return integration_dict(item)


@app.patch("/api/admin/integrations/{item_id}")
def update_integration(item_id: int, payload: IntegrationConnectionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(IntegrationConnection, item_id)
    if not item: raise HTTPException(404, "Integration not found")
    previous = {"name": item.name, "provider": item.provider, "enabled": item.enabled, "status": item.status}
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    item.status = "Disabled" if not item.enabled else "Disconnected"
    audit(db, "integration.updated", "integration", item.id, user.id, previous, {"name": item.name, "provider": item.provider, "enabled": item.enabled}); db.commit(); return integration_dict(item)


@app.post("/api/admin/integrations/{item_id}/test")
def test_integration(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(IntegrationConnection, item_id)
    if not item: raise HTTPException(404, "Integration not found")
    item.last_attempt_at = now(); configured = bool(item.configuration)
    item.status = "Disconnected" if item.enabled else "Disabled"
    item.last_error = "Connection credentials and provider adapter must be configured" if item.enabled and not configured else ("Provider adapter test is not yet connected" if item.enabled else "Integration is disabled")
    db.add(IntegrationLog(connection_id=item.id, level="warning", event="connection.test", details={"status": item.status, "message": item.last_error}))
    audit(db, "integration.tested", "integration", item.id, user.id, new={"status": item.status}); db.commit(); return integration_dict(item)


@app.get("/api/admin/integrations/{item_id}/logs")
def integration_logs(item_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if not db.get(IntegrationConnection, item_id): raise HTTPException(404, "Integration not found")
    return [{"id": row.id, "level": row.level, "event": row.event, "details": row.details, "created_at": row.created_at}
            for row in db.scalars(select(IntegrationLog).where(IntegrationLog.connection_id == item_id).order_by(IntegrationLog.created_at.desc()).limit(100)).all()]


@app.get("/api/admin/integrations/ringcentral/secrets")
def ringcentral_secret_status(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    present = integration_secret_status(db, "ringcentral")
    config = db.scalar(select(ConfigItem).where(ConfigItem.section == "ringcentral"))
    client_id = bool((config.value or {}).get("client_id")) if config else False
    return {"client_id": client_id, "client_secret": present.get("client_secret", False),
            "jwt_credential": present.get("jwt_credential", False),
            "connection_status": "Ready to connect" if client_id and present.get("client_secret") and present.get("jwt_credential") else "Credentials incomplete"}


@app.patch("/api/admin/integrations/ringcentral/secrets")
def update_ringcentral_secrets(payload: IntegrationSecretsUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    allowed = {"client_secret", "jwt_credential"}
    for name in payload.clear:
        if name in allowed: clear_integration_secret(db, "ringcentral", name)
    for name in allowed:
        value = getattr(payload, name)
        if value: set_integration_secret(db, "ringcentral", name, value)
    audit(db, "integration.credentials_changed", "integration", "ringcentral", user.id,
          new={"updated": [name for name in allowed if getattr(payload, name)], "cleared": [name for name in payload.clear if name in allowed]})
    db.commit()
    return ringcentral_secret_status(user, db)


@app.get("/api/admin/settings/{section}")
def get_settings(section: str, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    rows = db.scalars(select(ConfigItem).where(ConfigItem.section == section).order_by(ConfigItem.name)).all()
    result = []
    for row in rows:
        value = dict(row.value or {})
        if section == "assignment": value.setdefault("method", "least_active")
        result.append({"id": row.id, "section": row.section, "name": row.name,
                       "value": {k: ("••••••" if row.sensitive else v) for k,v in value.items()},
                       "description": row.description, "updated_at": row.updated_at})
    return result


@app.patch("/api/admin/settings/{item_id}")
def update_settings(item_id: int, payload: ConfigUpdate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(ConfigItem, item_id)
    if not item: raise HTTPException(404, "Configuration item not found")
    previous = item.value; item.value = payload.value
    audit(db, "configuration.changed", "config_item", item.id, user.id, previous, item.value)
    db.commit(); return {"ok": True, "updated_at": item.updated_at}


@app.get("/api/audit")
def audit_log(limit: int = Query(100, le=500), user: User = Depends(require_roles(Role.ADMIN, Role.AUDITOR, Role.MANAGER)), db: Session = Depends(get_db)):
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)).all()
    result=[]
    for event in events:
        values=event.new_value or {};actor=db.get(User,event.actor_id) if event.actor_id else None
        recipient_id=values.get("recipient_user_id") or values.get("user_id")
        recipient=db.get(User,recipient_id) if recipient_id else None
        notification=None
        if event.record_type=="notification" and event.record_id and (event.action=="notification.email_sent" or values.get("delivery_status")):
            try:notification=db.get(Notification,int(event.record_id))
            except (TypeError,ValueError):pass
        ticket_id=values.get("ticket_id") or (notification.ticket_id if notification else None)
        if not ticket_id and event.action=="notification.created" and not values.get("delivery_status"):ticket_id=event.record_id
        ticket=db.get(Ticket,int(ticket_id)) if ticket_id and str(ticket_id).isdigit() else None
        result.append({"id":event.id,"actor_id":event.actor_id,"actor":{"id":actor.id,"name":actor.display_name,"email":actor.email} if actor else None,
                       "action":event.action,"record_type":event.record_type,"record_id":event.record_id,"previous":event.previous_value,"new":event.new_value,
                       "details":{"recipient":{"id":recipient.id,"name":recipient.display_name,"email":recipient.email} if recipient else ({"id":recipient_id,"name":values.get("recipient_name"),"email":values.get("recipient_email")} if recipient_id or values.get("recipient_email") else None),
                                  "notification":{"id":notification.id,"event":notification.event,"subject":notification.title,"delivery_status":notification.delivery_status} if notification else None,
                                  "ticket":{"id":ticket.id,"number":ticket.number,"subject":ticket.subject} if ticket else None},
                       "source_ip":event.source_ip,"correlation_id":event.correlation_id,"created_at":event.created_at})
    return result


@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [{"id": n.id, "ticket_id": n.ticket_id, "event": n.event, "title": n.title, "body": n.body,
             "delivery_status": n.delivery_status, "read": n.read_at is not None, "created_at": n.created_at} for n in rows]


@app.get("/api/admin/failures")
def failures(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [{"id": f.id, "failure_type": f.failure_type, "summary": f.summary, "details": f.safe_details, "status": f.status,
             "retry_count": f.retry_count, "resolution_note": f.resolution_note, "created_at": f.created_at} for f in db.scalars(select(AutomationFailure).order_by(AutomationFailure.created_at.desc())).all()]


@app.post("/api/admin/failures/{failure_id}/resolve")
def resolve_failure(failure_id: int, payload: FailureResolve, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    failure = db.get(AutomationFailure, failure_id)
    if not failure: raise HTTPException(404, "Failure not found")
    failure.status = "Resolved"; failure.resolution_note = payload.resolution_note; failure.resolved_at = now()
    audit(db, "automation.resolved", "automation_failure", failure.id, user.id); db.commit(); return {"ok": True}


@app.get("/api/admin/health")
def health(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    db_ok = True
    try: db.execute(text("SELECT 1"))
    except Exception: db_ok = False
    mail_state = db.get(SystemState, "mailbox")
    worker_state = db.get(SystemState, "worker")
    migration = "unknown"
    try: migration = db.execute(text("SELECT version_num FROM alembic_version")).scalar() or "none"
    except Exception: pass
    backup_files = sorted((path for pattern in ("itsm-*.sqlite", "itsm-*.dump", "itsm-*.db")
                           for path in Path(settings.backup_directory).glob(pattern)), key=lambda path: path.stat().st_mtime, reverse=True)
    latest_backup = backup_files[0] if backup_files else None
    return {"application": "Operational", "database": "Connected" if db_ok else "Unavailable",
            "mailbox": (mail_state.value if mail_state else {"status": "Not configured"}),
            "worker": (worker_state.value if worker_state else {"status": "Not running"}),
            "migration_version": migration, "version": __version__, "uptime_seconds": int((now()-started_at).total_seconds()),
            "open_automation_failures": db.scalar(select(func.count(AutomationFailure.id)).where(AutomationFailure.status == "Open")) or 0,
            "notification_failures": db.scalar(select(func.count(Notification.id)).where(Notification.delivery_status == "failed")) or 0,
            "notification_email_pending": db.scalar(select(func.count(Notification.id)).where(Notification.delivery_status == "pending_email")) or 0,
            "smtp": {"status": "Configured" if os.getenv("ITSM_SMTP_HOST") else "Not configured"},
            "storage": {"database_bytes": Path("data/itsm.db").stat().st_size if Path("data/itsm.db").exists() else 0},
            "backup": {"status": "Available" if latest_backup else "Not configured",
                       "latest": latest_backup.name if latest_backup else None}}


@app.post("/api/feedback", status_code=201)
def feedback(payload: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = Feedback(user_id=user.id, feedback_type=payload.feedback_type, current_page=payload.current_page,
                    user_role=user.role.value, app_version=__version__, related_record_id=payload.related_record_id, text=payload.text)
    db.add(item); audit(db, "feedback.created", "feedback", None, user.id, new={"type": payload.feedback_type}); db.commit(); return {"ok": True}


def form_dict(form: FormDefinition):
    return {"id": form.id, "slug": form.slug, "name": form.name, "description": form.description,
            "category": form.category, "icon": form.icon, "fields": form.fields or [], "active": form.active,
            "is_template": form.is_template, "published": form.published,
            "form_type": form.form_type, "portal_visible": form.portal_visible,
            "default_for_type": form.default_for_type, "requester_layout": form.requester_layout or [],
            "technician_layout": form.technician_layout or [], "lifecycle_state": form.lifecycle_state,
            "version": form.version, "archived_at": form.archived_at,
            "created_at": form.created_at, "updated_at": form.updated_at}


def form_snapshot(form: FormDefinition) -> dict:
    snapshot = {key: value for key, value in form_dict(form).items() if key not in {"created_at", "updated_at"}}
    if isinstance(snapshot.get("archived_at"), datetime):
        snapshot["archived_at"] = snapshot["archived_at"].isoformat()
    return snapshot


def validate_form_layouts(fields: list[dict], requester_layout: list, technician_layout: list) -> tuple[list, list]:
    field_ids = [str(field.get("id")) for field in fields]
    valid_ids = set(field_ids)
    def clean(layout: list, label: str) -> list:
        if not layout:
            return list(field_ids)
        normalized = [str(item) for item in layout]
        if len(normalized) != len(set(normalized)) or any(item not in valid_ids for item in normalized):
            raise HTTPException(422, f"{label} layout contains duplicate or unknown fields")
        return normalized + [item for item in field_ids if item not in normalized]
    return clean(requester_layout, "Requester"), clean(technician_layout, "Technician")


@app.get("/api/forms")
def published_forms(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(FormDefinition).where(FormDefinition.active.is_(True), FormDefinition.published.is_(True),
                                                       FormDefinition.portal_visible.is_(True), FormDefinition.archived_at.is_(None))
                      .order_by(FormDefinition.name)).all()
    return [form_dict(row) for row in rows]


@app.get("/api/admin/forms")
def admin_forms(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [form_dict(row) for row in db.scalars(select(FormDefinition).order_by(FormDefinition.name)).all()]


@app.post("/api/admin/forms", status_code=201)
def create_form(payload: FormDefinitionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if payload.is_template and payload.published: raise HTTPException(422, "A reusable template cannot be published")
    try: fields = validate_form_fields(payload.fields)
    except ValueError as exc: raise HTTPException(422, str(exc))
    requester_layout, technician_layout = validate_form_layouts(fields, payload.requester_layout, payload.technician_layout)
    values = payload.model_dump(exclude={"fields", "version", "requester_layout", "technician_layout"})
    values.update(requester_layout=requester_layout, technician_layout=technician_layout)
    values["lifecycle_state"] = "published" if payload.published else "draft"
    if payload.published and any(field.get("type") == "section" and field.get("label", "").strip().lower().startswith("untitled") for field in fields):
        raise HTTPException(422, "Name every section before publishing")
    if payload.default_for_type:
        db.execute(update(FormDefinition).where(FormDefinition.form_type == payload.form_type).values(default_for_type=False))
    form = FormDefinition(**values, fields=fields)
    db.add(form)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "A form with this key already exists")
    audit(db, "form.created", "form_definition", form.id, user.id, new={"name": form.name, "published": form.published})
    db.flush(); db.add(FormDefinitionVersion(form_definition_id=form.id, version=1, snapshot=form_snapshot(form), created_by_id=user.id))
    db.commit(); db.refresh(form); return form_dict(form)


@app.patch("/api/admin/forms/{form_id}")
def update_form(form_id: int, payload: FormDefinitionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, form_id)
    if not form: raise HTTPException(404, "Form not found")
    if payload.is_template and payload.published: raise HTTPException(422, "A reusable template cannot be published")
    try: fields = validate_form_fields(payload.fields)
    except ValueError as exc: raise HTTPException(422, str(exc))
    if payload.published and any(field.get("type") == "section" and field.get("label", "").strip().lower().startswith("untitled") for field in fields):
        raise HTTPException(422, "Name every section before publishing")
    previous = form_snapshot(form)
    if payload.version is not None and payload.version != form.version:
        raise HTTPException(409, "This form changed after you opened it. Reload before saving.")
    requester_layout, technician_layout = validate_form_layouts(fields, payload.requester_layout, payload.technician_layout)
    values = payload.model_dump(exclude={"fields", "version", "requester_layout", "technician_layout"})
    values.update(requester_layout=requester_layout, technician_layout=technician_layout)
    values["lifecycle_state"] = "published" if payload.published else "draft"
    if payload.default_for_type:
        db.execute(update(FormDefinition).where(FormDefinition.form_type == payload.form_type,
                                                FormDefinition.id != form.id).values(default_for_type=False))
    for key, value in values.items(): setattr(form, key, value)
    form.fields = fields
    form.version += 1
    db.add(FormDefinitionVersion(form_definition_id=form.id, version=form.version, snapshot=form_snapshot(form), created_by_id=user.id))
    audit(db, "form.updated", "form_definition", form.id, user.id, previous=previous,
          new={"name": form.name, "published": form.published, "field_count": len(fields)})
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "A form with this key already exists")
    return form_dict(form)


@app.post("/api/admin/forms/{form_id}/copy", status_code=201)
def copy_form(form_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    source = db.get(FormDefinition, form_id)
    if not source or source.archived_at:
        raise HTTPException(404, "Form not found")
    suffix = uuid.uuid4().hex[:6]
    copied = FormDefinition(slug=f"{source.slug[:90]}-{suffix}", name=f"{source.name} Copy", description=source.description,
                            category=source.category, icon=source.icon, fields=source.fields, active=True, is_template=source.is_template,
                            published=False, form_type=source.form_type, portal_visible=False, default_for_type=False,
                            requester_layout=source.requester_layout, technician_layout=source.technician_layout,
                            lifecycle_state="draft", version=1)
    db.add(copied); db.flush()
    db.add(FormDefinitionVersion(form_definition_id=copied.id, version=1, snapshot=form_snapshot(copied), created_by_id=user.id))
    audit(db, "form.copied", "form_definition", copied.id, user.id, new={"source_id": source.id})
    db.commit(); return form_dict(copied)


@app.delete("/api/admin/forms/{form_id}")
def archive_form(form_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, form_id)
    if not form:
        raise HTTPException(404, "Form not found")
    if form.default_for_type:
        raise HTTPException(409, "Choose another default form before archiving this template")
    form.active = False; form.published = False; form.portal_visible = False; form.lifecycle_state = "archived"; form.archived_at = now(); form.version += 1
    audit(db, "form.archived", "form_definition", form.id, user.id, new={"version": form.version})
    db.commit(); return {"ok": True, "archived": True}


@app.post("/api/admin/forms/{form_id}/unarchive")
def unarchive_form(form_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, form_id)
    if not form:
        raise HTTPException(404, "Form not found")
    form.archived_at = None; form.active = True; form.published = False; form.portal_visible = False
    form.lifecycle_state = "draft"; form.version += 1
    db.add(FormDefinitionVersion(form_definition_id=form.id, version=form.version,
                                 snapshot=form_snapshot(form), created_by_id=user.id))
    audit(db, "form.unarchived", "form_definition", form.id, user.id, new={"version": form.version})
    db.commit(); return form_dict(form)


@app.get("/api/admin/forms/{form_id}/versions")
def form_versions(form_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if not db.get(FormDefinition, form_id):
        raise HTTPException(404, "Form not found")
    rows = db.scalars(select(FormDefinitionVersion).where(FormDefinitionVersion.form_definition_id == form_id)
                      .order_by(FormDefinitionVersion.version.desc())).all()
    return [{"id": row.id, "version": row.version, "created_by_id": row.created_by_id, "created_at": row.created_at,
             "snapshot": row.snapshot} for row in rows]


@app.post("/api/admin/forms/{form_id}/versions/{version_id}/restore")
def restore_form_version(form_id: int, version_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, form_id); stored = db.get(FormDefinitionVersion, version_id)
    if not form or not stored or stored.form_definition_id != form.id:
        raise HTTPException(404, "Form version not found")
    snapshot = stored.snapshot or {}
    for key in ["name", "description", "category", "icon", "fields", "active", "is_template", "published", "form_type",
                "portal_visible", "default_for_type", "requester_layout", "technician_layout", "lifecycle_state"]:
        if key in snapshot:
            setattr(form, key, snapshot[key])
    form.version += 1
    db.add(FormDefinitionVersion(form_definition_id=form.id, version=form.version, snapshot=form_snapshot(form), created_by_id=user.id))
    audit(db, "form.version_restored", "form_definition", form.id, user.id, new={"restored_version": stored.version, "version": form.version})
    db.commit(); return form_dict(form)


def approval_dict(item: ApprovalRequest, db: Session):
    ticket = db.get(Ticket, item.ticket_id); workflow = db.get(ApprovalWorkflow, item.workflow_id)
    approver = db.get(User, item.current_approver_id) if item.current_approver_id else None
    requester = db.get(User, item.requested_by_id)
    decisions = db.scalars(select(ApprovalDecision).where(ApprovalDecision.approval_request_id == item.id)
                           .order_by(ApprovalDecision.created_at)).all()
    return {"id": item.id, "status": item.status, "current_step": item.current_step,
            "step_name": workflow.steps[item.current_step].get("name", f"Step {item.current_step + 1}") if workflow and item.current_step < len(workflow.steps) else "Complete",
            "workflow": workflow.name if workflow else "Approval", "ticket_id": ticket.id if ticket else None,
            "ticket_number": ticket.number if ticket else None, "subject": ticket.subject if ticket else None,
            "requester": requester.display_name if requester else None,
            "approver": approver.display_name if approver else "Unassigned approver",
            "created_at": item.created_at, "updated_at": item.updated_at,
            "decisions": [{"step_index": d.step_index, "decision": d.decision, "comment": d.comment,
                           "approver": db.get(User, d.approver_id).display_name, "created_at": d.created_at} for d in decisions]}


@app.post("/api/forms/{form_id}/submit", status_code=201)
def submit_form(form_id: int, payload: FormSubmissionIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, form_id)
    if not form or not form.active or not form.published: raise HTTPException(404, "Form not found")
    try: values = validate_form_submission(form, payload.values)
    except ValueError as exc: raise HTTPException(422, str(exc))
    requester = user
    if payload.requester_id and payload.requester_id != user.id:
        if user.role not in STAFF_ROLES: raise HTTPException(403, "Only IT staff can submit for another user")
        requester = db.get(User, payload.requester_id)
        if not requester or not requester.active: raise HTTPException(422, "Requester is not active")
    employee = db.scalar(select(Employee).where(Employee.user_id == requester.id))
    priority = priority_for(payload.impact, payload.urgency); first_due, resolution_due = sla_dates(priority)
    description_lines = []
    for field in form.fields:
        if field.get("type") != "section" and field.get("key") in values:
            value = values[field["key"]]
            description_lines.append(f"{field['label']}: {', '.join(map(str, value)) if isinstance(value, list) else value}")
    selected_assets = ticket_assets_for_email(db, requester.email, payload.asset_ids)
    if selected_assets:
        description_lines.append("")
        description_lines.append("Asset information")
        for asset in selected_assets:
            assigned = f"{asset.assigned_employee.first_name} {asset.assigned_employee.last_name}" if asset.assigned_employee else "Unassigned"
            description_lines.extend([
                f"Asset tag: {asset.asset_tag}", f"Hostname: {asset.hostname or 'Not recorded'}",
                f"Device type: {asset.asset_type}", f"Manufacturer / model: {asset.manufacturer} {asset.model}",
                f"Serial number: {asset.serial_number or 'Not recorded'}", f"Assigned to: {assigned}",
                f"Location: {asset.location.name if asset.location else 'Not recorded'}", f"Status: {asset.status}",
            ])
    description = "\n".join(description_lines) or payload.subject
    requester_email = (requester.email or "").strip().lower()
    requester_domain = requester_email.rsplit("@", 1)[1] if "@" in requester_email else ""
    routing_sample = {
        "request_type": form.name, "status": "New", "mode": "Portal", "level": "User",
        "impact": payload.impact, "urgency": payload.urgency, "priority": priority,
        "category": form.category, "subcategory": "", "item": "", "location_name": "",
        "requester": requester_email, "requester_email": requester_email,
        "requester_domain": requester_domain, "requester_department": "",
        "organization": str(requester.organization_id), "channel": "portal",
        "keywords": f"{payload.subject}\n{description}".strip(),
    }
    try:
        team, tech, reason, route_trace = route_incident(db, routing_sample, requester)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    ticket = Ticket(number=next_ticket_number(db, form.name), request_type=form.name, subject=payload.subject,
                    description=description, requester_id=requester.id, opened_by_id=user.id,
                    employee_id=employee.id if employee else None, team_id=team.id,
                    assigned_user_id=tech.id if tech else None, status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW,
                    priority=priority, impact=payload.impact, urgency=payload.urgency, category=form.category,
                    route_reason=reason, routing_trace=route_trace,
                    first_response_due=first_due, resolution_due=resolution_due,
                    form_definition_id=form.id, custom_data=values,
                    requester_snapshot=requester_snapshot(db, requester, user, selected_assets))
    if selected_assets:
        ticket.assets = selected_assets
    db.add(ticket); db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id, body=ticket.description, kind="public"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="created_from_form", actor_id=user.id,
                         new_value={"form": form.name, "status": ticket.status.value}))
    workflow = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.form_definition_id == form.id,
                                                        ApprovalWorkflow.active.is_(True)))
    if workflow:
        for template in db.scalars(select(TaskTemplate).where(TaskTemplate.id.in_(workflow.task_template_ids or []),TaskTemplate.active.is_(True))).all():
            items=[{**row,"id":str(row.get("id") or uuid.uuid4()),"completed":False,"completed_by_id":None,"completed_at":None,"note":""} for row in (template.items or [])]
            db.add(TicketChecklist(ticket_id=ticket.id,task_template_id=template.id,name=template.name,items=items,status="Blocked",required_for_closure=bool((workflow.closure_requirements or {}).get("require_checklists",True))))
        approver = workflow_approver(db, workflow, 0)
        ticket.status = TicketStatus.WAITING_APPROVAL; ticket.next_action_owner = "Approver"
        ticket.next_action = workflow.steps[0].get("name", "Review request")
        approval = ApprovalRequest(ticket_id=ticket.id, workflow_id=workflow.id, requested_by_id=requester.id,
                                   current_approver_id=approver.id if approver else None)
        db.add(approval); db.flush()
        notify(db, approver.id if approver else None, "approval.requested", f"Approval needed: {ticket.number}",
               f"{requester.display_name} submitted {form.name}: {ticket.subject}", ticket.id, email=True)
        if not approver:
            fail_automation(db, "approval_routing", "Approval step has no eligible approver",
                            {"ticket_number": ticket.number, "workflow": workflow.name}, "approval", approval.id)
    notify(db, requester.id, "ticket.created", f"{ticket.number} created", "Your form was submitted successfully.", ticket.id, email=True)
    if tech and not workflow:
        notify(db,tech.id,"ticket.assigned",f"[{ticket.number}] Assigned: {ticket.subject}",
               f"Submitted by {requester.display_name} using {form.name}.",ticket.id,email=True)
    audit(db, "form.submitted", "ticket", ticket.id, user.id, new={"form_id": form.id, "approval": bool(workflow)},
          source_ip=request.client.host if request.client else None)
    db.commit(); db.refresh(ticket)
    return {"ticket": ticket_dict(ticket, True,user,db), "approval_required": bool(workflow)}


@app.get("/api/admin/approval-workflows")
def approval_workflows(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApprovalWorkflow).order_by(ApprovalWorkflow.name)).all()
    return [{"id": row.id, "name": row.name, "form_definition_id": row.form_definition_id,
             "steps": row.steps, "task_template_ids":row.task_template_ids or [],"closure_requirements":row.closure_requirements or {},"active": row.active} for row in rows]


def clean_task_items(items:list[dict]):
    clean=[];seen=set()
    for index,row in enumerate(items):
        item_id=str(row.get("id") or uuid.uuid4());label=str(row.get("label") or row.get("name") or "").strip()
        if not label: raise HTTPException(422,f"Task item {index+1} needs a label")
        if item_id in seen: raise HTTPException(422,"Task item IDs must be unique")
        seen.add(item_id);clean.append({"id":item_id,"label":label[:240],"description":str(row.get("description", ""))[:1000],"required":bool(row.get("required",True))})
    return clean


@app.get("/api/admin/task-templates")
def task_templates(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    return [{"id":item.id,"name":item.name,"description":item.description,"items":item.items or [],"active":item.active,"version":item.version} for item in db.scalars(select(TaskTemplate).order_by(TaskTemplate.name)).all()]


@app.post("/api/admin/task-templates",status_code=201)
def create_task_template(payload:TaskTemplateIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=TaskTemplate(name=payload.name,description=payload.description,items=clean_task_items(payload.items),active=payload.active);db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback();raise HTTPException(409,"A task template with this name already exists")
    audit(db,"task_template.created","task_template",item.id,user.id,new={"name":item.name,"items":len(item.items)});db.commit();return {"id":item.id,"name":item.name,"description":item.description,"items":item.items,"active":item.active,"version":item.version}


@app.patch("/api/admin/task-templates/{item_id}")
def update_task_template(item_id:int,payload:TaskTemplateIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(TaskTemplate,item_id)
    if not item: raise HTTPException(404,"Task template not found")
    if payload.version is not None and payload.version!=item.version: raise HTTPException(409,"This task template changed after you opened it")
    item.name=payload.name;item.description=payload.description;item.items=clean_task_items(payload.items);item.active=payload.active;item.version+=1
    audit(db,"task_template.updated","task_template",item.id,user.id,new={"name":item.name,"version":item.version});db.commit();return {"id":item.id,"name":item.name,"description":item.description,"items":item.items,"active":item.active,"version":item.version}


@app.delete("/api/admin/task-templates/{item_id}")
def archive_task_template(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(TaskTemplate,item_id)
    if not item: raise HTTPException(404,"Task template not found")
    workflows=[workflow.name for workflow in db.scalars(select(ApprovalWorkflow).where(ApprovalWorkflow.active.is_(True))).all() if item.id in (workflow.task_template_ids or [])]
    if workflows: raise HTTPException(409,"Remove this task template from active workflows before archiving: "+", ".join(workflows))
    item.active=False;item.archived_at=now();item.version+=1;audit(db,"task_template.archived","task_template",item.id,user.id);db.commit();return {"ok":True,"archived":True}


@app.patch("/api/tickets/{ticket_id}/checklists/{checklist_id}")
def update_checklist_item(ticket_id:int,checklist_id:int,payload:ChecklistItemUpdate,user:User=Depends(require_roles(*STAFF_ROLES)),db:Session=Depends(get_db)):
    ticket=db.get(Ticket,ticket_id);checklist=db.get(TicketChecklist,checklist_id)
    if not ticket or not checklist or checklist.ticket_id!=ticket.id or not can_view_ticket(user,ticket): raise HTTPException(404,"Checklist not found")
    items=[dict(row) for row in (checklist.items or [])];target=next((row for row in items if str(row.get("id"))==payload.item_id),None)
    if not target: raise HTTPException(404,"Checklist item not found")
    target.update(completed=payload.completed,note=payload.note,completed_by_id=user.id if payload.completed else None,completed_at=now().isoformat() if payload.completed else None)
    checklist.items=items;required=[row for row in items if row.get("required",True)];checklist.status="Completed" if required and all(row.get("completed") for row in required) else "Active";checklist.completed_at=now() if checklist.status=="Completed" else None
    audit(db,"ticket.checklist_updated","ticket",ticket.id,user.id,new={"checklist_id":checklist.id,"item_id":payload.item_id,"completed":payload.completed});db.commit();return {"id":checklist.id,"status":checklist.status,"items":checklist.items,"completed_at":checklist.completed_at}


@app.post("/api/admin/approval-workflows", status_code=201)
def create_approval_workflow(payload: ApprovalWorkflowIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    form = db.get(FormDefinition, payload.form_definition_id)
    if not form: raise HTTPException(422, "Form not found")
    if db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.form_definition_id == form.id)):
        raise HTTPException(409, "This form already has an approval workflow")
    steps = []
    for index, raw in enumerate(payload.steps):
        name = str(raw.get("name", "")).strip()
        role = str(raw.get("approver_role", "manager"))
        user_id = raw.get("approver_user_id")
        if not name: raise HTTPException(422, f"Approval step {index + 1} needs a name")
        if user_id and not db.get(User, int(user_id)): raise HTTPException(422, f"Approver for step {index + 1} was not found")
        if not user_id:
            try: Role(role)
            except ValueError: raise HTTPException(422, f"Approval role for step {index + 1} is invalid")
        steps.append({"name": name[:160], "approver_role": role, "approver_user_id": int(user_id) if user_id else None})
    templates=db.scalars(select(TaskTemplate).where(TaskTemplate.id.in_(payload.task_template_ids),TaskTemplate.active.is_(True))).all() if payload.task_template_ids else []
    if len(templates)!=len(set(payload.task_template_ids)): raise HTTPException(422,"One or more task templates are missing or inactive")
    workflow = ApprovalWorkflow(name=payload.name, form_definition_id=form.id, steps=steps,task_template_ids=payload.task_template_ids,closure_requirements=payload.closure_requirements, active=payload.active)
    db.add(workflow); db.flush(); audit(db, "approval_workflow.created", "approval_workflow", workflow.id, user.id,
                                       new={"form": form.name, "steps": len(steps)})
    db.commit(); return {"id": workflow.id, "name": workflow.name, "form_definition_id": workflow.form_definition_id,
                         "steps": workflow.steps,"task_template_ids":workflow.task_template_ids,"closure_requirements":workflow.closure_requirements, "active": workflow.active}


@app.patch("/api/admin/approval-workflows/{workflow_id}")
def update_approval_workflow(workflow_id: int, payload: ApprovalWorkflowIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    workflow = db.get(ApprovalWorkflow, workflow_id)
    if not workflow: raise HTTPException(404, "Workflow not found")
    if payload.form_definition_id != workflow.form_definition_id: raise HTTPException(422, "Workflow form cannot be changed")
    steps = []
    for index, raw in enumerate(payload.steps):
        name = str(raw.get("name", "")).strip(); role = str(raw.get("approver_role", "manager")); user_id = raw.get("approver_user_id")
        if not name: raise HTTPException(422, f"Approval step {index + 1} needs a name")
        if user_id and not db.get(User, int(user_id)): raise HTTPException(422, f"Approver for step {index + 1} was not found")
        if not user_id:
            try: Role(role)
            except ValueError: raise HTTPException(422, f"Approval role for step {index + 1} is invalid")
        steps.append({"name": name[:160], "approver_role": role, "approver_user_id": int(user_id) if user_id else None})
    previous = {"name": workflow.name, "steps": workflow.steps, "active": workflow.active}
    templates=db.scalars(select(TaskTemplate).where(TaskTemplate.id.in_(payload.task_template_ids),TaskTemplate.active.is_(True))).all() if payload.task_template_ids else []
    if len(templates)!=len(set(payload.task_template_ids)): raise HTTPException(422,"One or more task templates are missing or inactive")
    workflow.name = payload.name; workflow.steps = steps;workflow.task_template_ids=payload.task_template_ids;workflow.closure_requirements=payload.closure_requirements; workflow.active = payload.active
    audit(db, "approval_workflow.updated", "approval_workflow", workflow.id, user.id, previous, {"name": workflow.name, "steps": steps, "active": workflow.active})
    db.commit(); return {"ok": True}


@app.get("/api/approvals")
def approval_queue(status: str = "Pending", user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)), db: Session = Depends(get_db)):
    stmt = select(ApprovalRequest)
    if status != "all": stmt = stmt.where(ApprovalRequest.status == status)
    if user.role not in (Role.ADMIN, Role.MANAGER, Role.AUDITOR): stmt = stmt.where(ApprovalRequest.current_approver_id == user.id)
    return [approval_dict(item, db) for item in db.scalars(stmt.order_by(ApprovalRequest.updated_at.desc())).all()]


@app.post("/api/approvals/{approval_id}/decision")
def decide_approval(approval_id: int, payload: ApprovalDecisionIn, user: User = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)):
    item = db.get(ApprovalRequest, approval_id)
    if not item or item.status != "Pending": raise HTTPException(404, "Pending approval not found")
    if item.current_approver_id != user.id and user.role != Role.ADMIN: raise HTTPException(403, "This approval is assigned to another approver")
    workflow = db.get(ApprovalWorkflow, item.workflow_id); ticket = db.get(Ticket, item.ticket_id)
    db.add(ApprovalDecision(approval_request_id=item.id, step_index=item.current_step,
                            approver_id=user.id, decision=payload.decision, comment=payload.comment))
    if payload.decision == "Rejected":
        item.status = "Rejected"; item.completed_at = now(); ticket.status = TicketStatus.CANCELLED
        ticket.next_action_owner = "Requester"; ticket.next_action = "Review rejection decision"
        notify(db, item.requested_by_id, "approval.rejected", f"{ticket.number} was rejected",
               payload.comment or "The request was not approved.", ticket.id, email=True)
        for checklist in db.scalars(select(TicketChecklist).where(TicketChecklist.ticket_id==ticket.id)).all(): checklist.status="Cancelled"
    elif item.current_step + 1 < len(workflow.steps):
        item.current_step += 1; next_approver = workflow_approver(db, workflow, item.current_step)
        item.current_approver_id = next_approver.id if next_approver else None
        ticket.next_action = workflow.steps[item.current_step].get("name", "Review request")
        notify(db, next_approver.id if next_approver else None, "approval.requested", f"Approval needed: {ticket.number}",
               f"{user.display_name} approved the previous step. {ticket.subject}", ticket.id, email=True)
        if not next_approver: fail_automation(db, "approval_routing", "Approval step has no eligible approver",
                                              {"ticket_number": ticket.number, "step": item.current_step + 1}, "approval", item.id)
    else:
        item.status = "Approved"; item.completed_at = now(); item.current_approver_id = None
        ticket.status = TicketStatus.ASSIGNED if ticket.assigned_user_id else TicketStatus.NEW
        ticket.next_action_owner = "IT"; ticket.next_action = "Begin approved work"
        notify(db, item.requested_by_id, "approval.approved", f"{ticket.number} was approved",
               payload.comment or "All approval steps are complete.", ticket.id, email=True)
        notify(db, ticket.assigned_user_id, "ticket.approved", f"Approved work: {ticket.number}", ticket.subject, ticket.id, email=True)
        for checklist in db.scalars(select(TicketChecklist).where(TicketChecklist.ticket_id==ticket.id,TicketChecklist.status=="Blocked")).all(): checklist.status="Active"
    db.add(TicketHistory(ticket_id=ticket.id, event_type=f"approval_{payload.decision.lower()}", actor_id=user.id,
                         new_value={"step": item.current_step, "comment": payload.comment}))
    audit(db, f"approval.{payload.decision.lower()}", "approval_request", item.id, user.id,
          new={"ticket_id": ticket.id, "step": item.current_step, "comment": payload.comment})
    db.commit(); return approval_dict(item, db)


REPORT_COLUMNS = {"number", "subject", "description", "requester", "requester_email", "requester_department",
                  "requester_location", "status", "priority", "impact", "urgency", "category", "subcategory",
                  "team", "assigned_user", "created_at", "updated_at", "resolved_at", "request_type"}


def validate_report_configuration(configuration: dict,db:Session|None=None) -> dict:
    columns = configuration.get("columns") or ["number", "subject", "status", "priority"]
    filters = configuration.get("filters") or []
    group_by = configuration.get("group_by") or ""
    reportable={field.get("key") for form in db.scalars(select(FormDefinition)).all() for field in (form.fields or []) if field.get("type")!="section" and field.get("reportable",True)} if db else set()
    def valid_field(value): return value in REPORT_COLUMNS or (isinstance(value, str) and value.startswith("custom.") and len(value) <= 80 and (db is None or value[7:] in reportable))
    if len(columns) > 30 or any(not valid_field(item) for item in columns): raise HTTPException(422, "Report contains an unsupported column")
    if len(filters) > 20 or any(not valid_field(item.get("field")) or item.get("operator") not in {"equals", "not_equals", "contains", "one_of", "before", "after"} for item in filters):
        raise HTTPException(422, "Report contains an unsupported filter")
    if group_by and not valid_field(group_by): raise HTTPException(422, "Report group is unsupported")
    return {"columns": columns, "filters": filters, "group_by": group_by}


def report_definition_dict(row: ReportDefinition):
    return {"id": row.id, "name": row.name, "description": row.description,
            "configuration": row.configuration, "active": row.active, "updated_at": row.updated_at}


@app.get("/api/reports/definitions")
def report_definitions(user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    return [report_definition_dict(row) for row in db.scalars(select(ReportDefinition).where(ReportDefinition.active.is_(True)).order_by(ReportDefinition.name)).all()]


@app.get("/api/admin/report-definitions")
def admin_report_definitions(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [report_definition_dict(row) for row in db.scalars(select(ReportDefinition).order_by(ReportDefinition.name)).all()]


@app.post("/api/admin/report-definitions", status_code=201)
def create_report_definition(payload: ReportDefinitionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    config = validate_report_configuration(payload.configuration,db)
    row = ReportDefinition(name=payload.name, description=payload.description, configuration=config,
                           created_by_id=user.id, active=payload.active)
    db.add(row)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "A report with this name already exists")
    audit(db, "report.created", "report_definition", row.id, user.id, new={"name": row.name})
    db.commit(); return report_definition_dict(row)


@app.patch("/api/admin/report-definitions/{report_id}")
def update_report_definition(report_id: int, payload: ReportDefinitionIn, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    row = db.get(ReportDefinition, report_id)
    if not row: raise HTTPException(404, "Report not found")
    previous = report_definition_dict(row); row.name = payload.name; row.description = payload.description
    row.configuration = validate_report_configuration(payload.configuration,db); row.active = payload.active
    audit(db, "report.updated", "report_definition", row.id, user.id, previous, {"name": row.name})
    try: db.commit()
    except IntegrityError: db.rollback(); raise HTTPException(409, "A report with this name already exists")
    return report_definition_dict(row)


def execute_report_definition(row: ReportDefinition, user: User, db: Session):
    config = validate_report_configuration(row.configuration,db)
    tickets = db.scalars(select(Ticket).where(visible_ticket_filter(user)).order_by(Ticket.created_at.desc()).limit(5000)).all()
    records = []; matched_records = []
    for ticket in tickets:
        record = ticket_dict(ticket)
        record["request_type"] = ticket.request_type; record["resolved_at"] = ticket.resolved_at
        for key, value in secure_custom_data(ticket,user,db).items(): record[f"custom.{key}"] = value
        matches = True
        for item in config["filters"]:
            actual = record.get(item["field"]); expected = item.get("value", ""); operator = item["operator"]
            if operator == "equals": matches = str(actual).lower() == str(expected).lower()
            elif operator == "not_equals": matches = str(actual).lower() != str(expected).lower()
            elif operator == "contains": matches = str(expected).lower() in str(actual).lower()
            elif operator == "before": matches = str(actual or "")[:10] < str(expected)[:10]
            elif operator == "after": matches = str(actual or "")[:10] > str(expected)[:10]
            else: matches = str(actual) in ([str(v) for v in expected] if isinstance(expected, list) else [v.strip() for v in str(expected).split(",")])
            if not matches: break
        if matches:
            matched_records.append(record)
            records.append({column: record.get(column) for column in config["columns"]})
    groups = []
    if config["group_by"]:
        counts = {}
        for record in matched_records:
            value = str(record.get(config["group_by"]) or "Not set"); counts[value] = counts.get(value, 0) + 1
        groups = [{"label": key, "count": value} for key,value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    return {"report": report_definition_dict(row), "columns": config["columns"], "rows": records[:1000], "matching": len(records), "groups": groups}


@app.get("/api/reports/{report_id}/run")
def run_custom_report(report_id: int, user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    row = db.get(ReportDefinition, report_id)
    if not row or not row.active: raise HTTPException(404, "Report not found")
    audit(db, "report.executed", "report_definition", row.id, user.id); db.commit()
    return execute_report_definition(row, user, db)


@app.get("/api/reports/{report_id}/csv")
def custom_report_csv(report_id: int, user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    row = db.get(ReportDefinition, report_id)
    if not row or not row.active: raise HTTPException(404, "Report not found")
    result = execute_report_definition(row, user, db); output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(result["columns"])
    for item in result["rows"]: writer.writerow([item.get(column, "") for column in result["columns"]])
    filename = re.sub(r"[^a-z0-9]+", "-", row.name.lower()).strip("-") or "custom-report"
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}.csv"})


@app.post("/api/email/ingest")
def email_ingest(payload: EmailIngest, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if db.scalar(select(EmailMessage).where(EmailMessage.message_id == payload.message_id)):
        return {"status": "duplicate", "ticket_id": None}
    if is_automated_email(payload.headers, payload.subject):
        db.add(EmailMessage(message_id=payload.message_id, in_reply_to=payload.in_reply_to, sender=str(payload.sender),
                            subject=payload.subject, processing_status="ignored_automatic", attachment_metadata=payload.attachments)); db.commit()
        return {"status": "ignored_automatic", "ticket_id": None}
    requester = db.scalar(select(User).where(func.lower(User.email) == str(payload.sender).lower()))
    if not requester:
        failure = fail_automation(db, "email_requester", "Requester could not be identified", {"sender": str(payload.sender), "message_id": payload.message_id})
        db.add(EmailMessage(message_id=payload.message_id, in_reply_to=payload.in_reply_to, sender=str(payload.sender), subject=payload.subject,
                            processing_status="failed", attachment_metadata=payload.attachments)); db.commit()
        return {"status": "failed", "failure_id": failure.id}
    prior_ids = [payload.in_reply_to, *payload.references]
    prior = db.scalar(select(EmailMessage).where(EmailMessage.message_id.in_([x for x in prior_ids if x])).order_by(EmailMessage.id.desc())) if any(prior_ids) else None
    ticket = ticket_from_email_subject(db, payload.subject)
    if not ticket and prior and prior.ticket_id:
        ticket = db.get(Ticket, prior.ticket_id)
    if ticket:
        db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=payload.text_body, kind="public", source="email"))
        closed = close_ticket_from_requester_message(db, ticket, requester, payload.text_body, "email")
        if not closed:
            notify(db, ticket.assigned_user_id, "user.replied", f"Email reply on {ticket.number}", payload.text_body[:200], ticket.id,email=True)
        status = "threaded"
    else:
        sample = inbound_email_routing_sample(db, requester, str(payload.sender), payload.subject, payload.text_body)
        team, tech, reason, trace = route_incident(db, sample, requester); priority = "Medium"; first, due = sla_dates(priority)
        employee = db.scalar(select(Employee).where(func.lower(Employee.work_email) == requester.email.lower()))
        ticket = Ticket(number=next_ticket_number(db, "Report an issue"), request_type="Report an issue", subject=payload.subject[:240],
                        description=payload.text_body, requester_id=requester.id, opened_by_id=requester.id,
                        employee_id=employee.id if employee else None,
                        team_id=team.id, assigned_user_id=tech.id if tech else None,
                        status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW, priority=priority, impact="Medium", urgency="Medium",
                        category="General", route_reason=reason, first_response_due=first, resolution_due=due)
        ticket.routing_trace = trace
        ticket.assets = ticket_assets_for_email(db, requester.email)
        ticket.requester_snapshot = requester_snapshot(db, requester, requester, ticket.assets)
        db.add(ticket); db.flush(); db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=payload.text_body, kind="public", source="email"))
        notify(db, requester.id, "ticket.created", f"{ticket.number} created from email", "Your email was received.", ticket.id,email=True)
        notify(db, tech.id if tech else None, "ticket.assigned", f"[{ticket.number}] Assigned: {ticket.subject}", f"Created by email from {requester.display_name}.", ticket.id,email=True); status = "created"
    db.add(EmailMessage(message_id=payload.message_id, in_reply_to=payload.in_reply_to, sender=str(payload.sender), subject=payload.subject,
                        ticket_id=ticket.id, processing_status=status, attachment_metadata=payload.attachments))
    audit(db, f"email.{status}", "ticket", ticket.id, requester.id, new={"message_id": payload.message_id, "attachments": len(payload.attachments)})
    db.commit(); return {"status": status, "ticket_id": ticket.id, "ticket_number": ticket.number, "attachments_recorded": len(payload.attachments)}


@app.get("/api/reports/tickets.csv")
def report_csv(start_date: str | None = Query(None), end_date: str | None = Query(None), status: str | None = Query(None),
               user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    """Complete ticket export; created-date and status filters are inclusive/server-side."""
    def boundary(value, label):
        if not value: return None
        try: return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError: raise HTTPException(422, f"{label} must use YYYY-MM-DD")
    start, end = boundary(start_date, "start_date"), boundary(end_date, "end_date")
    if start and end and end < start: raise HTTPException(422, "end_date must be on or after start_date")
    stmt = select(Ticket).where(visible_ticket_filter(user))
    if start: stmt = stmt.where(Ticket.created_at >= start)
    if end: stmt = stmt.where(Ticket.created_at < end + timedelta(days=1))
    if status and status.lower() not in {"all", "*"}:
        values = {item.strip().lower() for item in status.split(",") if item.strip()}
        allowed = {item.value.lower() for item in TicketStatus}
        if not values or not values.issubset(allowed): raise HTTPException(422, "status contains an unsupported value")
        stmt = stmt.where(func.lower(Ticket.status).in_(values))
    tickets = db.scalars(stmt.order_by(Ticket.created_at.desc())).all()
    columns = ["id","number","request_type","subject","description","requester_id","requester","requester_email","opened_by_id","opened_by",
      "requester_department","requester_location","employee_id","assigned_user_id","assigned_user","team_id","team","status","priority","impact","urgency",
      "calculated_priority","priority_source","priority_override_reason","impact_details","mode","level","site_location","category","subcategory","restricted","item",
      "emails_to_notify","next_action_owner","next_action","waiting_reason","route_reason","sla_policy_key","first_response_due","resolution_due","first_responded_at",
      "resolved_at","resolution_summary","reopened_count","created_at","updated_at","form_definition_id","custom_data"]
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=columns); writer.writeheader()
    for ticket in tickets:
        row = ticket_dict(ticket, viewer=user, db=db); row["custom_data"] = secure_custom_data(ticket, user, db)
        row = {key: json.dumps(value, default=str, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()}
        writer.writerow({column: row.get(column, "") for column in columns})
    suffix = f"-{start_date or 'beginning'}-to-{end_date or 'today'}" if (start_date or end_date) else ""
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":f"attachment; filename=northstar-desk-tickets{suffix}.csv"})

static_dir = Path(settings.static_directory) if settings.static_directory else Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

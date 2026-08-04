import csv
import enum
import io
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import __version__
from .config import settings
from .database import Base, engine, get_db
from .models import *
from .schemas import *
from .security import *
from .services import *

app = FastAPI(title="Northstar Desk API", version=__version__, docs_url="/api/docs", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
started_at = now()


@app.middleware("http")
async def security_headers(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers.update({
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Referrer-Policy": "same-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' http://localhost:8000 http://127.0.0.1:8000",
        "X-Correlation-ID": correlation_id,
    })
    return response


def user_dict(user: User):
    return {"id": user.id, "username": user.username, "email": user.email, "display_name": user.display_name,
            "role": user.role.value, "active": user.active, "must_change_password": user.must_change_password,
            "availability": user.availability, "team_id": user.team_id, "team": user.team.name if user.team else None,
            "last_login_at": user.last_login_at}


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def ticket_dict(ticket: Ticket, detail=False):
    data = {"id": ticket.id, "number": ticket.number, "request_type": ticket.request_type, "subject": ticket.subject,
            "description": ticket.description, "requester_id": ticket.requester_id,
            "requester": ticket.requester.display_name, "requester_email": ticket.requester.email,
            "assigned_user_id": ticket.assigned_user_id,
            "assigned_user": ticket.assigned_user.display_name if ticket.assigned_user else None,
            "team_id": ticket.team_id, "team": ticket.team.name, "status": ticket.status.value,
            "priority": ticket.priority, "impact": ticket.impact, "urgency": ticket.urgency,
            "category": ticket.category, "subcategory": ticket.subcategory, "restricted": ticket.restricted,
            "next_action_owner": ticket.next_action_owner, "next_action": ticket.next_action,
            "waiting_reason": ticket.waiting_reason, "route_reason": ticket.route_reason,
            "first_response_due": ticket.first_response_due, "resolution_due": ticket.resolution_due,
            "first_responded_at": ticket.first_responded_at, "resolved_at": ticket.resolved_at,
            "resolution_summary": ticket.resolution_summary, "reopened_count": ticket.reopened_count,
            "created_at": ticket.created_at, "updated_at": ticket.updated_at,
            "sla_state": "breached" if aware(ticket.resolution_due) < now() and ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED)
                         else "warning" if aware(ticket.resolution_due) < now() + timedelta(hours=4) and ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED)
                         else "on_track"}
    if detail:
        data["assets"] = [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname, "model": a.model} for a in ticket.assets]
        data["messages"] = [{"id": m.id, "body": m.body, "kind": m.kind, "source": m.source,
                             "author": m.author.display_name if m.author else "Email requester", "created_at": m.created_at}
                            for m in sorted(ticket.messages, key=lambda x: x.created_at)]
    return data


@app.get("/api/health/live")
def live(): return {"status": "ok", "version": __version__}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = payload.username.strip().lower()
    user = db.scalar(select(User).where(or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier)))
    if not user:
        audit(db, "login.failed", "user", None, source_ip=request.client.host if request.client else None,
              new={"identifier": identifier, "reason": "unknown account"})
        db.commit(); time.sleep(.15)
        raise HTTPException(401, "Invalid username or password")
    locked = user.locked_until and user.locked_until.replace(tzinfo=user.locked_until.tzinfo or timezone.utc) > now()
    if locked or not user.active:
        audit(db, "login.failed", "user", user.id, source_ip=request.client.host if request.client else None,
              new={"reason": "account unavailable"}); db.commit()
        raise HTTPException(423, "Account is temporarily unavailable")
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
    return {"user": user_dict(user), "csrf_token": csrf}


@app.get("/api/auth/me")
def me(session: Session = Depends(get_current_session)):
    return {"user": user_dict(session.user), "csrf_token": session.csrf_token}


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


@app.get("/api/bootstrap")
def bootstrap(user: User = Depends(current_user), db: Session = Depends(get_db)):
    teams = db.scalars(select(Team).order_by(Team.name)).all()
    techs = db.scalars(select(User).where(User.role.in_([Role.TECHNICIAN, Role.TEAM_LEAD]), User.active.is_(True))).all()
    assets_query = select(Asset).order_by(Asset.asset_tag)
    if user.role == Role.END_USER:
        employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
        assets_query = assets_query.where(Asset.assigned_employee_id == (employee.id if employee else -1))
    return {"user": user_dict(user), "teams": [{"id": t.id, "name": t.name, "queue": t.queue_name} for t in teams],
            "technicians": [user_dict(t) for t in techs],
            "assets": [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname, "model": a.model} for a in db.scalars(assets_query).all()],
            "announcements": [{"id": a.id, "title": a.title, "body": a.body, "severity": a.severity} for a in db.scalars(select(Announcement).where(Announcement.active.is_(True))).all()]}


@app.get("/api/tickets")
def list_tickets(view: str = "all", q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Ticket).where(visible_ticket_filter(user))
    closed = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED]
    filters = {
        "open": Ticket.status.notin_(closed), "unassigned": Ticket.assigned_user_id.is_(None),
        "mine": Ticket.assigned_user_id == user.id, "team": Ticket.team_id == user.team_id,
        "new": Ticket.status == TicketStatus.NEW, "high": Ticket.priority.in_(["Critical", "High"]),
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


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketCreate, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    warnings = sensitive_warnings(payload.subject + " " + payload.description)
    priority = priority_for(payload.impact, payload.urgency)
    category = {"Request access": "Access", "Request software": "Software", "Request equipment": "Hardware",
                "New employee request": "Onboarding"}.get(payload.request_type, "General")
    team, tech, reason = route_ticket(db, category, user)
    first_due, resolution_due = sla_dates(priority)
    ticket = Ticket(number=next_ticket_number(db, payload.request_type), request_type=payload.request_type,
                    subject=payload.subject, description=payload.description, requester_id=user.id,
                    team_id=team.id, assigned_user_id=tech.id if tech else None,
                    status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW, priority=priority,
                    impact=payload.impact, urgency=payload.urgency, category=category, restricted=payload.restricted,
                    route_reason=reason, first_response_due=first_due, resolution_due=resolution_due)
    if payload.asset_ids:
        ticket.assets = db.scalars(select(Asset).where(Asset.id.in_(payload.asset_ids))).all()
    db.add(ticket); db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id, body=payload.description, kind="public"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="created", actor_id=user.id,
                         new_value={"status": ticket.status.value, "team": team.name, "assignee": tech.display_name if tech else None}))
    audit(db, "ticket.created", "ticket", ticket.id, user.id, new={"number": ticket.number, "route_reason": reason},
          source_ip=request.client.host if request.client else None)
    notify(db, user.id, "ticket.created", f"{ticket.number} created", "Your request was received.", ticket.id)
    notify(db, tech.id if tech else None, "ticket.assigned", f"{ticket.number} assigned", ticket.subject, ticket.id)
    if not tech: fail_automation(db, "assignment", "No available technician", {"ticket_number": ticket.number}, "ticket", ticket.id)
    db.commit(); db.refresh(ticket)
    return {"ticket": ticket_dict(ticket, True), "warnings": warnings}


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or not can_view_ticket(user, ticket): raise HTTPException(404, "Ticket not found")
    history = db.scalars(select(TicketHistory).where(TicketHistory.ticket_id == ticket.id).order_by(TicketHistory.created_at)).all()
    result = ticket_dict(ticket, True)
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
    for field, value in changes.items():
        old = getattr(ticket, field); previous[field] = old.value if isinstance(old, enum.Enum) else old
        setattr(ticket, field, value)
    if "status" in changes:
        if ticket.status == TicketStatus.RESOLVED:
            if not ticket.resolution_summary: raise HTTPException(422, "Resolution summary is required")
            ticket.resolved_at = now(); ticket.next_action_owner = "Requester"; ticket.next_action = "Confirm resolution"
            notify(db, ticket.requester_id, "ticket.resolved", f"{ticket.number} resolved", ticket.resolution_summary or "Resolved", ticket.id)
        elif ticket.status == TicketStatus.CLOSED: ticket.closed_at = now()
    if "assigned_user_id" in changes: notify(db, ticket.assigned_user_id, "ticket.assigned", f"{ticket.number} assigned", ticket.subject, ticket.id)
    db.add(TicketHistory(ticket_id=ticket.id, event_type="updated", actor_id=user.id, previous_value=previous,
                         new_value={k: v.value if isinstance(v, enum.Enum) else v for k, v in changes.items()},
                         reason=changes.get("priority_override_reason")))
    audit(db, "ticket.updated", "ticket", ticket.id, user.id, previous, {k: str(v) for k, v in changes.items()})
    db.commit(); db.refresh(ticket); return ticket_dict(ticket, True)


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
            notify(db, ticket.assigned_user_id, "user.replied", f"User replied to {ticket.number}", payload.body[:200], ticket.id)
            if ticket.status == TicketStatus.WAITING_USER: ticket.status = TicketStatus.IN_PROGRESS
        else:
            ticket.first_responded_at = ticket.first_responded_at or now()
            notify(db, ticket.requester_id, "technician.replied", f"Update on {ticket.number}", payload.body[:200], ticket.id)
    db.add(TicketHistory(ticket_id=ticket.id, event_type=f"{payload.kind}_message", actor_id=user.id))
    audit(db, f"ticket.{payload.kind}_message", "ticket", ticket.id, user.id)
    db.commit(); return {"ok": True, "warnings": sensitive_warnings(payload.body)}


@app.post("/api/tickets/{ticket_id}/confirm")
def confirm_resolution(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.requester_id != user.id or ticket.status != TicketStatus.RESOLVED: raise HTTPException(400, "Ticket is not eligible")
    ticket.status = TicketStatus.CLOSED; ticket.closed_at = now()
    audit(db, "ticket.closed_by_requester", "ticket", ticket.id, user.id); db.commit(); return {"ok": True}


@app.post("/api/tickets/{ticket_id}/reopen")
def reopen(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    resolved_at = ticket.resolved_at.replace(tzinfo=ticket.resolved_at.tzinfo or timezone.utc) if ticket and ticket.resolved_at else None
    if not ticket or not can_view_ticket(user, ticket) or ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED) or not resolved_at or resolved_at < now() - timedelta(days=settings.reopen_days):
        raise HTTPException(400, "Ticket is not eligible to reopen")
    ticket.status = TicketStatus.IN_PROGRESS; ticket.closed_at = None; ticket.reopened_count += 1
    audit(db, "ticket.reopened", "ticket", ticket.id, user.id); notify(db, ticket.assigned_user_id, "ticket.reopened", f"{ticket.number} reopened", ticket.subject, ticket.id)
    db.commit(); return {"ok": True}


@app.post("/api/tickets/bulk")
def bulk_update(payload: BulkUpdate, user: User = Depends(require_roles(*STAFF_ROLES)), db: Session = Depends(get_db)):
    changed = 0
    for ticket in db.scalars(select(Ticket).where(Ticket.id.in_(payload.ticket_ids))).all():
        if not can_view_ticket(user, ticket): continue
        if payload.status: ticket.status = TicketStatus(payload.status)
        if payload.assigned_user_id is not None: ticket.assigned_user_id = payload.assigned_user_id
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


@app.get("/api/assets")
def assets(q: str = "", user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Asset)
    if user.role == Role.END_USER:
        emp = db.scalar(select(Employee).where(Employee.user_id == user.id)); stmt = stmt.where(Asset.assigned_employee_id == (emp.id if emp else -1))
    if q: stmt = stmt.where(or_(Asset.asset_tag.ilike(f"%{q}%"), Asset.hostname.ilike(f"%{q}%"), Asset.serial_number.ilike(f"%{q}%")))
    return [{"id": a.id, "asset_tag": a.asset_tag, "hostname": a.hostname, "serial_number": a.serial_number,
             "manufacturer": a.manufacturer, "model": a.model, "asset_type": a.asset_type, "status": a.status,
             "condition": a.condition, "assigned_employee": f"{a.assigned_employee.first_name} {a.assigned_employee.last_name}" if a.assigned_employee else None} for a in db.scalars(stmt.order_by(Asset.asset_tag)).all()]


@app.post("/api/assets", status_code=201)
def create_asset(payload: AssetCreate, user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    asset = Asset(**payload.model_dump()); db.add(asset)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Asset tag, hostname, and serial number must be unique when provided")
    db.add(AssetHistory(asset_id=asset.id, event_type="created", new_value=payload.model_dump(mode="json"), actor_id=user.id))
    audit(db, "asset.created", "asset", asset.id, user.id, new={"asset_tag": asset.asset_tag}); db.commit(); return {"id": asset.id}


@app.post("/api/assets/{asset_id}/assign")
def assign_asset(asset_id: int, payload: AssetAssign, user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER, Role.TECHNICIAN, Role.TEAM_LEAD)), db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset: raise HTTPException(404, "Asset not found")
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


@app.get("/api/admin/users")
def users(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    return [user_dict(u) for u in db.scalars(select(User).order_by(User.display_name)).all()]


@app.post("/api/admin/users", status_code=201)
def create_user(payload: UserCreate, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    errors = validate_password(payload.temporary_password)
    if errors: raise HTTPException(422, errors)
    account = User(username=payload.username.lower(), email=payload.email.lower(), display_name=payload.display_name,
                   role=Role(payload.role), team_id=payload.team_id, password_hash=hash_password(payload.temporary_password), must_change_password=True)
    db.add(account)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409, "Username or email already exists")
    audit(db, "user.created", "user", account.id, user.id, new={"role": account.role.value}); db.commit(); return user_dict(account)


@app.post("/api/admin/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: PasswordReset, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    account = db.get(User, user_id)
    if not account: raise HTTPException(404, "User not found")
    errors = validate_password(payload.temporary_password)
    if errors: raise HTTPException(422, errors)
    account.password_hash = hash_password(payload.temporary_password); account.must_change_password = True
    account.failed_attempts = 0; account.locked_until = None
    audit(db, "password.admin_reset", "user", account.id, user.id); db.commit(); return {"ok": True}


@app.get("/api/admin/settings/{section}")
def get_settings(section: str, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    rows = db.scalars(select(ConfigItem).where(ConfigItem.section == section).order_by(ConfigItem.name)).all()
    return [{"id": row.id, "section": row.section, "name": row.name,
             "value": {k: ("••••••" if row.sensitive else v) for k,v in row.value.items()},
             "description": row.description, "updated_at": row.updated_at} for row in rows]


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
    return [{"id": e.id, "actor_id": e.actor_id, "action": e.action, "record_type": e.record_type, "record_id": e.record_id,
             "previous": e.previous_value, "new": e.new_value, "source_ip": e.source_ip, "correlation_id": e.correlation_id, "created_at": e.created_at} for e in events]


@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [{"id": n.id, "ticket_id": n.ticket_id, "event": n.event, "title": n.title, "body": n.body, "read": n.read_at is not None, "created_at": n.created_at} for n in rows]


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
    return {"application": "Operational", "database": "Connected" if db_ok else "Unavailable",
            "mailbox": (mail_state.value if mail_state else {"status": "Not configured"}),
            "worker": (worker_state.value if worker_state else {"status": "Not running"}),
            "migration_version": migration, "version": __version__, "uptime_seconds": int((now()-started_at).total_seconds()),
            "open_automation_failures": db.scalar(select(func.count(AutomationFailure.id)).where(AutomationFailure.status == "Open")) or 0,
            "notification_failures": db.scalar(select(func.count(Notification.id)).where(Notification.delivery_status == "failed")) or 0,
            "storage": {"database_bytes": Path("data/itsm.db").stat().st_size if Path("data/itsm.db").exists() else 0},
            "backup": {"status": "Not configured", "note": "Configure scheduled database backups before production use"}}


@app.post("/api/feedback", status_code=201)
def feedback(payload: FeedbackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = Feedback(user_id=user.id, feedback_type=payload.feedback_type, current_page=payload.current_page,
                    user_role=user.role.value, app_version=__version__, related_record_id=payload.related_record_id, text=payload.text)
    db.add(item); audit(db, "feedback.created", "feedback", None, user.id, new={"type": payload.feedback_type}); db.commit(); return {"ok": True}


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
    if prior and prior.ticket_id:
        ticket = db.get(Ticket, prior.ticket_id)
        db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=payload.text_body, kind="public", source="email"))
        notify(db, ticket.assigned_user_id, "user.replied", f"Email reply on {ticket.number}", payload.text_body[:200], ticket.id)
        status = "threaded"
    else:
        team, tech, reason = route_ticket(db, "General", requester); priority = "Medium"; first, due = sla_dates(priority)
        ticket = Ticket(number=next_ticket_number(db, "Report an issue"), request_type="Report an issue", subject=payload.subject[:240],
                        description=payload.text_body, requester_id=requester.id, team_id=team.id, assigned_user_id=tech.id if tech else None,
                        status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW, priority=priority, impact="Medium", urgency="Medium",
                        category="General", route_reason=reason, first_response_due=first, resolution_due=due)
        db.add(ticket); db.flush(); db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=payload.text_body, kind="public", source="email"))
        notify(db, requester.id, "ticket.created", f"{ticket.number} created from email", "Your email was received.", ticket.id); status = "created"
    db.add(EmailMessage(message_id=payload.message_id, in_reply_to=payload.in_reply_to, sender=str(payload.sender), subject=payload.subject,
                        ticket_id=ticket.id, processing_status=status, attachment_metadata=payload.attachments))
    audit(db, f"email.{status}", "ticket", ticket.id, requester.id, new={"message_id": payload.message_id, "attachments": len(payload.attachments)})
    db.commit(); return {"status": status, "ticket_id": ticket.id, "ticket_number": ticket.number, "attachments_recorded": len(payload.attachments)}


@app.get("/api/reports/tickets.csv")
def report_csv(user: User = Depends(require_roles(*REPORT_ROLES)), db: Session = Depends(get_db)):
    tickets = db.scalars(select(Ticket).where(visible_ticket_filter(user)).order_by(Ticket.created_at.desc())).all()
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Number","Subject","Status","Priority","Category","Team","Assignee","Created","Resolved"])
    for t in tickets: writer.writerow([t.number,t.subject,t.status.value,t.priority,t.category,t.team.name,t.assigned_user.display_name if t.assigned_user else "",t.created_at,t.resolved_at or ""])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=northstar-desk-tickets.csv"})


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

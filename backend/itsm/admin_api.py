import enum
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .admin_services import EVENTS, NOTIFICATION_TEMPLATES, evaluate_group, provider_requirements, queue_simulation
from .config import settings
from .credential_store import clear_integration_secret, get_integration_secret, integration_secret_status, set_integration_secret
from .database import get_db
from .models import *
from .schemas import *
from .security import hash_password, require_roles, validate_password
from .services import audit, notification_context, notification_delivery_enabled, outbound_email_delivery_enabled, notify, render_notification_text

router=APIRouter(prefix="/api/admin",tags=["Administration"])


def conflict_guard(item, version: int | None):
    if version is not None and getattr(item,"version",1)!=version:
        raise HTTPException(409,"This record was changed by another administrator. Reload before saving.")


def bump(item): item.version=getattr(item,"version",1)+1
def as_aware(value:datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


GUIDED_PROVIDERS = {"Microsoft Entra ID", "Microsoft 365", "RingCentral"}


def _oauth_state(payload: dict) -> str:
    payload = {**payload, "expires": int(time.time()) + 600, "nonce": uuid.uuid4().hex}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def _read_oauth_state(value: str) -> dict:
    try:
        raw, signature = value.rsplit(".", 1)
        expected = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        payload = json.loads(decoded)
        if int(payload["expires"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "This provider authorization request is invalid or has expired. Start the connection again.") from exc


def _connection_callback(provider: str) -> str:
    slug = "microsoft" if provider.startswith("Microsoft") else "ringcentral"
    public_url = settings.public_url.rstrip("/")
    parsed = urlsplit(public_url)
    if parsed.hostname in {"127.0.0.1", "::1"}:
        host = f"localhost:{parsed.port}" if parsed.port else "localhost"
        public_url = urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))
    return f"{public_url}/api/admin/integrations/oauth/callback/{slug}"


def _provider_application(db:Session,provider_slug:str) -> dict:
    namespace=f"platform:{provider_slug}"
    configured_client_id=settings.microsoft_client_id if provider_slug=="microsoft" else settings.ringcentral_client_id
    configured_secret=settings.microsoft_client_secret if provider_slug=="microsoft" else settings.ringcentral_client_secret
    return {
        "client_id": configured_client_id or get_integration_secret(db,namespace,"client_id") or "",
        "client_secret": configured_secret or get_integration_secret(db,namespace,"client_secret") or "",
        "environment": (get_integration_secret(db,namespace,"environment") or
                        (settings.ringcentral_environment if provider_slug=="ringcentral" else "production")),
    }


def admin_count(db:Session,exclude_id:int|None=None):
    stmt=select(func.count(User.id)).where(User.role==Role.ADMIN,User.active.is_(True))
    if exclude_id: stmt=stmt.where(User.id!=exclude_id)
    return db.scalar(stmt) or 0


def user_admin_dict(account:User,db:Session,detail=False):
    team_ids=db.scalars(select(TeamMembership.team_id).where(TeamMembership.user_id==account.id,TeamMembership.active.is_(True))).all()
    role_ids=db.scalars(select(UserRoleAssignment.role_definition_id).where(UserRoleAssignment.user_id==account.id,UserRoleAssignment.active.is_(True))).all()
    group_ids=db.scalars(select(UserGroupMembership.group_id).where(UserGroupMembership.user_id==account.id)).all()
    data={"id":account.id,"username":account.username,"email":account.email,"display_name":account.display_name,"role":account.role.value,
        "active":account.active,"must_change_password":account.must_change_password,"availability":account.availability,"team_id":account.team_id,
        "team":account.team.name if account.team else None,"last_login_at":account.last_login_at,"ringcentral_extension_id":account.ringcentral_extension_id,
        "ringcentral_extension_number":account.ringcentral_extension_number,"alternate_email":account.alternate_email,"employee_number":account.employee_number,
        "phone":account.phone,"job_title":account.job_title,"department_name":account.department_name,"location_name":account.location_name,
        "manager_user_id":account.manager_user_id,"timezone":account.timezone,"preferred_language":account.preferred_language,
        "notification_preferences":account.notification_preferences or {},"auth_source":account.auth_source,"role_source":account.role_source,
        "team_source":account.team_source,"team_ids":team_ids,"role_definition_ids":role_ids,"group_ids":group_ids,"version":account.version,
        "archived_at":account.archived_at,"created_at":account.created_at,"updated_at":account.updated_at}
    if detail:
        data["assigned_assets"]=[{"id":a.id,"asset_tag":a.asset_tag,"hostname":a.hostname,"status":a.status} for a in db.scalars(select(Asset).join(Employee,Asset.assigned_employee_id==Employee.id).where(Employee.user_id==account.id,Asset.is_archived.is_(False))).all()]
        data["open_tickets"]=[{"id":t.id,"number":t.number,"subject":t.subject,"status":t.status.value} for t in db.scalars(select(Ticket).where(or_(Ticket.requester_id==account.id,Ticket.assigned_user_id==account.id),Ticket.status.not_in([TicketStatus.CLOSED,TicketStatus.CANCELLED]))).all()]
        data["audit"]=[{"id":x.id,"action":x.action,"created_at":x.created_at} for x in db.scalars(select(AuditEvent).where(AuditEvent.record_type=="user",AuditEvent.record_id==str(account.id)).order_by(AuditEvent.created_at.desc()).limit(100)).all()]
    return data


def replace_user_links(db:Session,account:User,role_ids:list[int]|None,team_ids:list[int]|None,group_ids:list[int]|None):
    if role_ids is not None:
        db.execute(delete(UserRoleAssignment).where(UserRoleAssignment.user_id==account.id))
        valid=db.scalars(select(RoleDefinition.id).where(RoleDefinition.id.in_(role_ids),RoleDefinition.active.is_(True))).all() if role_ids else []
        db.add_all([UserRoleAssignment(user_id=account.id,role_definition_id=x) for x in valid])
    if team_ids is not None:
        db.execute(delete(TeamMembership).where(TeamMembership.user_id==account.id))
        valid=db.scalars(select(Team.id).where(Team.id.in_(team_ids),Team.active.is_(True))).all() if team_ids else []
        db.add_all([TeamMembership(team_id=x,user_id=account.id,is_primary=x==account.team_id) for x in valid])
    if group_ids is not None:
        db.execute(delete(UserGroupMembership).where(UserGroupMembership.user_id==account.id))
        valid=db.scalars(select(UserGroup.id).where(UserGroup.id.in_(group_ids),UserGroup.active.is_(True))).all() if group_ids else []
        db.add_all([UserGroupMembership(group_id=x,user_id=account.id,membership_role="member") for x in valid])


@router.get("/users")
def list_users(q:str="",role:str|None=None,team_id:int|None=None,source:str|None=None,active:bool|None=None,availability:str|None=None,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    stmt=select(User)
    if q:
        term=f"%{q}%"; stmt=stmt.where(or_(User.display_name.ilike(term),User.email.ilike(term),User.username.ilike(term),User.employee_number.ilike(term),User.department_name.ilike(term),User.location_name.ilike(term)))
    if role: stmt=stmt.where(User.role==Role(role))
    if team_id: stmt=stmt.where(or_(User.team_id==team_id,User.id.in_(select(TeamMembership.user_id).where(TeamMembership.team_id==team_id))))
    if source: stmt=stmt.where(User.auth_source==source)
    if active is not None: stmt=stmt.where(User.active==active)
    if availability: stmt=stmt.where(User.availability==availability)
    return [user_admin_dict(x,db) for x in db.scalars(stmt.order_by(User.display_name)).all()]


@router.get("/users/{user_id}")
def get_user(user_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    return user_admin_dict(account,db,True)


@router.post("/users",status_code=201)
def create_user(payload:AdminUserCreate,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    errors=validate_password(payload.temporary_password)
    if errors: raise HTTPException(422,errors)
    values=payload.model_dump(exclude={"temporary_password","role_definition_ids","team_ids","group_ids"})
    if values.get("team_id") and not db.get(Team,values["team_id"]): raise HTTPException(422,"Primary team not found")
    values["role"]=Role(values["role"]); values["username"]=values["username"].lower(); values["email"]=values["email"].lower()
    account=User(**values,password_hash=hash_password(payload.temporary_password),must_change_password=True)
    db.add(account)
    try: db.flush(); replace_user_links(db,account,payload.role_definition_ids,payload.team_ids,payload.group_ids)
    except IntegrityError: db.rollback(); raise HTTPException(409,"Username or email already exists")
    audit(db,"user.created","user",account.id,user.id,new={"role":account.role.value,"source":account.auth_source}); db.commit(); return user_admin_dict(account,db)


@router.patch("/users/{user_id}")
def update_user(user_id:int,payload:UserUpdate,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    changes=payload.model_dump(exclude_none=True); conflict_guard(account,changes.pop("version",None))
    role_ids=changes.pop("role_definition_ids",None); team_ids=changes.pop("team_ids",None); group_ids=changes.pop("group_ids",None)
    if changes.get("team_id") and not db.get(Team,changes["team_id"]): raise HTTPException(422,"Primary team not found")
    if "role" in changes:
        next_role=Role(changes["role"])
        if account.role==Role.ADMIN and next_role!=Role.ADMIN and admin_count(db,account.id)==0: raise HTTPException(409,"The final active administrator cannot lose Administrator access")
        changes["role"]=next_role
    if changes.get("active") is False and account.role==Role.ADMIN and admin_count(db,account.id)==0: raise HTTPException(409,"The final active administrator cannot be deactivated")
    previous={k:getattr(account,k).value if isinstance(getattr(account,k),enum.Enum) else getattr(account,k) for k in changes}
    for key,value in changes.items(): setattr(account,key,value)
    replace_user_links(db,account,role_ids,team_ids,group_ids); bump(account)
    audit(db,"user.updated","user",account.id,user.id,previous,{k:str(v) for k,v in changes.items()}); db.commit(); return user_admin_dict(account,db)


@router.delete("/users/{user_id}")
def deactivate_user(user_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    if account.id==user.id: raise HTTPException(409,"You cannot deactivate your own account")
    if account.role==Role.ADMIN and admin_count(db,account.id)==0: raise HTTPException(409,"The final active administrator cannot be deactivated")
    account.active=False; account.availability="Unavailable"; account.archived_at=now(); bump(account)
    db.execute(delete(Session).where(Session.user_id==account.id))
    memberships=db.scalars(select(TeamMembership).where(TeamMembership.user_id==account.id,TeamMembership.active.is_(True))).all()
    for membership in memberships: membership.active=False
    audit(db,"user.deactivated","user",account.id,user.id,new={"assignment_eligibility":False,"sessions_revoked":True})
    db.commit(); return {"ok":True,"archived":True}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    if not db.get(User,user_id): raise HTTPException(404,"User not found")
    count=db.execute(delete(Session).where(Session.user_id==user_id)).rowcount; audit(db,"user.sessions_revoked","user",user_id,user.id,new={"sessions":count}); db.commit(); return {"ok":True,"sessions_revoked":count}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id:int,payload:PasswordReset,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    if account.auth_source!="Local": raise HTTPException(409,"Password resets must be completed in the authoritative identity provider")
    errors=validate_password(payload.temporary_password)
    if errors: raise HTTPException(422,errors)
    account.password_hash=hash_password(payload.temporary_password); account.must_change_password=True; bump(account)
    sessions=db.execute(delete(Session).where(Session.user_id==account.id)).rowcount
    audit(db,"password.admin_reset","user",account.id,user.id,new={"force_change":True,"sessions_revoked":sessions}); db.commit()
    return {"ok":True,"must_change_password":True,"sessions_revoked":sessions}


@router.post("/users/{user_id}/force-password-change")
def force_user_password_change(user_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    if account.auth_source!="Local": raise HTTPException(409,"Password policy is controlled by the authoritative identity provider")
    account.must_change_password=True; bump(account)
    audit(db,"password.force_change_enabled","user",account.id,user.id); db.commit()
    return {"ok":True,"must_change_password":True}


def role_dict(x:RoleDefinition,db:Session):
    count=db.scalar(select(func.count(UserRoleAssignment.id)).where(UserRoleAssignment.role_definition_id==x.id,UserRoleAssignment.active.is_(True))) or 0
    legacy=db.scalar(select(func.count(User.id)).where(User.role==Role(x.key))) if x.key in {r.value for r in Role} else 0
    return {"id":x.id,"key":x.key,"name":x.name,"description":x.description,"permissions":x.permissions or {},"parent_role_id":x.parent_role_id,"system":x.system,"active":x.active,"user_count":count+(legacy or 0),"version":x.version}


@router.get("/roles")
def roles(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [role_dict(x,db) for x in db.scalars(select(RoleDefinition).order_by(RoleDefinition.system.desc(),RoleDefinition.name)).all()]

@router.post("/roles",status_code=201)
def create_role(payload:RoleDefinitionIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=RoleDefinition(**payload.model_dump(exclude={"version"}),system=False); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Role name or key already exists")
    audit(db,"role.created","role",item.id,user.id,new={"name":item.name}); db.commit(); return role_dict(item,db)

@router.patch("/roles/{item_id}")
def update_role(item_id:int,payload:RoleDefinitionIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(RoleDefinition,item_id)
    if not item: raise HTTPException(404,"Role not found")
    conflict_guard(item,payload.version); values=payload.model_dump(exclude={"version"})
    if item.system and values["key"]!=item.key: raise HTTPException(409,"System role keys cannot be changed")
    previous=role_dict(item,db)
    for k,v in values.items(): setattr(item,k,v)
    bump(item); audit(db,"role.updated","role",item.id,user.id,previous,{"name":item.name}); db.commit(); return role_dict(item,db)

@router.post("/roles/{item_id}/duplicate",status_code=201)
def duplicate_role(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    source=db.get(RoleDefinition,item_id)
    if not source: raise HTTPException(404,"Role not found")
    suffix=uuid.uuid4().hex[:6]; item=RoleDefinition(key=f"{source.key}_copy_{suffix}",name=f"{source.name} Copy",description=source.description,permissions=source.permissions,system=False,active=True); db.add(item); db.flush(); audit(db,"role.duplicated","role",item.id,user.id,new={"source_id":source.id}); db.commit(); return role_dict(item,db)

@router.delete("/roles/{item_id}")
def archive_role(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(RoleDefinition,item_id)
    if not item: raise HTTPException(404,"Role not found")
    if item.system: raise HTTPException(409,"System roles cannot be deleted")
    item.active=False; item.archived_at=now(); bump(item); audit(db,"role.archived","role",item.id,user.id); db.commit(); return {"ok":True,"archived":True}

@router.get("/users/{user_id}/effective-permissions")
def effective_permissions(user_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    account=db.get(User,user_id)
    if not account: raise HTTPException(404,"User not found")
    roles=db.scalars(select(RoleDefinition).where(or_(RoleDefinition.key==account.role.value,RoleDefinition.id.in_(select(UserRoleAssignment.role_definition_id).where(UserRoleAssignment.user_id==account.id,UserRoleAssignment.active.is_(True)))))).all()
    effective={}; expanded=[]; visited=set(); stack=list(roles)
    while stack:
        role=stack.pop()
        if role.id in visited: continue
        visited.add(role.id); expanded.append(role)
        if role.parent_role_id:
            parent=db.get(RoleDefinition,role.parent_role_id)
            if parent and parent.active: stack.append(parent)
    for role in expanded:
        for area,permissions in (role.permissions or {}).items(): effective.setdefault(area,set()).update(permissions)
    return {"user_id":account.id,"roles":[role_dict(x,db) for x in expanded],"permissions":{k:sorted(v) for k,v in effective.items()}}


def group_type_dict(x:GroupType,db:Session): return {"id":x.id,"name":x.name,"description":x.description,"icon":x.icon,"color":x.color,"purpose":x.purpose,"allowed_uses":x.allowed_uses or [],"sort_order":x.sort_order,"active":x.active,"group_count":db.scalar(select(func.count(UserGroup.id)).where(UserGroup.group_type_id==x.id,UserGroup.active.is_(True))) or 0,"version":x.version}

@router.get("/group-types")
def group_types(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [group_type_dict(x,db) for x in db.scalars(select(GroupType).order_by(GroupType.sort_order,GroupType.name)).all()]

@router.post("/group-types",status_code=201)
def create_group_type(payload:GroupTypeIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=GroupType(**payload.model_dump(exclude={"version"})); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Group type already exists")
    audit(db,"group_type.created","group_type",item.id,user.id,new={"name":item.name}); db.commit(); return group_type_dict(item,db)

@router.patch("/group-types/{item_id}")
def update_group_type(item_id:int,payload:GroupTypeIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(GroupType,item_id)
    if not item: raise HTTPException(404,"Group type not found")
    conflict_guard(item,payload.version); previous=group_type_dict(item,db)
    for k,v in payload.model_dump(exclude={"version"}).items(): setattr(item,k,v)
    bump(item); audit(db,"group_type.updated","group_type",item.id,user.id,previous,{"name":item.name}); db.commit(); return group_type_dict(item,db)

@router.delete("/group-types/{item_id}")
def archive_group_type(item_id:int,reassign_to:int|None=None,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(GroupType,item_id)
    if not item: raise HTTPException(404,"Group type not found")
    count=db.scalar(select(func.count(UserGroup.id)).where(UserGroup.group_type_id==item.id,UserGroup.active.is_(True))) or 0
    if count and not reassign_to: raise HTTPException(409,f"{count} active groups use this type. Choose a replacement before archiving it.")
    if count:
        replacement=db.get(GroupType,reassign_to)
        if not replacement or replacement.id==item.id: raise HTTPException(422,"Replacement group type not found")
        for group in db.scalars(select(UserGroup).where(UserGroup.group_type_id==item.id)).all(): group.group_type_id=replacement.id; group.group_type=replacement.name
    item.active=False; item.archived_at=now(); bump(item); audit(db,"group_type.archived","group_type",item.id,user.id,new={"reassigned_groups":count}); db.commit(); return {"ok":True,"archived":True,"reassigned_groups":count}


def group_dict(x:UserGroup,db:Session):
    memberships=db.execute(select(UserGroupMembership.user_id,UserGroupMembership.membership_role).where(UserGroupMembership.group_id==x.id)).all(); gt=db.get(GroupType,x.group_type_id) if x.group_type_id else None
    return {"id":x.id,"name":x.name,"group_type":gt.name if gt else x.group_type,"group_type_id":x.group_type_id,"description":x.description,"source":x.source,"active":x.active,
        "manager_user_id":x.manager_user_id,"email":x.email,"region":x.region,"timezone":x.timezone,"escalation_contact":x.escalation_contact,
        "member_ids":[i for i,r in memberships if r=="member"],"owner_ids":[i for i,r in memberships if r=="owner"],"member_count":len(memberships),"version":x.version}

@router.get("/groups")
def groups(q:str="",user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    stmt=select(UserGroup)
    if q: stmt=stmt.where(or_(UserGroup.name.ilike(f"%{q}%"),UserGroup.email.ilike(f"%{q}%"),UserGroup.description.ilike(f"%{q}%")))
    return [group_dict(x,db) for x in db.scalars(stmt.order_by(UserGroup.name)).all()]

@router.post("/groups",status_code=201)
def create_group(payload:GroupIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    values=payload.model_dump(exclude={"member_ids","owner_ids","version"}); gt=db.get(GroupType,payload.group_type_id) if payload.group_type_id else None
    if payload.group_type_id and not gt: raise HTTPException(422,"Group type not found")
    if gt: values["group_type"]=gt.name
    item=UserGroup(**values); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,"Group name already exists")
    valid=set(db.scalars(select(User.id).where(User.id.in_([*payload.member_ids,*payload.owner_ids]))).all()) if payload.member_ids or payload.owner_ids else set()
    db.add_all([UserGroupMembership(group_id=item.id,user_id=i,membership_role="owner" if i in payload.owner_ids else "member") for i in valid]); audit(db,"group.created","group",item.id,user.id,new={"name":item.name,"members":len(valid)}); db.commit(); return group_dict(item,db)

@router.patch("/groups/{item_id}")
def update_group(item_id:int,payload:GroupIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(UserGroup,item_id)
    if not item: raise HTTPException(404,"Group not found")
    conflict_guard(item,payload.version); values=payload.model_dump(exclude={"member_ids","owner_ids","version"}); gt=db.get(GroupType,payload.group_type_id) if payload.group_type_id else None
    if payload.group_type_id and not gt: raise HTTPException(422,"Group type not found")
    if gt: values["group_type"]=gt.name
    previous=group_dict(item,db)
    for k,v in values.items(): setattr(item,k,v)
    db.execute(delete(UserGroupMembership).where(UserGroupMembership.group_id==item.id)); valid=set(db.scalars(select(User.id).where(User.id.in_([*payload.member_ids,*payload.owner_ids]))).all()) if payload.member_ids or payload.owner_ids else set()
    db.add_all([UserGroupMembership(group_id=item.id,user_id=i,membership_role="owner" if i in payload.owner_ids else "member") for i in valid]); bump(item); audit(db,"group.updated","group",item.id,user.id,previous,{"name":item.name,"members":len(valid)}); db.commit(); return group_dict(item,db)

@router.post("/groups/{item_id}/duplicate",status_code=201)
def duplicate_group(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    source=db.get(UserGroup,item_id)
    if not source: raise HTTPException(404,"Group not found")
    item=UserGroup(name=f"{source.name} Copy {uuid.uuid4().hex[:4]}",group_type=source.group_type,group_type_id=source.group_type_id,description=source.description,source="Local",active=True,email="",region=source.region,timezone=source.timezone); db.add(item); db.flush()
    for membership in db.scalars(select(UserGroupMembership).where(UserGroupMembership.group_id==source.id)).all(): db.add(UserGroupMembership(group_id=item.id,user_id=membership.user_id,membership_role=membership.membership_role))
    audit(db,"group.duplicated","group",item.id,user.id,new={"source_id":source.id}); db.commit(); return group_dict(item,db)

@router.delete("/groups/{item_id}")
def archive_group(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(UserGroup,item_id)
    if not item: raise HTTPException(404,"Group not found")
    item.active=False; item.archived_at=now(); bump(item); audit(db,"group.archived","group",item.id,user.id); db.commit(); return {"ok":True,"archived":True}


def team_dict(x:Team,db:Session):
    members=db.scalars(select(TeamMembership).where(TeamMembership.team_id==x.id,TeamMembership.active.is_(True))).all(); queue_ids=db.scalars(select(QueueTeamEligibility.queue_id).where(QueueTeamEligibility.team_id==x.id,QueueTeamEligibility.active.is_(True))).all()
    open_count=db.scalar(select(func.count(Ticket.id)).where(Ticket.team_id==x.id,Ticket.status.not_in([TicketStatus.RESOLVED,TicketStatus.CLOSED,TicketStatus.CANCELLED]))) or 0
    available=db.scalar(select(func.count(User.id)).where(User.id.in_([m.user_id for m in members]),User.availability=="Available",User.active.is_(True))) if members else 0
    return {"id":x.id,"name":x.name,"key":x.key,"description":x.description,"lead_user_id":x.lead_user_id,"backup_lead_user_id":x.backup_lead_user_id,
        "member_ids":[m.user_id for m in members],"primary_member_ids":[m.user_id for m in members if m.is_primary],"region":x.region,"supported_locations":x.supported_locations or [],"timezone":x.timezone,
        "business_hours":x.business_hours or {},"supported_services":x.supported_services or [],"supported_categories":x.supported_categories or [],"skills":x.skills or [],"default_capacity":x.default_capacity,
        "escalation_team_id":x.escalation_team_id,"active":x.active,"queue_ids":queue_ids,"open_ticket_count":open_count,"available_technician_count":available or 0,"version":x.version}

@router.get("/teams")
def teams(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [team_dict(x,db) for x in db.scalars(select(Team).order_by(Team.name)).all()]

def save_team_members(db:Session,item:Team,member_ids:list[int],primary_ids:list[int]):
    db.execute(delete(TeamMembership).where(TeamMembership.team_id==item.id)); valid=db.scalars(select(User.id).where(User.id.in_(member_ids),User.active.is_(True))).all() if member_ids else []
    db.add_all([TeamMembership(team_id=item.id,user_id=i,is_primary=i in primary_ids) for i in valid])

@router.post("/teams",status_code=201)
def create_team(payload:TeamIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    values=payload.model_dump(exclude={"member_ids","primary_member_ids","version"}); item=Team(**values,queue_name=f"{payload.name} Queue"); db.add(item)
    try: db.flush(); save_team_members(db,item,payload.member_ids,payload.primary_member_ids)
    except IntegrityError: db.rollback(); raise HTTPException(409,"Team name or key already exists")
    audit(db,"team.created","team",item.id,user.id,new={"name":item.name}); db.commit(); return team_dict(item,db)

@router.patch("/teams/{item_id}")
def update_team(item_id:int,payload:TeamIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(Team,item_id)
    if not item: raise HTTPException(404,"Team not found")
    conflict_guard(item,payload.version); previous=team_dict(item,db)
    for k,v in payload.model_dump(exclude={"member_ids","primary_member_ids","version"}).items(): setattr(item,k,v)
    save_team_members(db,item,payload.member_ids,payload.primary_member_ids); bump(item); audit(db,"team.updated","team",item.id,user.id,previous,{"name":item.name}); db.commit(); return team_dict(item,db)

@router.delete("/teams/{item_id}")
def archive_team(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(Team,item_id)
    if not item: raise HTTPException(404,"Team not found")
    item.active=False; item.archived_at=now(); bump(item); audit(db,"team.archived","team",item.id,user.id); db.commit(); return {"ok":True,"archived":True}


def category_dict(x:ServiceCategory): return {"id":x.id,"name":x.name,"parent_id":x.parent_id,"level":x.level,"description":x.description,"sort_order":x.sort_order,"configuration":x.configuration or {},"active":x.active,"archived_at":x.archived_at,"version":x.version}
def validate_category_parent(db:Session,item_id:int|None,parent_id:int|None,level:str):
    expected={"category":None,"subcategory":"category","item":"subcategory"}[level]
    if expected is None and parent_id is not None: raise HTTPException(422,"A top-level category cannot have a parent")
    if expected is not None:
        parent=db.get(ServiceCategory,parent_id) if parent_id else None
        if not parent or not parent.active or parent.level!=expected: raise HTTPException(422,f"A {level} must have an active {expected} parent")
    if item_id and parent_id==item_id: raise HTTPException(422,"A category cannot be its own parent")
def category_dependencies(db:Session,item:ServiceCategory):
    children=db.scalar(select(func.count(ServiceCategory.id)).where(ServiceCategory.parent_id==item.id,ServiceCategory.active.is_(True))) or 0
    teams=[team.name for team in db.scalars(select(Team).where(Team.active.is_(True))).all() if item.id in (team.supported_categories or [])]
    routing=[]
    for rule in db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True))).all():
        conditions=(rule.conditions or {}).get("conditions",[]) if isinstance(rule.conditions,dict) else (rule.conditions or [])
        if any(condition.get("field") in {"category","subcategory","item"} and str(condition.get("value","")).lower()==item.name.lower() for condition in conditions): routing.append(rule.name)
    return {"active_children":children,"teams":teams,"routing_rules":routing,"in_use":bool(children or teams or routing)}
@router.get("/categories")
def categories(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [category_dict(x) for x in db.scalars(select(ServiceCategory).order_by(ServiceCategory.sort_order,ServiceCategory.name)).all()]
@router.post("/categories",status_code=201)
def create_category(payload:CategoryIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    validate_category_parent(db,None,payload.parent_id,payload.level)
    item=ServiceCategory(**payload.model_dump(exclude={"version"})); db.add(item)
    try: db.flush()
    except IntegrityError: db.rollback(); raise HTTPException(409,"A category with this name already exists under the selected parent")
    audit(db,"category.created","category",item.id,user.id,new=payload.model_dump()); db.commit(); return category_dict(item)
@router.patch("/categories/{item_id}")
def update_category(item_id:int,payload:CategoryIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(ServiceCategory,item_id)
    if not item: raise HTTPException(404,"Category not found")
    conflict_guard(item,payload.version); validate_category_parent(db,item.id,payload.parent_id,payload.level)
    for k,v in payload.model_dump(exclude={"version"}).items(): setattr(item,k,v)
    bump(item); audit(db,"category.updated","category",item.id,user.id,new=payload.model_dump()); db.commit(); return category_dict(item)
@router.get("/categories/{item_id}/dependencies")
def get_category_dependencies(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(ServiceCategory,item_id)
    if not item: raise HTTPException(404,"Category not found")
    return category_dependencies(db,item)
@router.post("/categories/reorder")
def reorder_categories(payload:list[dict],user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    for position,row in enumerate(payload):
        item=db.get(ServiceCategory,int(row.get("id",0)))
        if not item: raise HTTPException(422,f"Category at position {position+1} was not found")
        item.sort_order=int(row.get("sort_order",position*10)); bump(item)
    audit(db,"category.reordered","category",None,user.id,new={"count":len(payload)}); db.commit(); return {"ok":True,"count":len(payload)}
@router.delete("/categories/{item_id}")
def archive_category(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(ServiceCategory,item_id)
    if not item: raise HTTPException(404,"Category not found")
    dependencies=category_dependencies(db,item)
    if dependencies["in_use"]: raise HTTPException(409,{"message":"Remove or reassign category dependencies before archiving","dependencies":dependencies})
    item.active=False; item.archived_at=now(); bump(item); audit(db,"category.archived","category",item.id,user.id); db.commit(); return {"ok":True,"archived":True}
@router.post("/categories/{item_id}/unarchive")
def unarchive_category(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(ServiceCategory,item_id)
    if not item: raise HTTPException(404,"Category not found")
    validate_category_parent(db,item.id,item.parent_id,item.level)
    item.active=True; item.archived_at=None; bump(item); audit(db,"category.unarchived","category",item.id,user.id); db.commit(); return category_dict(item)


def queue_dict(x:SupportQueue,db:Session):
    links=db.scalars(select(QueueTeamEligibility).where(QueueTeamEligibility.queue_id==x.id).order_by(QueueTeamEligibility.eligibility_priority)).all()
    return {"id":x.id,"name":x.name,"key":x.key,"team_id":x.team_id,"team":x.team.name if x.team else None,"manager_user_id":x.manager_user_id,"description":x.description,
        "assignment_strategy":x.assignment_strategy,"configuration":x.configuration or {},"priority_order":x.priority_order,"active":x.active,"version":x.version,
        "eligible_teams":[{"team_id":i.team_id,"eligibility_priority":i.eligibility_priority,"weight":i.weight,"schedule":i.schedule or {},"capacity_override":i.capacity_override,"active":i.active} for i in links]}
def save_queue_teams(db:Session,item:SupportQueue,teams:list[dict]):
    db.execute(delete(QueueTeamEligibility).where(QueueTeamEligibility.queue_id==item.id)); values=teams or [{"team_id":item.team_id,"eligibility_priority":100,"weight":100,"schedule":{},"active":True}]
    valid=set(db.scalars(select(Team.id).where(Team.id.in_([x.get("team_id") for x in values]),Team.active.is_(True))).all())
    db.add_all([QueueTeamEligibility(queue_id=item.id,team_id=x["team_id"],eligibility_priority=x.get("eligibility_priority",100),weight=x.get("weight",100),schedule=x.get("schedule",{}),capacity_override=x.get("capacity_override"),active=x.get("active",True)) for x in values if x.get("team_id") in valid])
@router.get("/queues")
def queues(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [queue_dict(x,db) for x in db.scalars(select(SupportQueue).order_by(SupportQueue.priority_order,SupportQueue.name)).all()]
@router.post("/queues",status_code=201)
def create_queue(payload:QueueIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    if not db.get(Team,payload.team_id): raise HTTPException(422,"Owning team not found")
    values=payload.model_dump(exclude={"eligible_teams","version"}); values["key"]=values["key"] or re.sub(r"[^a-z0-9]+","-",values["name"].lower()).strip("-")
    item=SupportQueue(**values); db.add(item)
    try: db.flush(); save_queue_teams(db,item,payload.eligible_teams)
    except IntegrityError: db.rollback(); raise HTTPException(409,"Queue name or key already exists")
    audit(db,"queue.created","queue",item.id,user.id,new={"name":item.name}); db.commit(); return queue_dict(item,db)
@router.patch("/queues/{item_id}")
def update_queue(item_id:int,payload:QueueIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(SupportQueue,item_id)
    if not item: raise HTTPException(404,"Queue not found")
    conflict_guard(item,payload.version); previous=queue_dict(item,db)
    for k,v in payload.model_dump(exclude={"eligible_teams","version"}).items(): setattr(item,k,v)
    save_queue_teams(db,item,payload.eligible_teams); bump(item); audit(db,"queue.updated","queue",item.id,user.id,previous,{"name":item.name}); db.commit(); return queue_dict(item,db)
@router.post("/queues/{item_id}/simulate")
def simulate_queue(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(SupportQueue,item_id)
    if not item: raise HTTPException(404,"Queue not found")
    return queue_simulation(db,item)
@router.delete("/queues/{item_id}")
def archive_queue(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(SupportQueue,item_id)
    if not item: raise HTTPException(404,"Queue not found")
    rule_names=[rule.name for rule in db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True))).all() if (rule.actions or {}).get("queue_id")==item.id]
    overflow_names=[queue.name for queue in db.scalars(select(SupportQueue).where(SupportQueue.active.is_(True),SupportQueue.id!=item.id)).all() if (queue.configuration or {}).get("overflow_queue_id")==item.id]
    if rule_names or overflow_names: raise HTTPException(409,{"message":"Remove queue dependencies before archiving","routing_rules":rule_names,"overflow_queues":overflow_names})
    item.active=False; item.archived_at=now(); bump(item); audit(db,"queue.archived","queue",item.id,user.id); db.commit(); return {"ok":True,"archived":True}


def routing_dict(x:RoutingRule): return {"id":x.id,"name":x.name,"description":x.description,"trigger":x.trigger,"priority_order":x.priority_order,"conditions":x.conditions or [],"actions":x.actions or {},"status":x.status,"active":x.active,"stop_processing":x.stop_processing,"overwrite_existing":x.overwrite_existing,"reevaluate_fields":x.reevaluate_fields or [],"effective_from":x.effective_from,"effective_until":x.effective_until,"match_count":x.match_count,"last_matched_at":x.last_matched_at,"version":x.version}
def snapshot_rule(x:RoutingRule):
    data=routing_dict(x)
    for key in ("effective_from","effective_until","last_matched_at"):
        if isinstance(data.get(key),datetime): data[key]=data[key].isoformat()
    return data
ROUTING_FIELDS={"organization","requester","requester_email","requester_domain","requester_department","location_name","requester_group","vip","channel","request_type","category","subcategory","service","asset_type","priority","impact","urgency","keywords","business_hours","telephone_number","call_queue","status"}
ROUTING_OPERATORS={"equals","does_not_equal","contains","does_not_contain","starts_with","ends_with","is_empty","is_not_empty","in","not_in","greater_than","less_than","matches"}
def validate_routing_rule(db:Session,payload:RoutingRuleIn):
    leaves=[]
    def walk(node,depth=0):
        if depth>5: raise HTTPException(422,"Routing conditions may not be nested more than five levels")
        if isinstance(node,list):
            for child in node: walk(child,depth+1)
        elif isinstance(node,dict) and "conditions" in node:
            if str(node.get("logic","AND")).upper() not in {"AND","OR"}: raise HTTPException(422,"Condition groups must use AND or OR")
            for child in node.get("conditions",[]): walk(child,depth+1)
        elif isinstance(node,dict): leaves.append(node)
        else: raise HTTPException(422,"Routing conditions contain an invalid entry")
    walk(payload.conditions)
    if len(leaves)>50: raise HTTPException(422,"A routing rule may contain at most 50 conditions")
    for condition in leaves:
        if condition.get("field") not in ROUTING_FIELDS or condition.get("operator","equals") not in ROUTING_OPERATORS:
            raise HTTPException(422,"Routing rule contains an unsupported field or operator")
    queue_id=payload.actions.get("queue_id"); team_id=payload.actions.get("team_id")
    if queue_id and not db.scalar(select(SupportQueue.id).where(SupportQueue.id==int(queue_id),SupportQueue.active.is_(True))): raise HTTPException(422,"Routing action references an inactive or missing queue")
    if team_id and not db.scalar(select(Team.id).where(Team.id==int(team_id),Team.active.is_(True))): raise HTTPException(422,"Routing action references an inactive or missing team")
    if payload.effective_from and payload.effective_until and payload.effective_until<=payload.effective_from: raise HTTPException(422,"Routing rule effective end must be after its start")
    action_fields={str(key).removesuffix("_id") for key in payload.actions}
    if not payload.stop_processing and action_fields.intersection(payload.reevaluate_fields): raise HTTPException(422,"Loop protection: a continuing rule cannot reevaluate a field it changes")
@router.get("/routing-rules")
def routing_rules(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [routing_dict(x) for x in db.scalars(select(RoutingRule).order_by(RoutingRule.priority_order,RoutingRule.name)).all()]
@router.post("/routing-rules",status_code=201)
def create_routing(payload:RoutingRuleIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    validate_routing_rule(db,payload); values=payload.model_dump(exclude={"version"}); values["active"]=values["status"]=="active" and values["active"]; item=RoutingRule(**values); db.add(item); db.flush(); db.add(RoutingRuleVersion(routing_rule_id=item.id,version=1,snapshot=snapshot_rule(item),created_by_id=user.id)); audit(db,"routing_rule.created","routing_rule",item.id,user.id,new={"name":item.name}); db.commit(); return routing_dict(item)
@router.patch("/routing-rules/{item_id}")
def update_routing(item_id:int,payload:RoutingRuleIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(RoutingRule,item_id)
    if not item: raise HTTPException(404,"Routing rule not found")
    conflict_guard(item,payload.version); validate_routing_rule(db,payload); previous=snapshot_rule(item)
    for k,v in payload.model_dump(exclude={"version"}).items(): setattr(item,k,v)
    item.active=item.status=="active" and item.active; bump(item); db.add(RoutingRuleVersion(routing_rule_id=item.id,version=item.version,snapshot=snapshot_rule(item),created_by_id=user.id)); audit(db,"routing_rule.updated","routing_rule",item.id,user.id,previous,{"version":item.version}); db.commit(); return routing_dict(item)
@router.post("/routing-rules/test")
def test_routing(sample:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    trace=[]; final={}; matched_rules=[]
    current=now()
    for rule in db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True),RoutingRule.status=="active").order_by(RoutingRule.priority_order)).all():
        if (rule.effective_from and as_aware(rule.effective_from)>current) or (rule.effective_until and as_aware(rule.effective_until)<current):
            trace.append({"rule_id":rule.id,"rule":rule.name,"matched":False,"conditions":["Rule is outside its effective date window"]}); continue
        matched,detail=evaluate_group(rule.conditions,sample); trace.append({"rule_id":rule.id,"rule":rule.name,"matched":matched,"conditions":detail})
        if matched:
            matched_rules.append(rule.id); final.update(rule.actions or {})
            if rule.stop_processing: break
    queue=None
    if final.get("queue_id"):
        item=db.get(SupportQueue,int(final["queue_id"])); queue=queue_simulation(db,item) if item else None
    return {"matched":bool(matched_rules),"matched_rule_ids":matched_rules,"result":final,"trace":trace,"queue_simulation":queue}
@router.get("/routing-rules/conflicts")
def routing_conflicts(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    rules=db.scalars(select(RoutingRule).where(RoutingRule.active.is_(True),RoutingRule.status=="active").order_by(RoutingRule.priority_order)).all(); conflicts=[]
    for index,left in enumerate(rules):
        for right in rules[index+1:]:
            same_conditions=json.dumps(left.conditions or {},sort_keys=True)==json.dumps(right.conditions or {},sort_keys=True)
            competing=bool(set((left.actions or {})).intersection(right.actions or {}))
            if left.trigger==right.trigger and same_conditions and competing:
                conflicts.append({"first_rule_id":left.id,"first_rule":left.name,"second_rule_id":right.id,"second_rule":right.name,"reason":"Identical trigger and conditions set competing actions","resolved_by_order":left.priority_order!=right.priority_order})
    return {"count":len(conflicts),"conflicts":conflicts}
@router.post("/routing-rules/evaluate")
def evaluate_draft_routing(payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    rule=payload.get("rule") or {}; sample=payload.get("sample") or {}
    matched,detail=evaluate_group(rule.get("conditions") or {"logic":"AND","conditions":[]},sample)
    result=rule.get("actions") or {} if matched else {}
    queue=None
    if matched and result.get("queue_id"):
        item=db.get(SupportQueue,int(result["queue_id"])); queue=queue_simulation(db,item) if item else None
    return {"matched":matched,"result":result,"trace":[{"rule_id":rule.get("id"),"rule":rule.get("name") or "Unsaved rule","matched":matched,"conditions":detail}],"queue_simulation":queue}
@router.post("/routing-rules/{item_id}/duplicate",status_code=201)
def duplicate_routing(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    source=db.get(RoutingRule,item_id)
    if not source: raise HTTPException(404,"Routing rule not found")
    item=RoutingRule(name=f"{source.name} Copy {uuid.uuid4().hex[:4]}",description=source.description,trigger=source.trigger,priority_order=source.priority_order+1,conditions=source.conditions,actions=source.actions,status="draft",active=False,stop_processing=source.stop_processing); db.add(item); db.flush(); audit(db,"routing_rule.duplicated","routing_rule",item.id,user.id,new={"source_id":source.id}); db.commit(); return routing_dict(item)
@router.get("/routing-rules/{item_id}/versions")
def routing_versions(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [{"id":x.id,"version":x.version,"snapshot":x.snapshot,"created_by_id":x.created_by_id,"created_at":x.created_at} for x in db.scalars(select(RoutingRuleVersion).where(RoutingRuleVersion.routing_rule_id==item_id).order_by(RoutingRuleVersion.version.desc())).all()]
@router.post("/routing-rules/{item_id}/rollback/{version_id}")
def rollback_routing(item_id:int,version_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(RoutingRule,item_id); stored=db.get(RoutingRuleVersion,version_id)
    if not item or not stored or stored.routing_rule_id!=item.id: raise HTTPException(404,"Routing rule version not found")
    previous=snapshot_rule(item); snapshot=stored.snapshot or {}
    for key in ("name","description","trigger","priority_order","conditions","actions","status","active","stop_processing","overwrite_existing","reevaluate_fields","effective_from","effective_until"):
        if key in snapshot:
            value=snapshot[key]
            if key in {"effective_from","effective_until"} and isinstance(value,str): value=datetime.fromisoformat(value)
            setattr(item,key,value)
    bump(item); db.add(RoutingRuleVersion(routing_rule_id=item.id,version=item.version,snapshot=snapshot_rule(item),created_by_id=user.id))
    audit(db,"routing_rule.rolled_back","routing_rule",item.id,user.id,previous,{"restored_version":stored.version}); db.commit(); return routing_dict(item)
@router.delete("/routing-rules/{item_id}")
def archive_routing(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(RoutingRule,item_id)
    if not item: raise HTTPException(404,"Routing rule not found")
    item.active=False; item.status="draft"; item.archived_at=now(); bump(item); audit(db,"routing_rule.archived","routing_rule",item.id,user.id); db.commit(); return {"ok":True,"archived":True}


def notification_dict(x:NotificationRule): return {"id":x.id,"name":x.name,"trigger":x.trigger,"classification":x.classification,"conditions":x.conditions or [],"recipients":x.recipients or [],"template":x.template or {},"locale":x.locale,"status":x.status,"rate_limit":x.rate_limit or {},"suppress_actor":x.suppress_actor,"active":x.active,"version":x.version}

# Automation policies are deliberately stored as tenant-scoped configuration rather
# than code switches.  Every policy ships disabled and is therefore safe to stage,
# review, test, and activate independently without changing ticket behaviour.
AUTOMATION_DEFAULTS = {
    "duplicate_detection": {"enabled": False, "lookback_hours": 72, "action": "suggest"},
    "priority_escalation": {"enabled": False, "high_after_hours": 24, "critical_after_hours": 4, "action": "notify_lead"},
    "after_hours_alerts": {"enabled": False, "start": "18:00", "end": "08:00", "recipients": ["on_call"]},
    "unresponsive_tech": {"enabled": False, "after_hours": 8, "action": "notify_lead"},
    "scheduled_maintenance": {"enabled": False, "auto_note": True, "announcement": True},
    "knowledge_base_linking": {"enabled": False, "mode": "suggest"},
    "license_software_expiry": {"enabled": False, "warning_days": 30},
    "satisfaction_surveys": {"enabled": False, "delay_hours": 24},
    "chat_auto_archive": {"enabled": False, "inactivity_days": 30},
    "password_expiry": {
        "enabled": False, "identity_source": "not_configured", "warning_days": 15,
        "login_popup_days": 5, "mandatory_days": 3, "weekend_warning_days": 4,
        "self_service_url": "https://passwordreset.microsoftonline.com/", "it_fallback": True,
    },
    "announcements": {"portal_visible": True, "agent_popup": False, "require_acknowledgement": False},
}

def automation_center_value(db: Session) -> dict:
    item = db.scalar(select(ConfigItem).where(ConfigItem.section == "automation_center", ConfigItem.name == "Policies"))
    stored = (item.value or {}) if item else {}
    return {key: {**value, **(stored.get(key) or {})} for key, value in AUTOMATION_DEFAULTS.items()}

@router.get("/automation-center")
def automation_center(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    return {"policies": automation_center_value(db), "all_disabled": not any(x.get("enabled") for x in automation_center_value(db).values())}

@router.patch("/automation-center")
def update_automation_center(payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    requested=payload.get("policies") or {}
    unknown=set(requested)-set(AUTOMATION_DEFAULTS)
    if unknown: raise HTTPException(422, f"Unknown automation policy: {sorted(unknown)[0]}")
    current=automation_center_value(db)
    for key, values in requested.items():
        if not isinstance(values, dict): raise HTTPException(422, f"{key} must be an object")
        current[key]={**current[key], **values, "enabled": bool(values.get("enabled", current[key].get("enabled", False)))}
    item=db.scalar(select(ConfigItem).where(ConfigItem.section=="automation_center",ConfigItem.name=="Policies"))
    if not item:
        item=ConfigItem(section="automation_center",name="Policies",value=current,description="Independent service-desk automation controls")
        db.add(item); db.flush()
    else: item.value=current
    audit(db,"automation_center.updated","automation_center",item.id,user.id,new={"enabled":[key for key,value in current.items() if value.get("enabled")]})
    db.commit(); return {"policies":current,"all_disabled":not any(x.get("enabled") for x in current.values())}

@router.post("/automation-center/{policy_key}/test")
def test_automation_policy(policy_key:str,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    policies=automation_center_value(db)
    if policy_key not in policies: raise HTTPException(404,"Automation policy not found")
    policy=policies[policy_key]
    ready=policy_key!="password_expiry" or policy.get("identity_source")!="not_configured"
    audit(db,"automation_center.tested","automation_center",None,user.id,new={"policy":policy_key,"ready":ready,"enabled":policy.get("enabled",False)})
    db.commit()
    return {"ok":True,"policy":policy_key,"enabled":policy.get("enabled",False),"ready":ready,
            "message":"Test completed. No production ticket, message, account, or device was changed." if ready else "Password expiry is staged but needs an identity source before it can evaluate users."}

def announcement_dict(x:Announcement): return {"id":x.id,"title":x.title,"body":x.body,"severity":x.severity,"active":x.active,"created_at":x.created_at}
@router.get("/announcements")
def announcements(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [announcement_dict(x) for x in db.scalars(select(Announcement).order_by(Announcement.created_at.desc())).all()]
@router.post("/announcements",status_code=201)
def create_announcement(payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    title=str(payload.get("title") or "").strip(); body=str(payload.get("body") or "").strip(); severity=str(payload.get("severity") or "info")
    if not title or not body: raise HTTPException(422,"Announcement title and message are required")
    if severity not in {"info","warning","critical"}: raise HTTPException(422,"Invalid announcement severity")
    item=Announcement(title=title[:240],body=body,severity=severity,active=bool(payload.get("active",True)));db.add(item);db.flush();audit(db,"announcement.created","announcement",item.id,user.id,new={"title":item.title,"severity":severity,"active":item.active});db.commit();return announcement_dict(item)
@router.patch("/announcements/{item_id}")
def update_announcement(item_id:int,payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(Announcement,item_id)
    if not item: raise HTTPException(404,"Announcement not found")
    if "title" in payload: item.title=str(payload["title"]).strip()[:240]
    if "body" in payload: item.body=str(payload["body"]).strip()
    if "severity" in payload:
        if payload["severity"] not in {"info","warning","critical"}: raise HTTPException(422,"Invalid announcement severity")
        item.severity=payload["severity"]
    if "active" in payload: item.active=bool(payload["active"])
    if not item.title or not item.body: raise HTTPException(422,"Announcement title and message are required")
    audit(db,"announcement.updated","announcement",item.id,user.id,new={"title":item.title,"active":item.active});db.commit();return announcement_dict(item)
def validate_template(template:dict):
    combined=" ".join(str(x) for x in template.values())
    if re.search(r"<\s*(script|iframe|object)|javascript:",combined,re.I): raise HTTPException(422,"Unsafe HTML is not permitted in notification templates")
@router.get("/event-catalog")
def event_catalog(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [{"id":x.id,"key":x.key,"name":x.name,"description":x.description,"category":x.category,"reportable":x.reportable,"custom":x.custom,"active":x.active} for x in db.scalars(select(EventCatalogItem).order_by(EventCatalogItem.category,EventCatalogItem.key)).all()]
@router.get("/events")
def events(event_key:str|None=None,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    stmt=select(DomainEvent)
    if event_key: stmt=stmt.where(DomainEvent.event_key==event_key)
    return [{"id":x.id,"event_key":x.event_key,"aggregate_type":x.aggregate_type,"aggregate_id":x.aggregate_id,"actor_id":x.actor_id,"payload":x.payload,"occurred_at":x.occurred_at} for x in db.scalars(stmt.order_by(DomainEvent.occurred_at.desc()).limit(500)).all()]
@router.get("/notification-rules")
def notifications(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)): return [notification_dict(x) for x in db.scalars(select(NotificationRule).order_by(NotificationRule.trigger,NotificationRule.name)).all()]
@router.get("/notification-settings")
def notification_settings(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    return {"enabled":notification_delivery_enabled(db),"email_enabled":outbound_email_delivery_enabled(db)}
@router.patch("/notification-settings")
def update_notification_settings(payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    enabled=bool(payload.get("enabled",notification_delivery_enabled(db)))
    item=db.scalar(select(ConfigItem).where(ConfigItem.section=="notification_controls",ConfigItem.name=="Global notification delivery"))
    if not item:
        item=ConfigItem(section="notification_controls",name="Global notification delivery",value={"enabled":enabled},description="Master control for all in-app and outbound notifications")
        db.add(item);db.flush()
    else:item.value={**(item.value or {}),"enabled":enabled}
    email_enabled=bool(payload.get("email_enabled",outbound_email_delivery_enabled(db)))
    email_item=db.scalar(select(ConfigItem).where(ConfigItem.section=="notification_controls",ConfigItem.name=="Outbound email delivery"))
    if not email_item:
        email_item=ConfigItem(section="notification_controls",name="Outbound email delivery",value={"enabled":email_enabled},description="Controls outbound email while preserving in-app notifications and inbound email intake")
        db.add(email_item);db.flush()
    else:email_item.value={**(email_item.value or {}),"enabled":email_enabled}
    suppressed=0
    if not enabled or not email_enabled:
        pending=db.scalars(select(Notification).where(Notification.delivery_status=="pending_email")).all()
        for notification in pending:notification.delivery_status="suppressed"
        suppressed=len(pending)
    action="notification.delivery_disabled" if not enabled else "notification.email_enabled" if email_enabled else "notification.email_disabled"
    audit(db,action,"notification_settings",email_item.id,user.id,
          new={"enabled":enabled,"email_enabled":email_enabled,"queued_emails_suppressed":suppressed})
    db.commit();return {"enabled":enabled,"email_enabled":email_enabled,"queued_emails_suppressed":suppressed}
@router.post("/notification-rules/seed-defaults")
def seed_notifications(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    existing=set(db.scalars(select(NotificationRule.trigger)).all()); created=[]
    for trigger,(name,classification,subject,body) in NOTIFICATION_TEMPLATES.items():
        if trigger in existing: continue
        item=NotificationRule(name=name,trigger=trigger,classification=classification,recipients=[{"type":"requester" if classification=="customer" else "assignee","channel":"to"}],template={"subject":subject,"text_body":body,"html_body":""},locale="en",status="draft",active=False,suppress_actor=True); db.add(item); db.flush(); created.append(item.id)
    audit(db,"notification.defaults_seeded","notification_rule",None,user.id,new={"created":len(created)}); db.commit(); return {"created":len(created),"ids":created}
@router.post("/notification-rules",status_code=201)
def create_notification(payload:NotificationRuleIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    validate_template(payload.template); values=payload.model_dump(exclude={"version"}); values["active"]=values["status"]=="active" and values["active"]; item=NotificationRule(**values); db.add(item); db.flush(); audit(db,"notification_rule.created","notification_rule",item.id,user.id,new={"name":item.name,"trigger":item.trigger}); db.commit(); return notification_dict(item)
@router.patch("/notification-rules/{item_id}")
def update_notification(item_id:int,payload:NotificationRuleIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(NotificationRule,item_id)
    if not item: raise HTTPException(404,"Notification rule not found")
    conflict_guard(item,payload.version); validate_template(payload.template)
    for k,v in payload.model_dump(exclude={"version"}).items(): setattr(item,k,v)
    item.active=item.status=="active" and item.active; bump(item); audit(db,"notification_rule.updated","notification_rule",item.id,user.id,new={"name":item.name}); db.commit(); return notification_dict(item)
@router.post("/notification-rules/preview")
def preview_notification(payload:dict,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    template=payload.get("template") or {};validate_template(template);context=notification_context(db,None,str(payload.get("trigger") or "ticket.created"))
    for group,values in (payload.get("context") or {}).items():
        if isinstance(values,dict): context[group]={**context.get(group,{}),**values}
    return {"subject":render_notification_text(template.get("subject", ""),context),"text_body":render_notification_text(template.get("text_body") or template.get("body") or "",context),"html_body":render_notification_text(template.get("html_body", ""),context),"context":context}
@router.post("/notification-rules/{item_id}/test")
def test_notification(item_id:int,payload:dict|None=None,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(NotificationRule,item_id)
    if not item: raise HTTPException(404,"Notification rule not found")
    template=item.template or {};context=notification_context(db,None,item.trigger);title=render_notification_text(template.get("subject") or f"Test: {item.name}",context);body=render_notification_text(template.get("text_body") or template.get("body") or "Notification test",context)
    delivery=(payload or {}).get("delivery","in_app");notify(db,user.id,f"test.{item.trigger}",title[:240],body,email=delivery=="email");audit(db,"notification_rule.tested","notification_rule",item.id,user.id,new={"delivery":delivery,"recipient_email":user.email,"suppressed":not notification_delivery_enabled(db)});db.commit();return {"ok":True,"delivery":delivery,"recipient":user.email,"subject":title,"suppressed":not notification_delivery_enabled(db)}
@router.post("/notification-rules/{item_id}/duplicate",status_code=201)
def duplicate_notification(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    source=db.get(NotificationRule,item_id)
    if not source: raise HTTPException(404,"Notification rule not found")
    item=NotificationRule(name=f"{source.name} Copy {uuid.uuid4().hex[:4]}",trigger=source.trigger,classification=source.classification,conditions=source.conditions,recipients=source.recipients,template=source.template,locale=source.locale,status="draft",active=False,rate_limit=source.rate_limit,suppress_actor=source.suppress_actor); db.add(item); db.flush(); audit(db,"notification_rule.duplicated","notification_rule",item.id,user.id,new={"source_id":source.id}); db.commit(); return notification_dict(item)
@router.delete("/notification-rules/{item_id}")
def archive_notification(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(NotificationRule,item_id)
    if not item: raise HTTPException(404,"Notification rule not found")
    item.active=False; item.archived_at=now(); bump(item); audit(db,"notification_rule.archived","notification_rule",item.id,user.id); db.commit(); return {"ok":True,"archived":True}


def integration_dict(x:IntegrationConnection,db:Session):
    requirements=provider_requirements(x.provider); status=integration_secret_status(db,f"connection:{x.id}") if x.id else {}
    return {"id":x.id,"kind":x.kind,"name":x.name,"provider":x.provider,"enabled":x.enabled,"configuration":x.configuration or {},"status":x.status,"last_attempt_at":x.last_attempt_at,"last_success_at":x.last_success_at,"last_error":x.last_error,"records_processed":x.records_processed,"required_fields":requirements["fields"],"secret_status":{key:bool(status.get(key)) for key in requirements["secrets"]},"version":x.version}
def save_connection_secrets(db:Session,item:IntegrationConnection,payload:IntegrationConnectionIn):
    allowed=set(provider_requirements(item.provider)["secrets"])
    for key,value in payload.secrets.items():
        if key in allowed and value: set_integration_secret(db,f"connection:{item.id}",key,value)
    for key in payload.clear_secrets:
        if key in allowed: clear_integration_secret(db,f"connection:{item.id}",key)
    item.secret_refs={key:f"connection:{item.id}/{key}" for key in allowed}
@router.get("/integration-schemas")
def integration_schemas(user:User=Depends(require_roles(Role.ADMIN))): return {name:value for name,value in sorted(__import__('itsm.admin_services',fromlist=['PROVIDER_SCHEMAS']).PROVIDER_SCHEMAS.items())}


@router.get("/integrations/connect/readiness")
def guided_integration_readiness(user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    microsoft=_provider_application(db,"microsoft"); ringcentral=_provider_application(db,"ringcentral")
    return {
        "microsoft": {
            "ready": bool(microsoft["client_id"] and microsoft["client_secret"]),
            "client_id_configured":bool(microsoft["client_id"]),"credential_configured":bool(microsoft["client_secret"]),
            "callback_url":_connection_callback("Microsoft Entra ID"),
            "message": "Ready for Microsoft administrator consent." if microsoft["client_id"] and microsoft["client_secret"] else "Complete the one-time Northstar Microsoft application setup below.",
            "registration_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
        },
        "ringcentral": {
            "ready": bool(ringcentral["client_id"] and ringcentral["client_secret"]),
            "client_id_configured":bool(ringcentral["client_id"]),"credential_configured":bool(ringcentral["client_secret"]),
            "environment":ringcentral["environment"],"callback_url":_connection_callback("RingCentral"),
            "message": "Ready for RingCentral authorization." if ringcentral["client_id"] and ringcentral["client_secret"] else "Complete the one-time Northstar RingCentral application setup below.",
            "registration_url": "https://developers.ringcentral.com/console/apps",
        },
    }


@router.put("/integrations/connect/registration/{provider_slug}")
def save_provider_application(provider_slug:str,payload:ProviderApplicationRegistrationIn,
                              user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    if provider_slug not in {"microsoft","ringcentral"}: raise HTTPException(404,"Provider registration not found")
    namespace=f"platform:{provider_slug}"
    set_integration_secret(db,namespace,"client_id",payload.client_id.strip())
    if payload.client_secret: set_integration_secret(db,namespace,"client_secret",payload.client_secret)
    if provider_slug=="ringcentral": set_integration_secret(db,namespace,"environment",payload.environment)
    audit(db,"integration.application_registered","integration_application",provider_slug,user.id,
          new={"provider":provider_slug,"credential_updated":bool(payload.client_secret),"environment":payload.environment})
    db.commit()
    application=_provider_application(db,provider_slug)
    return {"ok":True,"ready":bool(application["client_id"] and application["client_secret"]),
            "client_id_configured":bool(application["client_id"]),"credential_configured":bool(application["client_secret"])}


@router.post("/integrations/connect/start")
def start_guided_integration(payload:GuidedIntegrationStartIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    if payload.provider not in GUIDED_PROVIDERS:
        raise HTTPException(422,"This provider does not support guided authorization")
    expected_kind = provider_requirements(payload.provider).get("kind")
    if expected_kind != payload.kind:
        raise HTTPException(422,"Provider does not support this integration type")
    microsoft = payload.provider.startswith("Microsoft")
    application=_provider_application(db,"microsoft" if microsoft else "ringcentral")
    client_id=application["client_id"]
    if not client_id or not application["client_secret"]:
        return {
            "ready": False,
            "provider": payload.provider,
            "message": f"Northstar's {'Microsoft' if microsoft else 'RingCentral'} application must be registered once by the server administrator. Customer tenant IDs, account IDs, and passwords are not required.",
            "registration_url": "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" if microsoft else "https://developers.ringcentral.com/console/apps",
        }
    item = db.scalar(select(IntegrationConnection).where(
        IntegrationConnection.kind==payload.kind,
        IntegrationConnection.provider==payload.provider,
        IntegrationConnection.name==payload.name,
        IntegrationConnection.archived_at.is_(None)))
    if not item:
        item=IntegrationConnection(kind=payload.kind,name=payload.name,provider=payload.provider,
                                   enabled=False,status="Authorization required",configuration=payload.configuration)
        db.add(item); db.flush()
        audit(db,"integration.authorization_started","integration",item.id,user.id,new={"provider":payload.provider})
    else:
        item.configuration={**(item.configuration or {}),**payload.configuration}
        item.status="Authorization required"; item.last_error=""; bump(item)
    state=_oauth_state({"connection_id":item.id,"organization_id":user.organization_id,
                        "actor_id":user.id,"provider":payload.provider})
    redirect_uri=_connection_callback(payload.provider)
    if microsoft:
        authorization_url="https://login.microsoftonline.com/organizations/v2.0/adminconsent?"+urlencode({
            "client_id":client_id,
            "scope":"https://graph.microsoft.com/.default",
            "redirect_uri":redirect_uri,
            "state":state,
        })
    else:
        host="platform.devtest.ringcentral.com" if application["environment"].lower() in {"sandbox","devtest"} else "platform.ringcentral.com"
        authorization_url=f"https://{host}/restapi/oauth/authorize?"+urlencode({
            "client_id":client_id,"response_type":"code","redirect_uri":redirect_uri,"state":state})
    db.add(IntegrationLog(connection_id=item.id,level="info",event="connection.authorization_started",
                          details={"provider":payload.provider,"callback":redirect_uri})); db.commit()
    return {"ready":True,"authorization_url":authorization_url,"connection_id":item.id}


@router.get("/integrations/oauth/callback/{provider_slug}")
def guided_integration_callback(provider_slug:str,request:Request,state:str,error:str|None=None,error_description:str|None=None,
                                admin_consent:str|None=None,tenant:str|None=None,code:str|None=None,
                                db:Session=Depends(get_db)):
    payload=_read_oauth_state(state)
    if payload.get("purpose")=="microsoft_login":
        if provider_slug!="microsoft":
            raise HTTPException(400,"Provider authorization response does not match the requested sign-in")
        from .microsoft_sso import MicrosoftSignInError, complete_microsoft_sign_in
        try:
            return complete_microsoft_sign_in(db,payload,code,error,error_description,request)
        except MicrosoftSignInError as exc:
            db.rollback()
            connections=list(db.scalars(select(IntegrationConnection).where(
                IntegrationConnection.provider=="Microsoft Entra ID",
                IntegrationConnection.enabled.is_(True),
                IntegrationConnection.archived_at.is_(None),
            )).all())
            for connection in connections:
                db.add(IntegrationLog(
                    organization_id=connection.organization_id,
                    connection_id=connection.id,
                    level="error",
                    event="login.microsoft_failed",
                    details={
                        "code":exc.code,
                        "message":str(exc),
                        "source_ip":request.client.host if request.client else None,
                    },
                ))
            if connections:
                db.commit()
            callback=urlsplit(_connection_callback("Microsoft Entra ID"))
            callback_origin=f"{callback.scheme}://{callback.netloc}"
            return RedirectResponse(f"{callback_origin}/?sso=failed&sso_error={quote(exc.code)}#login",status_code=303)
    expected_slug="microsoft" if str(payload.get("provider","")).startswith("Microsoft") else "ringcentral"
    if provider_slug!=expected_slug:
        raise HTTPException(400,"Provider authorization response does not match the requested connection")
    db.info["organization_id"]=int(payload["organization_id"])
    item=db.get(IntegrationConnection,int(payload["connection_id"]))
    if not item or item.provider!=payload["provider"]:
        raise HTTPException(404,"Integration connection not found")
    item.last_attempt_at=now()
    if error:
        item.status="Authorization failed"; item.last_error=error_description or error
        db.add(IntegrationLog(connection_id=item.id,level="error",event="connection.authorization_failed",
                              details={"error":error,"message":error_description or error})); db.commit()
        return RedirectResponse(f"{settings.public_url.rstrip('/')}/?integration=failed#admin",status_code=303)
    if provider_slug=="microsoft":
        if str(admin_consent).lower()!="true" or not tenant:
            raise HTTPException(400,"Microsoft administrator consent was not completed")
        item.configuration={**(item.configuration or {}),"tenant_id":tenant,"authorization":"admin_consent"}
    else:
        if not code:
            raise HTTPException(400,"RingCentral did not return an authorization code")
        application=_provider_application(db,"ringcentral")
        host="platform.devtest.ringcentral.com" if application["environment"].lower() in {"sandbox","devtest"} else "platform.ringcentral.com"
        credentials=base64.b64encode(f"{application['client_id']}:{application['client_secret']}".encode()).decode()
        try:
            response=httpx.post(f"https://{host}/restapi/oauth/token",headers={"Authorization":f"Basic {credentials}"},
                                data={"grant_type":"authorization_code","code":code,
                                      "redirect_uri":_connection_callback(item.provider)},timeout=20)
            response.raise_for_status(); token=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            item.status="Authorization failed"; item.last_error="RingCentral token exchange failed"
            db.add(IntegrationLog(connection_id=item.id,level="error",event="connection.authorization_failed",
                                  details={"message":"RingCentral token exchange failed"})); db.commit()
            raise HTTPException(502,"RingCentral authorization could not be completed") from exc
        for key in ("access_token","refresh_token"):
            if token.get(key): set_integration_secret(db,f"connection:{item.id}",key,token[key])
        item.configuration={**(item.configuration or {}),"authorization":"oauth","token_type":token.get("token_type","Bearer")}
    item.enabled=True; item.status="Connected"; item.last_success_at=now(); item.last_error=""
    db.add(IntegrationLog(connection_id=item.id,level="success",event="connection.authorized",
                          details={"provider":item.provider,"message":"Administrator authorization completed."}))
    audit(db,"integration.authorized","integration",item.id,payload.get("actor_id"),new={"provider":item.provider})
    db.commit()
    return RedirectResponse(f"{settings.public_url.rstrip('/')}/?integration=connected#admin",status_code=303)

@router.get("/integrations")
def integrations(kind:str|None=None,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    stmt=select(IntegrationConnection)
    if kind: stmt=stmt.where(IntegrationConnection.kind==kind)
    return [integration_dict(x,db) for x in db.scalars(stmt.order_by(IntegrationConnection.kind,IntegrationConnection.name)).all()]
@router.post("/integrations",status_code=201)
def create_integration(payload:IntegrationConnectionIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    requirements=provider_requirements(payload.provider)
    if requirements.get("kind") and requirements["kind"]!=payload.kind: raise HTTPException(422,"Provider does not support this integration type")
    values=payload.model_dump(exclude={"secrets","clear_secrets","version"}); item=IntegrationConnection(**values,status="Disabled" if not payload.enabled else "Disconnected"); db.add(item); db.flush(); save_connection_secrets(db,item,payload); audit(db,"integration.created","integration",item.id,user.id,new={"kind":item.kind,"provider":item.provider}); db.commit(); return integration_dict(item,db)
@router.patch("/integrations/{item_id}")
def update_integration(item_id:int,payload:IntegrationConnectionIn,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(IntegrationConnection,item_id)
    if not item: raise HTTPException(404,"Integration not found")
    conflict_guard(item,payload.version); previous={"name":item.name,"provider":item.provider,"enabled":item.enabled,"status":item.status}
    for k,v in payload.model_dump(exclude={"secrets","clear_secrets","version"}).items(): setattr(item,k,v)
    save_connection_secrets(db,item,payload); item.status="Disabled" if not item.enabled else "Configuration required"; bump(item); audit(db,"integration.updated","integration",item.id,user.id,previous,{"name":item.name,"provider":item.provider,"enabled":item.enabled}); db.commit(); return integration_dict(item,db)
@router.post("/integrations/{item_id}/test")
def test_integration(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(IntegrationConnection,item_id)
    if not item: raise HTTPException(404,"Integration not found")
    requirements=provider_requirements(item.provider); missing_fields=[x for x in requirements["fields"] if item.configuration.get(x) in (None,"")]; secrets=integration_secret_status(db,f"connection:{item.id}"); missing_secrets=[x for x in requirements["secrets"] if not secrets.get(x)]
    item.last_attempt_at=now()
    if item.provider in GUIDED_PROVIDERS and item.status != "Connected": item.status="Authorization required"; item.last_error="Use the secure provider sign-in flow to authorize this connection."
    elif not item.enabled: item.status="Disabled"; item.last_error="Integration is disabled"
    elif missing_fields or missing_secrets: item.status="Configuration required"; item.last_error=f"Missing fields: {', '.join(missing_fields) or 'none'}; missing credentials: {', '.join(missing_secrets) or 'none'}"
    elif item.provider == "Microsoft 365":
        try:
            from .microsoft_mail import test_connection as test_microsoft_mail
            result=test_microsoft_mail(db,item); item.status="Connected"; item.last_error=f"Mailbox verified: {result['mailbox']}"
        except Exception as exc:
            item.status="Connection failed"; item.last_error=f"Microsoft Graph mailbox test failed: {str(exc)[:300]}"
    elif item.provider == "RingCentral":
        try:
            from .ringcentral import test_connection as test_ringcentral
            profile=test_ringcentral(db,item); item.status="Connected"; item.last_error=f"RingCentral verified: extension {profile.get('extensionNumber','account owner')}"
        except Exception as exc:
            item.status="Connection failed"; item.last_error=f"RingCentral test failed: {str(exc)[:300]}"
    elif item.provider == "Microsoft Entra ID":
        try:
            from .microsoft_sso import test_microsoft_application
            result=test_microsoft_application(db,item); item.status="Connected"; item.last_error=f"Microsoft identity verified for tenant {result['tenant_id']}. Users are created at first login."
        except Exception as exc:
            item.status="Connection failed"; item.last_error=f"Microsoft identity test failed: {str(exc)[:500]}"
    else: item.status="Ready for provider test"; item.last_error="Configuration is complete. A live provider test requires reachable provider credentials and endpoints."
    level="success" if item.status=="Connected" else "info" if item.status=="Ready for provider test" else "warning"; db.add(IntegrationLog(connection_id=item.id,level=level,event="connection.configuration_test",details={"status":item.status,"message":item.last_error,"missing_fields":missing_fields,"missing_credentials":missing_secrets})); audit(db,"integration.tested","integration",item.id,user.id,new={"status":item.status}); db.commit(); return integration_dict(item,db)
@router.get("/integrations/{item_id}/logs")
def integration_logs(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    if not db.get(IntegrationConnection,item_id): raise HTTPException(404,"Integration not found")
    return [{"id":x.id,"level":x.level,"event":x.event,"details":x.details,"created_at":x.created_at} for x in db.scalars(select(IntegrationLog).where(IntegrationLog.connection_id==item_id).order_by(IntegrationLog.created_at.desc()).limit(200)).all()]
@router.delete("/integrations/{item_id}")
def archive_integration(item_id:int,user:User=Depends(require_roles(Role.ADMIN)),db:Session=Depends(get_db)):
    item=db.get(IntegrationConnection,item_id)
    if not item: raise HTTPException(404,"Integration not found")
    item.enabled=False; item.status="Archived"; item.archived_at=now(); bump(item); audit(db,"integration.archived","integration",item.id,user.id); db.commit(); return {"ok":True,"archived":True}

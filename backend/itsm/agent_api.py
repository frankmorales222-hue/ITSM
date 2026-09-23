"""Secure endpoint-agent enrollment and inventory ingestion.

Endpoint collectors authenticate with a per-device bearer credential. Browser
sessions are deliberately not accepted on ingestion routes, and agents never
write directly to the application database.
"""
import hashlib
import json
import secrets
import base64
import re
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import (AgentEnrollmentToken, Announcement, Asset, AssetHistory, AssetInventorySnapshot,
                     Employee, EndpointAction, EndpointAgent, Notification, Role, Ticket, TicketChatSession, TicketHistory,
                     TicketMessage, TicketStatus, User, now)
from .security import STAFF_ROLES, current_user, get_current_session, require_roles, token_hash
from .services import audit, notify

router = APIRouter(prefix="/api")


def _caddy_root_ca_material(url: str) -> tuple[str, str]:
    """Return the stable local Caddy root CA fingerprint and encoded DER.

    Caddy rotates leaf certificates, so pinning a live leaf would eventually
    stop every endpoint.  The server and Caddy run under the same Windows
    service identity; read the stable private-CA root from that local profile
    and let setup install it into the endpoint's machine trust store.
    """
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return "", ""
    candidates: list[Path] = []
    for variable in ("APPDATA", "PROGRAMDATA"):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / "Caddy" / "pki" / "authorities" / "local" / "root.crt")
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidates.extend([
        system_root / "System32" / "config" / "systemprofile" / "AppData" / "Roaming" / "Caddy" / "pki" / "authorities" / "local" / "root.crt",
        system_root / "ServiceProfiles" / "LocalService" / "AppData" / "Roaming" / "Caddy" / "pki" / "authorities" / "local" / "root.crt",
    ])
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            pem = candidate.read_text(encoding="ascii")
            raw = ssl.PEM_cert_to_DER_cert(pem)
            encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            return hashlib.sha256(raw).hexdigest(), encoded
        except (OSError, UnicodeError, ValueError):
            continue
    raise HTTPException(503, "Northstar could not locate Caddy's local root certificate. Restart the Northstar Caddy service and try again.")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _usable_identity(value: Any) -> str | None:
    text = _normalized_text(value)
    return None if not text or text.lower() in {"unknown", "unavailable", "none", "null"} else text


def _is_computer_account(value: Any) -> bool:
    """Return true for AD computer identities, which must never be users."""
    local_part = _normalized_text(value).split("@", 1)[0].strip()
    return local_part.endswith("$")


def _clean_observed_user_claims(claims: dict | None) -> dict:
    """Keep only usable, person-safe endpoint identity claims.

    Endpoint services run as LocalSystem.  A failed interactive-user lookup can
    therefore yield the computer's AD account (``HOSTNAME$``).  Treat that as
    no observation instead of persisting it as an employee email.
    """
    cleaned = {key: _normalized_text(value) for key, value in (claims or {}).items()
               if _usable_identity(value)}
    for key in ("email", "user_principal_name"):
        if key in cleaned:
            candidate = cleaned[key].lower()
            if _is_computer_account(candidate):
                cleaned.pop(key, None)
            else:
                cleaned[key] = candidate
    if _is_computer_account(cleaned.get("account_name")):
        cleaned.pop("account_name", None)
    # Metadata such as ``source`` is not an identity by itself.  Do not retain
    # it after rejecting a machine account, otherwise callers could mistake
    # the record for a usable employee observation.
    return cleaned if _has_identity_claim(cleaned) else {}


def _has_identity_claim(claims: dict | None) -> bool:
    return any(_usable_identity((claims or {}).get(key)) for key in (
        "email", "user_principal_name", "directory_object_id", "employee_id", "account_name",
    ))


class EnrollmentTokenCreate(BaseModel):
    label: str = Field(default="Windows endpoint enrollment", min_length=2, max_length=120)
    expires_in_hours: int = Field(default=24, ge=1, le=168)
    max_uses: int = Field(default=1, ge=1, le=1000)


class AgentEnrollIn(BaseModel):
    enrollment_token: str = Field(min_length=20, max_length=500)
    device_id: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    hostname: str = Field(min_length=1, max_length=120)
    agent_version: str = Field(default="", max_length=40)
    schema_version: int = Field(default=1, ge=1, le=100)


class AgentHeartbeatIn(BaseModel):
    hostname: str = Field(default="", max_length=120)
    agent_version: str = Field(default="", max_length=40)
    observed_user_email: str | None = Field(default=None, max_length=255)
    observed_user: dict[str, Any] = Field(default_factory=dict)
    last_error: str = Field(default="", max_length=500)


class InventoryIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: int = Field(default=1, ge=1, le=100)
    device_id: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    agent_version: str = Field(default="", max_length=40)
    collected_at: datetime
    observed_user_email: str | None = Field(default=None, max_length=255)
    observed_user: dict[str, Any] = Field(default_factory=dict)
    device: dict[str, Any] = Field(default_factory=dict)
    os: dict[str, Any] = Field(default_factory=dict)
    cpu: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    storage: dict[str, Any] = Field(default_factory=dict)
    gpu: list[dict[str, Any]] = Field(default_factory=list)
    bios: dict[str, Any] = Field(default_factory=dict)
    security: dict[str, Any] = Field(default_factory=dict)
    management: dict[str, Any] = Field(default_factory=dict)
    network: dict[str, Any] = Field(default_factory=dict)
    battery: dict[str, Any] = Field(default_factory=dict)
    peripherals: dict[str, Any] = Field(default_factory=dict)
    software: list[dict[str, Any]] = Field(default_factory=list)
    health: dict[str, Any] = Field(default_factory=dict)


class EndpointActionCreate(BaseModel):
    action_type: str = Field(pattern=r"^(terminate_process|restart_service)$")
    target: str = Field(min_length=1, max_length=160)


class EndpointActionResult(BaseModel):
    succeeded: bool
    summary: str = Field(min_length=1, max_length=500)


class FrozenAppDetection(BaseModel):
    detected_app: str = Field(min_length=1, max_length=160)
    detection_confidence: float | None = Field(default=None, ge=0, le=1)


ENDPOINT_ACTION_MAX_ATTEMPTS = 5
ENDPOINT_ACTION_STALE_SECONDS = 60


_AGENT_INSTALLER_NAME = re.compile(r"NorthstarEndpointAgent-Setup-(\d+)\.(\d+)\.(\d+)\.exe$", re.I)
_AGENT_RELEASE_MAX_BYTES = 150 * 1024 * 1024


def _managed_agent_release_root() -> Path:
    """Server-owned release folder used for administrator-published agent updates."""
    root = Path(settings.data_directory) / "agent-releases"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _latest_installer_in_roots(roots: list[Path]) -> Path | None:
    """Return the newest packaged agent, ignoring stale in-place-upgrade files."""
    matches: list[tuple[tuple[int, int, int], int, Path]] = []
    for priority, root in enumerate(roots):
        if not root.is_dir():
            continue
        for path in root.glob("NorthstarEndpointAgent-Setup-*.exe"):
            parsed = _AGENT_INSTALLER_NAME.fullmatch(path.name)
            if parsed and path.is_file():
                matches.append((tuple(map(int, parsed.groups())), -priority, path))
    return max(matches, default=None, key=lambda item: (item[0], item[1]))[2] if matches else None


def _self_service_installer() -> Path | None:
    managed_root = _managed_agent_release_root()
    packaged_root = Path(sys._MEIPASS) / "agent_installer" if getattr(sys, "_MEIPASS", None) else Path()
    development_root = Path(__file__).resolve().parents[2] / "endpoint_agent" / "artifacts"
    # A release published by an administrator is intentionally preferred when
    # its version is newer. This is the same safe source used by the existing
    # heartbeat update check and self-service installer download.
    return _latest_installer_in_roots([managed_root, packaged_root, development_root])


def _installer_version(path: Path | None) -> tuple[int, int, int] | None:
    """Read the semantic version from a packaged endpoint-agent installer."""
    if not path:
        return None
    match = _AGENT_INSTALLER_NAME.fullmatch(path.name)
    return tuple(map(int, match.groups())) if match else None


def _agent_release_details(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    version = _installer_version(path)
    if not version:
        return None
    return {
        "filename": path.name,
        "version": ".".join(map(str, version)),
        "sha256": _sha256_file(path),
        "published_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "managed": path.parent.resolve() == _managed_agent_release_root().resolve(),
    }


def _agent_alert_severity(event: str, title: str) -> str:
    """Map safe service events to the Windows notification severity."""
    text = f"{event} {title}".lower()
    if any(token in text for token in ("critical", "security", "breach", "urgent")):
        return "critical"
    if any(token in text for token in ("high", "overdue", "warning", "failed", "escalat")):
        return "warning"
    return "information"


def _agent_from_bearer(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> EndpointAgent:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Agent credential required")
    raw = authorization[7:].strip()
    if not raw:
        raise HTTPException(401, "Agent credential required")
    agent = db.scalar(select(EndpointAgent).where(EndpointAgent.credential_hash == token_hash(raw)))
    if not agent or agent.revoked_at is not None:
        raise HTTPException(401, "Agent credential is invalid or revoked")
    db.info["organization_id"] = agent.organization_id
    return agent


def _ticket_agent(db: Session, ticket: Ticket) -> EndpointAgent | None:
    employee = db.get(Employee, ticket.employee_id) if ticket.employee_id else db.scalar(
        select(Employee).where(Employee.user_id == ticket.requester_id)
    )
    conditions = [EndpointAgent.enrolled_by_user_id == ticket.requester_id]
    if employee:
        conditions.extend((EndpointAgent.matched_employee_id == employee.id,
                           EndpointAgent.asset_id.in_(select(Asset.id).where(Asset.assigned_employee_id == employee.id))))
    requester = db.get(User, ticket.requester_id)
    if requester and requester.email:
        conditions.append(func.lower(EndpointAgent.observed_user_email) == requester.email.lower())
    return db.scalar(select(EndpointAgent).where(
        EndpointAgent.revoked_at.is_(None), or_(*conditions)
    ).order_by(EndpointAgent.last_seen_at.desc()))


def _agent_device_summary(db: Session, agent: EndpointAgent | None) -> dict | None:
    """Return the small, non-sensitive device summary shown in a ticket."""
    if not agent:
        return None
    latest = db.scalar(select(AssetInventorySnapshot).where(
        AssetInventorySnapshot.agent_id == agent.id
    ).order_by(AssetInventorySnapshot.received_at.desc()))
    inventory = latest.inventory if latest else {}
    device = inventory.get("device") or {}
    cpu = inventory.get("cpu") or {}
    memory = inventory.get("memory") or {}
    operating_system = inventory.get("os") or {}
    last_boot = operating_system.get("last_boot")
    uptime_seconds = None
    if last_boot:
        try:
            boot_time = datetime.fromisoformat(str(last_boot).replace("Z", "+00:00"))
            if boot_time.tzinfo is None:
                boot_time = boot_time.replace(tzinfo=timezone.utc)
            uptime_seconds = max(0, int((now() - boot_time.astimezone(timezone.utc)).total_seconds()))
        except (TypeError, ValueError):
            pass
    return {
        "hostname": agent.hostname or device.get("hostname") or "This computer",
        "status": agent.status,
        "last_seen_at": agent.last_seen_at,
        "cpu_percent": cpu.get("utilization_percent"),
        "memory_percent": memory.get("percent_used"),
        "operating_system": operating_system.get("edition"),
        "os_version": operating_system.get("version"),
        "last_boot": last_boot,
        "uptime_seconds": uptime_seconds,
    }


def _action_dict(item: EndpointAction) -> dict:
    return {"id": item.id, "ticket_id": item.ticket_id, "agent_id": item.agent_id,
            "action_type": item.action_type, "target": item.target, "status": item.status,
            "requested_by_id": item.requested_by_id, "approved_by_id": item.approved_by_id,
            "approved_at": item.approved_at, "dispatched_at": item.dispatched_at,
            "auto_approved": item.auto_approved, "auto_approved_at": item.auto_approved_at,
            "auto_approval_reason": item.auto_approval_reason, "retry_count": item.retry_count,
            "completed_at": item.completed_at, "result_summary": item.result_summary,
            "created_at": item.created_at}


def _valid_action_target(action_type: str, target: str) -> str:
    value = target.strip()
    pattern = r"^[A-Za-z0-9_. -]{1,120}\.exe$" if action_type == "terminate_process" else r"^[A-Za-z0-9_.-]{1,120}$"
    if not re.fullmatch(pattern, value, re.IGNORECASE):
        label = "executable name ending in .exe" if action_type == "terminate_process" else "Windows service name"
        raise HTTPException(422, f"Enter a valid {label}")
    return value


def _staff_ticket_for_endpoint_action(db: Session, ticket_id: int, user: User) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket or user.role == Role.END_USER or (
        user.id != ticket.assigned_user_id and user.role not in {Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN}
    ):
        raise HTTPException(404, "Ticket not found")
    if ticket.status in {TicketStatus.CLOSED, TicketStatus.CANCELLED}:
        raise HTTPException(409, "Endpoint actions cannot be requested for a closed ticket")
    return ticket


def _pending_action(db: Session, ticket: Ticket, agent: EndpointAgent,
                    action_type: str, target: str) -> EndpointAction | None:
    return db.scalar(select(EndpointAction).where(
        EndpointAction.ticket_id == ticket.id, EndpointAction.agent_id == agent.id,
        EndpointAction.action_type == action_type, func.lower(EndpointAction.target) == target.lower(),
        EndpointAction.status.in_(["Pending approval", "Approved", "Dispatched"])))


def _create_auto_approved_action(db: Session, ticket: Ticket, agent: EndpointAgent, user: User,
                                 target: str, reason: str, confidence: float | None = None) -> EndpointAction:
    if _pending_action(db, ticket, agent, "terminate_process", target):
        raise HTTPException(409, "An action for this application is already pending or executing")
    approved_at = now()
    item = EndpointAction(
        agent_id=agent.id, ticket_id=ticket.id, action_type="terminate_process", target=target,
        requested_by_id=user.id, status="Approved", approved_by_id=user.id, approved_at=approved_at,
        auto_approved=True, auto_approved_at=approved_at, auto_approval_reason=reason,
    )
    db.add(item); db.flush()
    confidence_text = f" Detection confidence: {confidence:.0%}." if confidence is not None else ""
    db.add(TicketMessage(
        ticket_id=ticket.id, author_id=user.id,
        body=(f"[AUTO] {user.display_name} initiated automatic application closure for {target}. "
              f"Reason: frozen application remediation; requester approval was not required.{confidence_text}"),
        kind="internal", source="endpoint_action",
    ))
    db.add(TicketHistory(
        ticket_id=ticket.id, event_type="endpoint_action_auto_approved", actor_id=user.id,
        new_value={"action_id": item.id, "action_type": item.action_type, "target": target,
                   "auto_approved": True, "reason": reason, "confidence": confidence},
    ))
    notify(db, ticket.requester_id, "endpoint.action_auto_approved",
           f"[{ticket.number}] Frozen application remediation started",
           f"IT initiated automatic closure of {target}. This action is recorded in the ticket.", ticket.id)
    audit(db, "endpoint_action.auto_approved", "endpoint_action", item.id, user.id,
          new={"ticket_id": ticket.id, "agent_id": agent.id, "action_type": item.action_type,
               "target": target, "reason": reason, "confidence": confidence})
    return item


def _recover_stale_endpoint_actions(db: Session, actor_id: int | None = None,
                                    agent_id: int | None = None) -> tuple[int, int]:
    stale_threshold = now() - timedelta(seconds=ENDPOINT_ACTION_STALE_SECONDS)
    stale_delivery = or_(
        EndpointAction.status == "Dispatched",
        (EndpointAction.status == "Approved") &
        (EndpointAction.retry_count >= ENDPOINT_ACTION_MAX_ATTEMPTS),
    )
    conditions = [stale_delivery, EndpointAction.dispatched_at.is_not(None),
                  EndpointAction.dispatched_at < stale_threshold]
    if agent_id is not None:
        conditions.append(EndpointAction.agent_id == agent_id)
    stale_actions = db.scalars(select(EndpointAction).where(*conditions).with_for_update()).all()
    recovered = failed = 0
    for item in stale_actions:
        if item.status == "Dispatched" and item.retry_count < ENDPOINT_ACTION_MAX_ATTEMPTS:
            item.status = "Approved"
            item.retry_count += 1
            item.auto_approved_at = item.auto_approved_at or (now() if item.auto_approved else None)
            audit(db, "endpoint_action.stale_retry", "endpoint_action", item.id, actor_id,
                  new={"retry_count": item.retry_count, "ticket_id": item.ticket_id})
            recovered += 1
        else:
            item.status = "Failed"
            item.completed_at = now()
            item.result_summary = (
                f"Action timed out after {item.retry_count} attempts; the endpoint agent may be offline."
            )
            ticket = db.get(Ticket, item.ticket_id)
            if ticket:
                db.add(TicketMessage(ticket_id=ticket.id, author_id=None,
                                     body=f"Endpoint action failed: {item.result_summary}",
                                     kind="internal", source="endpoint_action"))
            audit(db, "endpoint_action.stale_failed", "endpoint_action", item.id, actor_id,
                  new={"retry_count": item.retry_count, "result_summary": item.result_summary})
            failed += 1
    return recovered, failed


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _inventory_hash(data: dict) -> str:
    stable = dict(data)
    stable.pop("collected_at", None)
    return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _meaningful_projection(data: dict) -> dict:
    """Exclude rapidly changing utilization while retaining asset-worthy changes."""
    storage = data.get("storage") or {}
    return {
        "device": data.get("device") or {},
        "os": data.get("os") or {},
        "memory_total_bytes": (data.get("memory") or {}).get("total_bytes"),
        "physical_disks": storage.get("physical_disks", []),
        "bios": data.get("bios") or {},
        "security": data.get("security") or {},
        "management": data.get("management") or {},
        "software": sorted(
            [{"name": item.get("name"), "version": item.get("version")} for item in data.get("software", [])],
            key=lambda item: (str(item.get("name") or "").lower(), str(item.get("version") or "")),
        ),
    }


def _matching_asset(db: Session, agent: EndpointAgent, data: dict) -> Asset | None:
    if agent.asset_id:
        linked = db.get(Asset, agent.asset_id)
        if linked:
            return linked
    device = data.get("device") or {}
    serial = _usable_identity(device.get("serial_number"))
    hostname = _usable_identity(device.get("hostname"))
    serial_match = db.scalar(select(Asset).where(func.lower(Asset.serial_number) == serial.lower())) if serial else None
    host_match = db.scalar(select(Asset).where(func.lower(Asset.hostname) == hostname.lower())) if hostname else None
    if serial_match and host_match and serial_match.id != host_match.id:
        raise HTTPException(409, "Serial number and hostname match different assets; administrator review is required")
    return serial_match or host_match


def _device_type(data: dict) -> str:
    device = data.get("device") or {}
    chassis = _normalized_text(device.get("chassis_type")).lower()
    if any(word in chassis for word in ("laptop", "notebook", "portable")) or (data.get("battery") or {}).get("present") is True:
        return "Laptop"
    return "Computer"


def _first_mac(data: dict) -> str | None:
    for adapter in (data.get("network") or {}).get("adapters", []):
        value = _usable_identity(adapter.get("mac_address"))
        if value and adapter.get("type") not in {"Virtual", "VPN"}:
            return value
    return None


def _upsert_asset(db: Session, agent: EndpointAgent, data: dict) -> tuple[Asset, bool, dict, dict]:
    asset = _matching_asset(db, agent, data)
    device = data.get("device") or {}
    created = asset is None
    if created:
        # This is explicitly a discovery identifier, not an invented business asset tag.
        asset = Asset(
            asset_tag=f"DISC-{agent.device_id[:12].upper()}",
            hostname=_usable_identity(device.get("hostname")),
            serial_number=_usable_identity(device.get("serial_number")),
            manufacturer=_normalized_text(device.get("manufacturer")) or "Unknown",
            model=_normalized_text(device.get("model")) or "Unknown",
            name=_normalized_text(device.get("hostname")),
            category="Computer",
            asset_type=_device_type(data), status="Discovered", condition="Unknown",
            source="EndpointAgent", source_id=agent.id,
        )
        db.add(asset)
        db.flush()
    previous = {
        "hostname": asset.hostname, "serial_number": asset.serial_number,
        "manufacturer": asset.manufacturer, "model": asset.model, "mac_address": asset.mac_address,
    }
    observed = {
        "hostname": _usable_identity(device.get("hostname")),
        "serial_number": _usable_identity(device.get("serial_number")),
        "manufacturer": _usable_identity(device.get("manufacturer")),
        "model": _usable_identity(device.get("model")),
        "mac_address": _first_mac(data),
    }
    # Agent observations own technical facts. Never touch business ownership,
    # location, cost, warranty, lifecycle, or assignment here.
    for field, value in observed.items():
        if value:
            setattr(asset, field, value)
    asset.asset_type = _device_type(data)
    extended = dict(asset.extended_data or {})
    extended["endpoint_agent"] = {
        "agent_id": agent.id, "device_id": agent.device_id, "last_seen_at": now().isoformat(),
        "agent_version": data.get("agent_version") or agent.agent_version,
        "schema_version": data.get("schema_version", 1), "assignment_state": agent.assignment_state,
    }
    asset.extended_data = extended
    agent.asset_id = asset.id
    return asset, created, previous, observed


def _identity_candidates(db: Session, claims: dict) -> tuple[Employee | None, str, int]:
    """Match strongest verified identity first and reject ambiguous claims."""
    employees = db.scalars(select(Employee)).all()
    email_values = {_normalized_text(claims.get("email")).lower(),
                    _normalized_text(claims.get("user_principal_name")).lower()}
    email_values.discard("")
    tiers: list[tuple[str, list[Employee]]] = []
    if email_values:
        tiers.append(("email", [item for item in employees if
            _normalized_text(item.work_email).lower() in email_values or
            any(_normalized_text(alias).lower() in email_values for alias in (item.alternate_emails or []))]))
    object_id = _normalized_text(claims.get("directory_object_id")).lower()
    if object_id:
        tiers.append(("directory_object_id", [item for item in employees
                                               if _normalized_text(item.directory_object_id).lower() == object_id]))
    employee_id = _normalized_text(claims.get("employee_id")).lower()
    if employee_id:
        tiers.append(("employee_id", [item for item in employees
                                      if _normalized_text(item.employee_number).lower() == employee_id]))
    account = _normalized_text(claims.get("account_name")).lower()
    if account and settings.agent_allow_account_name_match:
        tiers.append(("account_name", [item for item in employees
                                       if _normalized_text(item.account_name).lower() == account]))
    for method, matches in tiers:
        unique = {item.id: item for item in matches}
        if len(unique) == 1:
            return next(iter(unique.values())), method, 1
        if len(unique) > 1:
            return None, method, len(unique)
    return None, "", 0


def _reconcile_user(db: Session, agent: EndpointAgent, asset: Asset, observed: str | None,
                    observed_user: dict | None = None) -> dict:
    raw_claims = dict(observed_user or {})
    if observed and not raw_claims.get("email"):
        raw_claims["email"] = observed
    claims = _clean_observed_user_claims(raw_claims)
    old_claims = _clean_observed_user_claims(agent.observed_user or {})
    # A computer account must never erase a previously confirmed human
    # identity.  Preserve the valid observation until the agent reports its
    # next interactive user, while also scrubbing legacy computer-account data.
    if _has_identity_claim(raw_claims) and not _has_identity_claim(claims) and _has_identity_claim(old_claims):
        claims = old_claims
    email = _normalized_text(claims.get("email") or claims.get("user_principal_name")).lower()
    identity_key = email or _normalized_text(claims.get("directory_object_id")).lower() or \
        _normalized_text(claims.get("employee_id")).lower() or _normalized_text(claims.get("account_name")).lower()
    old_identity_key = _normalized_text(old_claims.get("email") or old_claims.get("user_principal_name")).lower() or \
        _normalized_text(old_claims.get("directory_object_id")).lower() or \
        _normalized_text(old_claims.get("employee_id")).lower() or _normalized_text(old_claims.get("account_name")).lower()
    agent.observed_user_email = email or None
    agent.observed_user = claims
    agent.consecutive_user_observations = agent.consecutive_user_observations + 1 if identity_key and identity_key == old_identity_key else (1 if identity_key else 0)
    employee, match_method, match_count = _identity_candidates(db, claims)
    agent.identity_match_method = match_method
    agent.matched_employee_id = employee.id if employee else None
    if not claims:
        state, employee = "No observation", None
    elif match_count > 1:
        state = "Ambiguous identity"
    else:
        if not employee:
            state = "Needs assignment review"
        elif (asset.extended_data or {}).get("assignment_mode") == "shared":
            state = "Shared device"
        elif asset.assigned_employee_id == employee.id:
            state = "Confirmed"
        elif asset.assigned_employee_id is not None:
            state = "Assignment conflict"
        elif agent.consecutive_user_observations >= max(1, settings.agent_assignment_observations):
            asset.assigned_employee_id = employee.id
            if asset.status == "Discovered":
                asset.status = "Active"
            state = "Automatically assigned"
            db.add(AssetHistory(asset_id=asset.id, event_type="agent_assignment", previous_value={"employee_id": None},
                                new_value={"employee_id": employee.id, "email": email, "match_method": match_method}))
        else:
            state = "Pending confirmation"
    agent.assignment_state = state
    return {"state": state, "observed_email": email or None,
            "matched_employee_id": employee.id if employee else None,
            "match_method": match_method or None, "observed_user": claims,
            "observation_count": agent.consecutive_user_observations,
            "required_observations": max(1, settings.agent_assignment_observations)}


@router.post("/agent-admin/enrollment-tokens", status_code=201)
def create_enrollment_token(payload: EnrollmentTokenCreate, user: User = Depends(require_roles(Role.ADMIN)),
                            db: Session = Depends(get_db)):
    raw = secrets.token_urlsafe(48)
    item = AgentEnrollmentToken(token_hash=token_hash(raw), label=payload.label,
                                expires_at=now() + timedelta(hours=payload.expires_in_hours),
                                max_uses=payload.max_uses, created_by_id=user.id)
    db.add(item)
    audit(db, "agent.enrollment_token_created", "agent_enrollment_token", None, user.id,
          new={"label": payload.label, "expires_at": item.expires_at.isoformat(), "max_uses": item.max_uses})
    db.commit()
    return {"id": item.id, "enrollment_token": raw, "expires_at": item.expires_at,
            "max_uses": item.max_uses, "notice": "This token is displayed once. Store it securely."}


@router.get("/agent/self-service/status")
def self_service_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    employee = db.scalar(select(Employee).where(Employee.user_id == user.id))
    conditions = [EndpointAgent.enrolled_by_user_id == user.id,
                  func.lower(EndpointAgent.observed_user_email) == user.email.strip().lower()]
    if employee:
        conditions.append(EndpointAgent.matched_employee_id == employee.id)
    rows = db.scalars(select(EndpointAgent).where(EndpointAgent.revoked_at.is_(None), or_(*conditions))
                      .order_by(EndpointAgent.last_seen_at.desc())).all()
    if not rows:
        # Upgrade compatibility: releases before 0.1.1 did not retain the
        # self-service requester on the endpoint row. A consumed one-use token
        # identifies the one endpoint enrolled during its validity window.
        used_token = db.scalar(select(AgentEnrollmentToken).where(
            AgentEnrollmentToken.created_by_id == user.id,
            AgentEnrollmentToken.label == "Self-service Windows enrollment",
            AgentEnrollmentToken.use_count > 0,
        ).order_by(AgentEnrollmentToken.created_at.desc()))
        if used_token:
            candidates = db.scalars(select(EndpointAgent).where(
                EndpointAgent.revoked_at.is_(None),
                EndpointAgent.enrolled_by_user_id.is_(None),
                EndpointAgent.enrolled_at >= used_token.created_at,
                EndpointAgent.enrolled_at <= used_token.expires_at,
            ).order_by(EndpointAgent.enrolled_at).limit(2)).all()
            if len(candidates) == 1:
                candidate = candidates[0]
                candidate.enrolled_by_user_id = user.id
                db.commit()
                rows = [candidate]
    latest = rows[0] if rows else None
    recent_cutoff = now() - timedelta(days=30)
    reporting = bool(latest and latest.last_seen_at and _aware(latest.last_seen_at) >= recent_cutoff)
    return {"installed": bool(rows), "reporting": reporting, "device_count": len(rows),
            "hostname": latest.hostname if latest else None,
            "status": latest.status if latest else "Not enrolled",
            "last_seen_at": latest.last_seen_at if latest else None,
            "installer_available": _self_service_installer() is not None}


@router.post("/agent/self-service/enrollment", status_code=201)
def create_self_service_enrollment(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Only the most recently generated self-service code remains valid. This
    # limits a copied code to one computer and a short enrollment window.
    active = db.scalars(select(AgentEnrollmentToken).where(
        AgentEnrollmentToken.created_by_id == user.id,
        AgentEnrollmentToken.label == "Self-service Windows enrollment",
        AgentEnrollmentToken.revoked_at.is_(None),
    )).all()
    for previous in active:
        previous.revoked_at = now()
    raw = secrets.token_urlsafe(48)
    item = AgentEnrollmentToken(token_hash=token_hash(raw), label="Self-service Windows enrollment",
                                expires_at=now() + timedelta(minutes=30), max_uses=1,
                                created_by_id=user.id)
    db.add(item)
    public_url = settings.public_url.strip().rstrip("/")
    if not public_url.lower().startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise HTTPException(503, "Self-service agent enrollment requires the public Help Desk URL to use HTTPS")
    encoded_url = base64.urlsafe_b64encode(public_url.encode()).decode().rstrip("=")
    audit(db, "agent.self_service_enrollment_created", "agent_enrollment_token", None, user.id,
          new={"expires_at": item.expires_at.isoformat(), "requested_by": user.email})
    db.commit()
    ca_fingerprint, ca_certificate = _caddy_root_ca_material(public_url)
    code = f"{encoded_url}.{raw}"
    if ca_fingerprint:
        code += f".{ca_fingerprint}.{ca_certificate}"
    return {"enrollment_code": code, "expires_at": item.expires_at,
            "installer_url": "/api/agent/self-service/installer",
            "one_click_url": f"/api/agent/self-service/one-click?code={quote(code, safe='')}"}


@router.get("/agent/self-service/installer")
def download_self_service_installer(request: Request, bootstrap: str | None = None,
                                    db: Session = Depends(get_db)):
    path = _self_service_installer()
    if not path:
        raise HTTPException(503, "The Windows agent installer is not available on this server")
    if bootstrap:
        item = db.scalar(select(AgentEnrollmentToken).where(
            AgentEnrollmentToken.token_hash == token_hash(bootstrap),
            AgentEnrollmentToken.label == "Self-service Windows enrollment",
            AgentEnrollmentToken.revoked_at.is_(None)))
        # Downloads are intentionally repeatable while the short-lived bootstrap
        # code is valid.  The enrollment endpoint remains the single-use gate;
        # rejecting downloads after a failed/partial install strands the user
        # without a way to retry or repair the agent.
        if not item or _aware(item.expires_at) <= now():
            raise HTTPException(401, "Enrollment link expired or already used")
    else:
        # Browser downloads may use the signed-in session. Bootstrap downloads
        # come from curl/PowerShell and deliberately have no browser cookie, so
        # authentication must only be evaluated when no bootstrap code exists.
        get_current_session(request, db)
    return FileResponse(path, media_type="application/vnd.microsoft.portable-executable",
                        filename="NorthstarEndpointAgent-Setup.exe",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/agent/self-service/one-click")
def download_one_click_installer(code: str, request: Request, db: Session = Depends(get_db)):
    """Return a no-code launcher for the authenticated user's one-time enrollment.

    The launcher contains only a short-lived enrollment code and downloads the
    signed agent installer from this server; it never stores credentials.
    """
    parts = code.strip().split('.', 3)
    if len(parts) not in (2, 3, 4) or not parts[1]:
        raise HTTPException(400, "Invalid enrollment link")
    item = db.scalar(select(AgentEnrollmentToken).where(
        AgentEnrollmentToken.token_hash == token_hash(parts[1]),
        AgentEnrollmentToken.label == "Self-service Windows enrollment",
        AgentEnrollmentToken.revoked_at.is_(None)))
    if not item or _aware(item.expires_at) <= now() or item.use_count >= item.max_uses:
        raise HTTPException(401, "Enrollment link expired or already used")
    base = str(request.base_url).rstrip('/')
    exe_url = f"{base}/api/agent/self-service/installer?bootstrap={quote(parts[1], safe='')}"
    installer = _self_service_installer()
    if not installer:
        raise HTTPException(503, "The Windows agent installer is not available on this server")
    expected_sha256 = _sha256_file(installer)
    # The Inno installer receives the code as a parameter and skips code entry.
    script = f'''@echo off
setlocal
set "NS_EXE=%TEMP%\\NorthstarEndpointAgent-Setup.exe"
set "NS_LOG=%LOCALAPPDATA%\\NorthstarEndpointAgent\\installer.log"
echo Northstar Endpoint Agent setup is starting...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $logDir=Split-Path -Parent $env:NS_LOG; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; try {{ Invoke-WebRequest -UseBasicParsing -Uri '{exe_url}' -OutFile $env:NS_EXE }} catch {{ Add-Content -LiteralPath $env:NS_LOG -Value ('Trusted download failed; using the enrollment certificate channel: ' + $_.Exception.Message); curl.exe --fail --location --insecure --output $env:NS_EXE '{exe_url}' }}; if (-not (Test-Path $env:NS_EXE)) {{ throw 'Unable to download the endpoint agent.' }}; $actual=(Get-FileHash -LiteralPath $env:NS_EXE -Algorithm SHA256).Hash.ToLowerInvariant(); if ($actual -ne '{expected_sha256}') {{ Remove-Item -LiteralPath $env:NS_EXE -Force -ErrorAction SilentlyContinue; throw 'The downloaded endpoint installer failed integrity verification.' }}; Add-Content -LiteralPath $env:NS_LOG -Value ('Downloaded and verified installer at ' + (Get-Date -Format o)); $args=@('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG=\"' + $env:NS_LOG + '\"'),('/ENROLLMENTCODE=\"{code}\"')); $setup=Start-Process -FilePath $env:NS_EXE -Verb RunAs -Wait -PassThru -ArgumentList $args; Add-Content -LiteralPath $env:NS_LOG -Value ('Installer exit code: ' + $setup.ExitCode); if ($setup.ExitCode -ne 0) {{ throw ('Endpoint agent setup failed with exit code ' + $setup.ExitCode + '. Log: ' + $env:NS_LOG) }}; $configureError=Join-Path $env:ProgramData 'NorthstarEndpointAgent-install-error.log'; if (Test-Path -LiteralPath $configureError) {{ throw ('Northstar was installed, but enrollment failed. Diagnostic: ' + $configureError) }}; Write-Host 'Northstar Endpoint Agent installed and enrolled successfully.' -ForegroundColor Green"
if errorlevel 1 (
  echo.
  echo Installation failed. Diagnostic log:
  echo %NS_LOG%
  pause
  exit /b 1
)
echo.
echo Installation completed. Northstar Endpoint Agent should now appear in Control Panel and the system tray.
pause
'''
    return PlainTextResponse(script, media_type="text/plain",
                             headers={"Content-Disposition": 'attachment; filename="Install-NorthstarEndpointAgent.cmd"',
                                      "Cache-Control": "private, no-store"})


@router.post("/agent/enroll", status_code=201)
def enroll_agent(payload: AgentEnrollIn, request: Request, db: Session = Depends(get_db)):
    item = db.scalar(select(AgentEnrollmentToken).where(
        AgentEnrollmentToken.token_hash == token_hash(payload.enrollment_token)
    ).with_for_update())
    if not item or item.revoked_at is not None or _aware(item.expires_at) <= now() or item.use_count >= item.max_uses:
        raise HTTPException(401, "Enrollment token is invalid, expired, revoked, or fully used")
    db.info["organization_id"] = item.organization_id
    agent = db.scalar(select(EndpointAgent).where(EndpointAgent.device_id == payload.device_id.lower()))
    credential = secrets.token_urlsafe(64)
    if agent and agent.revoked_at is None:
        raise HTTPException(409, "This endpoint is already enrolled")
    if agent:
        agent.revoked_at = None
        agent.status = "Enrolled"
        agent.credential_hash = token_hash(credential)
    else:
        agent = EndpointAgent(device_id=payload.device_id.lower(), credential_hash=token_hash(credential))
        db.add(agent)
    agent.enrolled_by_user_id = item.created_by_id
    agent.hostname = payload.hostname
    agent.agent_version = payload.agent_version
    agent.schema_version = payload.schema_version
    agent.last_seen_at = now()
    agent.last_ip = _request_ip(request)
    item.use_count += 1
    db.flush()
    audit(db, "agent.enrolled", "endpoint_agent", agent.id, None,
          new={"device_id_suffix": agent.device_id[-8:], "hostname": agent.hostname, "agent_version": agent.agent_version},
          source_ip=agent.last_ip)
    db.commit()
    return {"agent_id": agent.id, "device_id": agent.device_id, "credential": credential,
            "organization_id": agent.organization_id}


@router.get("/tickets/{ticket_id}/endpoint-actions")
def ticket_endpoint_actions(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket or (user.id not in {ticket.requester_id, ticket.assigned_user_id} and user.role not in STAFF_ROLES):
        raise HTTPException(404, "Ticket not found")
    agent = _ticket_agent(db, ticket)
    actions = db.scalars(select(EndpointAction).where(EndpointAction.ticket_id == ticket.id)
                         .order_by(EndpointAction.created_at.desc())).all()
    return {"agent": _agent_device_summary(db, agent),
            "actions": [_action_dict(item) for item in actions]}


@router.get("/endpoint-actions/pending")
def pending_endpoint_actions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Return only remediation requests awaiting this requester's decision."""
    rows = db.execute(
        select(EndpointAction, Ticket)
        .join(Ticket, Ticket.id == EndpointAction.ticket_id)
        .where(Ticket.requester_id == user.id, EndpointAction.status == "Pending approval")
        .order_by(EndpointAction.created_at)
    ).all()
    return [{**_action_dict(action), "ticket_number": ticket.number, "ticket_subject": ticket.subject}
            for action, ticket in rows]


@router.post("/tickets/{ticket_id}/endpoint-actions", status_code=201)
def request_endpoint_action(ticket_id: int, payload: EndpointActionCreate,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    ticket = _staff_ticket_for_endpoint_action(db, ticket_id, user)
    agent = _ticket_agent(db, ticket)
    if not agent:
        raise HTTPException(409, "The requester does not have a reporting endpoint agent")
    target = _valid_action_target(payload.action_type, payload.target)
    if _pending_action(db, ticket, agent, payload.action_type, target):
        raise HTTPException(409, "This endpoint action is already pending")
    item = EndpointAction(agent_id=agent.id, ticket_id=ticket.id, action_type=payload.action_type,
                          target=target, requested_by_id=user.id, status="Pending approval")
    db.add(item); db.flush()
    label = "close application" if payload.action_type == "terminate_process" else "restart service"
    db.add(TicketMessage(ticket_id=ticket.id, author_id=None,
                         body=f"Requester approval is required to {label}: {target}.",
                         kind="public", source="endpoint_action"))
    db.add(TicketHistory(ticket_id=ticket.id, event_type="endpoint_action_requested", actor_id=user.id,
                         new_value={"action_id": item.id, "action_type": payload.action_type, "target": target}))
    notify(db, ticket.requester_id, "endpoint.action_approval",
           f"[{ticket.number}] Approval required for endpoint support",
           f"Your technician requested permission to {label} {target}. Open the ticket to approve or decline.",
           ticket.id, email=True)
    audit(db, "endpoint_action.requested", "endpoint_action", item.id, user.id,
          new={"ticket_id": ticket.id, "agent_id": agent.id, "action_type": payload.action_type, "target": target})
    db.commit(); db.refresh(item)
    return _action_dict(item)


@router.post("/tickets/{ticket_id}/auto-close-application", status_code=201)
def auto_close_application(ticket_id: int, payload: EndpointActionCreate,
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Create a staff-authorized frozen-application closure without requester approval."""
    ticket = _staff_ticket_for_endpoint_action(db, ticket_id, user)
    if payload.action_type != "terminate_process":
        raise HTTPException(422, "Automatic closure supports terminate_process only")
    agent = _ticket_agent(db, ticket)
    if not agent:
        raise HTTPException(409, "The requester does not have a reporting endpoint agent")
    target = _valid_action_target("terminate_process", payload.target)
    item = _create_auto_approved_action(db, ticket, agent, user, target, "frozen_app_auto_close")
    db.commit(); db.refresh(item)
    return _action_dict(item)


@router.post("/tickets/{ticket_id}/auto-detect-and-close", status_code=201)
def auto_detect_and_close_frozen_app(ticket_id: int, payload: FrozenAppDetection,
                                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Record a trusted staff detection and queue a validated application closure."""
    ticket = _staff_ticket_for_endpoint_action(db, ticket_id, user)
    agent = _ticket_agent(db, ticket)
    if not agent:
        raise HTTPException(409, "The requester does not have a reporting endpoint agent")
    target = _valid_action_target("terminate_process", payload.detected_app)
    item = _create_auto_approved_action(
        db, ticket, agent, user, target, "frozen_app_detection", payload.detection_confidence,
    )
    db.commit(); db.refresh(item)
    return {"action": _action_dict(item), "message": "Frozen application closure initiated"}


@router.post("/admin/maintenance/recover-stale-actions")
def recover_stale_actions(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    """Recover legacy actions left in Dispatched or fail them after five attempts."""
    recovered, failed = _recover_stale_endpoint_actions(db, actor_id=user.id)
    db.commit()
    return {"recovered": recovered, "failed": failed}


@router.post("/tickets/{ticket_id}/endpoint-actions/{action_id}/approve")
def approve_endpoint_action(ticket_id: int, action_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id); item = db.get(EndpointAction, action_id)
    if not ticket or not item or item.ticket_id != ticket.id or user.id != ticket.requester_id:
        raise HTTPException(404, "Endpoint action not found")
    if item.status != "Pending approval":
        raise HTTPException(409, "This endpoint action is no longer awaiting approval")
    item.status = "Approved"; item.approved_by_id = user.id; item.approved_at = now()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id,
                         body=f"{user.display_name} approved {item.action_type.replace('_', ' ')} for {item.target}.",
                         kind="public", source="endpoint_action"))
    audit(db, "endpoint_action.approved", "endpoint_action", item.id, user.id,
          new={"ticket_id": ticket.id, "action_type": item.action_type, "target": item.target})
    db.commit(); db.refresh(item)
    return _action_dict(item)


@router.post("/tickets/{ticket_id}/endpoint-actions/{action_id}/decline")
def decline_endpoint_action(ticket_id: int, action_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id); item = db.get(EndpointAction, action_id)
    if not ticket or not item or item.ticket_id != ticket.id or user.id != ticket.requester_id:
        raise HTTPException(404, "Endpoint action not found")
    if item.status != "Pending approval":
        raise HTTPException(409, "This endpoint action is no longer awaiting approval")
    item.status = "Declined"; item.approved_by_id = user.id; item.approved_at = now()
    db.add(TicketMessage(ticket_id=ticket.id, author_id=user.id,
                         body=f"{user.display_name} declined {item.action_type.replace('_', ' ')} for {item.target}.",
                         kind="public", source="endpoint_action"))
    audit(db, "endpoint_action.declined", "endpoint_action", item.id, user.id,
          new={"ticket_id": ticket.id, "action_type": item.action_type, "target": item.target})
    db.commit(); db.refresh(item)
    return _action_dict(item)


@router.get("/agent/actions/next")
def next_endpoint_action(agent: EndpointAgent = Depends(_agent_from_bearer), db: Session = Depends(get_db)):
    # Self-heal actions orphaned by older agents that used Dispatched as a
    # blocking state. New deliveries remain Approved until a result arrives.
    _recover_stale_endpoint_actions(db, agent_id=agent.id)
    item = db.scalar(select(EndpointAction).where(
        EndpointAction.agent_id == agent.id, EndpointAction.status == "Approved",
        EndpointAction.retry_count < ENDPOINT_ACTION_MAX_ATTEMPTS,
    ).order_by(EndpointAction.approved_at).with_for_update(skip_locked=True))
    if not item:
        db.commit()
        return {"action": None}
    item.dispatched_at = now()
    item.retry_count += 1
    audit(db, "endpoint_action.dispatched", "endpoint_action", item.id, None,
          new={"ticket_id": item.ticket_id, "agent_id": agent.id, "action_type": item.action_type,
               "attempt": item.retry_count})
    db.commit(); db.refresh(item)
    return {"action": {"id": item.id, "action_type": item.action_type,
                       "target": item.target, "attempt": item.retry_count}}


@router.post("/agent/actions/{action_id}/result")
def endpoint_action_result(action_id: int, payload: EndpointActionResult,
                           agent: EndpointAgent = Depends(_agent_from_bearer), db: Session = Depends(get_db)):
    item = db.get(EndpointAction, action_id)
    if not item or item.agent_id != agent.id:
        raise HTTPException(404, "Endpoint action not found")
    if item.status in {"Completed", "Failed"}:
        return {"ok": True, "status": item.status, "already_recorded": True}
    if item.status not in {"Approved", "Dispatched"}:
        raise HTTPException(409, "Endpoint action is not ready for a result")
    item.status = "Completed" if payload.succeeded else "Failed"
    item.completed_at = now(); item.result_summary = payload.summary.strip()
    ticket = db.get(Ticket, item.ticket_id)
    if ticket:
        db.add(TicketMessage(ticket_id=ticket.id, author_id=None,
                             body=f"Endpoint action {item.status.lower()}: {item.result_summary}",
                             kind="internal", source="endpoint_action"))
        db.add(TicketHistory(ticket_id=ticket.id, event_type="endpoint_action_completed", actor_id=None,
                             new_value={"action_id": item.id, "status": item.status,
                                        "summary": item.result_summary}))
        notify(db, ticket.assigned_user_id, "endpoint.action_completed",
               f"[{ticket.number}] Endpoint action {item.status.lower()}", item.result_summary, ticket.id)
        notify(db, ticket.requester_id, "endpoint.action_completed",
               f"[{ticket.number}] Endpoint action {item.status.lower()}", item.result_summary, ticket.id)
    audit(db, "endpoint_action.completed", "endpoint_action", item.id, None,
          new={"ticket_id": item.ticket_id, "agent_id": agent.id, "status": item.status,
               "summary": item.result_summary})
    db.commit()
    return {"ok": True}


@router.post("/agent/heartbeat")
def agent_heartbeat(payload: AgentHeartbeatIn, request: Request, agent: EndpointAgent = Depends(_agent_from_bearer),
                    db: Session = Depends(get_db)):
    agent.last_seen_at = now()
    agent.status = "Online"
    agent.last_ip = _request_ip(request)
    agent.last_error = payload.last_error
    if payload.hostname:
        agent.hostname = payload.hostname
    if payload.agent_version:
        agent.agent_version = payload.agent_version
    raw_claims = dict(payload.observed_user or {})
    if payload.observed_user_email and not raw_claims.get("email"):
        raw_claims["email"] = payload.observed_user_email
    claims = _clean_observed_user_claims(raw_claims)
    previous_claims = _clean_observed_user_claims(agent.observed_user or {})
    if _has_identity_claim(claims):
        agent.observed_user = claims
        agent.observed_user_email = _normalized_text(
            claims.get("email") or claims.get("user_principal_name")).lower() or None
    elif _has_identity_claim(raw_claims):
        # Reject an incoming computer account and retain only an already valid
        # person observation.  This prevents HOSTNAME$ identities from leaking
        # into asset lists, ticket context, or tray notification routing.
        agent.observed_user = previous_claims
        agent.observed_user_email = _normalized_text(
            previous_claims.get("email") or previous_claims.get("user_principal_name")).lower() or None
    elif agent.observed_user:
        # Clean legacy records even on a heartbeat that contains no identity.
        agent.observed_user = previous_claims
        agent.observed_user_email = _normalized_text(
            previous_claims.get("email") or previous_claims.get("user_principal_name")).lower() or None
    db.commit()
    email = _normalized_text(agent.observed_user_email).lower()
    recipient = db.scalar(select(User).where(func.lower(User.email) == email)) if email else None
    alerts: list[dict[str, Any]] = []
    if recipient:
        # Notifications are the common event stream for ticket replies, chat,
        # approvals, assignment, and assistance requests.  The tray receives
        # only recent unread events, which avoids the agent polling application
        # pages or retaining ticket conversations locally.
        notifications = db.scalars(select(Notification).where(
            Notification.user_id == recipient.id,
            Notification.read_at.is_(None),
            Notification.created_at >= now() - timedelta(days=7),
        ).order_by(Notification.created_at.desc()).limit(12)).all()
        for item in notifications:
            alerts.append({
                "id": f"notification-{item.id}",
                "kind": "notification",
                "ticket_id": item.ticket_id,
                "severity": _agent_alert_severity(item.event, item.title),
                "title": item.title,
                "body": item.body,
                "created_at": item.created_at.isoformat(),
            })
    # Announcements are broadcast to every installed endpoint, including when
    # the web portal is closed.  They stay separate from user notifications so
    # a service notice never marks an individual's ticket event as read.
    announcements = db.scalars(select(Announcement).where(
        Announcement.active.is_(True),
        Announcement.organization_id == agent.organization_id,
    ).order_by(Announcement.created_at.desc()).limit(8)).all()
    for item in announcements:
        alerts.append({"id": f"announcement-{item.id}", "kind": "announcement",
                       "severity": (item.severity or "information").lower(),
                       "title": item.title, "body": item.body,
                       "created_at": item.created_at.isoformat()})
    alerts.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    installer = _self_service_installer()
    version = _installer_version(installer)
    update = None
    if installer and version:
        update = {"version": ".".join(map(str, version)), "sha256": _sha256_file(installer),
                  "download_path": "/api/agent/update/download"}
    return {"ok": True, "server_time": now(), "alerts": alerts, "agent_update": update}


@router.get("/agent/update/download")
def download_agent_update(agent: EndpointAgent = Depends(_agent_from_bearer)):
    """Serve the current endpoint installer only to an enrolled device."""
    path = _self_service_installer()
    if not path:
        raise HTTPException(503, "The Windows agent installer is not available on this server")
    return FileResponse(path, media_type="application/vnd.microsoft.portable-executable",
                        filename=path.name,
                        headers={"Cache-Control": "private, no-store"})


@router.get("/agent-admin/release")
def get_agent_release(user: User = Depends(require_roles(Role.ADMIN))):
    """Show the installer currently offered to enrolled remote computers."""
    return {
        "active": _agent_release_details(_self_service_installer()),
        "managed_releases": [
            _agent_release_details(path)
            for path in sorted(_managed_agent_release_root().glob("NorthstarEndpointAgent-Setup-*.exe"),
                               key=lambda item: _installer_version(item) or (0, 0, 0), reverse=True)
            if _installer_version(path)
        ],
    }


@router.post("/agent-admin/release", status_code=201)
async def publish_agent_release(installer: UploadFile = File(...), user: User = Depends(require_roles(Role.ADMIN))):
    """Publish one signed Windows agent installer for automatic remote delivery.

    The browser never executes this upload. It is staged on the server and
    every enrolled agent verifies the SHA-256 value before its existing
    unattended updater starts the installer.
    """
    name = Path(installer.filename or "").name
    match = _AGENT_INSTALLER_NAME.fullmatch(name)
    if not match:
        raise HTTPException(422, "Choose a NorthstarEndpointAgent-Setup-x.y.z.exe installer")
    incoming_version = tuple(map(int, match.groups()))
    current_version = _installer_version(_self_service_installer())
    if current_version and incoming_version <= current_version:
        raise HTTPException(409, "Publish an agent version newer than the current release")

    root = _managed_agent_release_root()
    temporary = root / f".{name}.{secrets.token_hex(8)}.upload"
    total = 0
    try:
        with temporary.open("wb") as destination:
            while chunk := await installer.read(1024 * 1024):
                total += len(chunk)
                if total > _AGENT_RELEASE_MAX_BYTES:
                    raise HTTPException(413, "The agent installer exceeds the 150 MB release limit")
                destination.write(chunk)
        if total < 2 or temporary.read_bytes()[:2] != b"MZ":
            raise HTTPException(422, "The uploaded file is not a valid Windows installer")
        target = root / name
        temporary.replace(target)
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(500, "The agent release could not be staged safely") from exc
    finally:
        await installer.close()

    release = _agent_release_details(target)
    return {
        "release": release,
        "message": f"Agent {release['version']} is published. Connected devices will check for it within one minute.",
    }


@router.put("/agent/inventory")
def ingest_inventory(payload: InventoryIn, request: Request, agent: EndpointAgent = Depends(_agent_from_bearer),
                     db: Session = Depends(get_db)):
    if payload.device_id.lower() != agent.device_id:
        raise HTTPException(409, "Inventory device ID does not match this agent credential")
    data = payload.model_dump(mode="json")
    asset, created, previous, observed = _upsert_asset(db, agent, data)
    assignment = _reconcile_user(db, agent, asset, payload.observed_user_email, payload.observed_user)
    latest = db.scalar(select(AssetInventorySnapshot).where(AssetInventorySnapshot.agent_id == agent.id)
                       .order_by(AssetInventorySnapshot.received_at.desc()))
    projection = _meaningful_projection(data)
    prior_projection = _meaningful_projection(latest.inventory) if latest else None
    digest = _inventory_hash(data)
    db.add(AssetInventorySnapshot(asset_id=asset.id, agent_id=agent.id, schema_version=payload.schema_version,
                                  inventory_hash=digest, collected_at=payload.collected_at, inventory=data))
    if created:
        db.add(AssetHistory(asset_id=asset.id, event_type="agent_discovered", new_value=observed))
    elif previous != observed:
        db.add(AssetHistory(asset_id=asset.id, event_type="agent_identity_observed",
                            previous_value=previous, new_value=observed))
    if prior_projection is not None and prior_projection != projection:
        db.add(AssetHistory(asset_id=asset.id, event_type="agent_inventory_change",
                            previous_value=prior_projection, new_value=projection))
    agent.hostname = _normalized_text(payload.device.get("hostname")) or agent.hostname
    agent.agent_version = payload.agent_version or agent.agent_version
    agent.schema_version = payload.schema_version
    agent.last_seen_at = now()
    agent.last_inventory_at = payload.collected_at
    agent.last_ip = _request_ip(request)
    agent.status = "Online"
    extended = dict(asset.extended_data or {})
    extended["endpoint_agent"] = {**extended.get("endpoint_agent", {}),
                                  "last_seen_at": agent.last_seen_at.isoformat(),
                                  "assignment_state": assignment["state"],
                                  "health": payload.health.get("status", "Unknown")}
    asset.extended_data = extended
    db.flush()
    keep = max(1, settings.agent_snapshot_retention)
    old_ids = db.scalars(select(AssetInventorySnapshot.id).where(AssetInventorySnapshot.agent_id == agent.id)
                         .order_by(AssetInventorySnapshot.received_at.desc()).offset(keep)).all()
    if old_ids:
        db.execute(delete(AssetInventorySnapshot).where(AssetInventorySnapshot.id.in_(old_ids)))
    audit(db, "agent.inventory_received", "asset", asset.id, None,
          new={"agent_id": agent.id, "created": created, "assignment_state": assignment["state"],
               "schema_version": payload.schema_version}, source_ip=agent.last_ip)
    db.commit()
    return {"ok": True, "asset_id": asset.id, "asset_tag": asset.asset_tag, "created": created,
            "assignment": assignment, "inventory_hash": digest}


@router.get("/agent-admin/devices")
def list_agents(user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    rows = db.scalars(select(EndpointAgent).order_by(EndpointAgent.last_seen_at.desc())).all()
    return [{"id": item.id, "asset_id": item.asset_id, "device_id_suffix": item.device_id[-8:],
             "hostname": item.hostname, "agent_version": item.agent_version, "schema_version": item.schema_version,
             "status": "Revoked" if item.revoked_at else item.status, "last_seen_at": item.last_seen_at,
             "last_inventory_at": item.last_inventory_at, "observed_user_email": item.observed_user_email,
             "observed_user": item.observed_user, "assignment_state": item.assignment_state,
             "identity_match_method": item.identity_match_method,
             "matched_employee_id": item.matched_employee_id, "last_error": item.last_error} for item in rows]


@router.get("/agent-admin/assignment-review")
def assignment_review(user: User = Depends(require_roles(Role.ADMIN, Role.MANAGER)), db: Session = Depends(get_db)):
    review_states = ("Needs assignment review", "Ambiguous identity", "Assignment conflict", "Pending confirmation")
    rows = db.scalars(select(EndpointAgent).where(EndpointAgent.assignment_state.in_(review_states))
                      .order_by(EndpointAgent.last_seen_at.desc())).all()
    return [{"agent_id": item.id, "asset_id": item.asset_id, "hostname": item.hostname,
             "assignment_state": item.assignment_state, "observed_user": item.observed_user,
             "identity_match_method": item.identity_match_method,
             "matched_employee_id": item.matched_employee_id, "last_seen_at": item.last_seen_at}
            for item in rows]


@router.post("/agent-admin/devices/{agent_id}/revoke")
def revoke_agent(agent_id: int, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    agent = db.get(EndpointAgent, agent_id)
    if not agent:
        raise HTTPException(404, "Endpoint agent not found")
    agent.revoked_at = now()
    agent.status = "Revoked"
    audit(db, "agent.revoked", "endpoint_agent", agent.id, user.id)
    db.commit()
    return {"ok": True}


@router.get("/assets/{asset_id}/endpoint-inventory")
def asset_endpoint_inventory(asset_id: int, user: User = Depends(require_roles(*STAFF_ROLES, Role.AUDITOR)),
                             db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    agent = db.scalar(select(EndpointAgent).where(EndpointAgent.asset_id == asset.id))
    if not agent:
        return {"agent": None, "inventory": None}
    latest = db.scalar(select(AssetInventorySnapshot).where(AssetInventorySnapshot.agent_id == agent.id)
                       .order_by(AssetInventorySnapshot.received_at.desc()))
    return {"agent": {"id": agent.id, "hostname": agent.hostname, "agent_version": agent.agent_version,
                       "status": "Revoked" if agent.revoked_at else agent.status,
                       "last_seen_at": agent.last_seen_at, "last_inventory_at": agent.last_inventory_at,
                       "observed_user_email": agent.observed_user_email, "observed_user": agent.observed_user,
                       "identity_match_method": agent.identity_match_method,
                       "matched_employee_id": agent.matched_employee_id,
                       "assignment_state": agent.assignment_state},
            "inventory": latest.inventory if latest else None}

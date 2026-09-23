"""Administrator API for signed offline application updates."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import __version__
from .config import settings
from .database import get_db
from .database_ops import create_backup
from .models import Role, SystemUpdate, User, now
from .security import require_roles
from .services import audit
from .system_updates import (UpdateValidationError, file_sha256, finalize_staging, launch_installer,
                             public_key_fingerprint, stream_to_staging, verify_package,
                             version_key)

router = APIRouter(prefix="/api/admin/system-updates", tags=["System updates"])


def update_dict(item: SystemUpdate) -> dict:
    return {
        "id": item.id, "package_id": item.package_id, "version": item.version,
        "previous_version": item.previous_version, "filename": item.filename,
        "package_sha256": item.package_sha256, "payload_sha256": item.payload_sha256,
        "release_notes": (item.manifest or {}).get("release_notes", ""),
        "released_at": (item.manifest or {}).get("released_at"), "publisher": (item.manifest or {}).get("publisher", ""),
        "status": item.status, "message": item.message, "backup_path": Path(item.backup_path).name if item.backup_path else "",
        "uploaded_by_id": item.uploaded_by_id, "created_at": item.created_at,
        "installation_started_at": item.installation_started_at, "installed_at": item.installed_at,
    }


def reconcile_installations(db: Session) -> None:
    changed = False
    for item in db.scalars(select(SystemUpdate).where(SystemUpdate.status == "Installing")).all():
        exit_code_file = Path(item.staged_path).parent / "exit-code.txt"
        exit_code = None
        if exit_code_file.is_file():
            try:
                marker = exit_code_file.read_text(encoding="ascii").strip()
            except OSError:
                marker = ""
            if marker:
                try:
                    exit_code = int(marker)
                except ValueError:
                    exit_code = None
        # Older supervised installers could finish successfully while leaving
        # exit-code.txt empty.  The installation log is the authoritative
        # fallback for that handoff so the UI cannot remain stuck at Installing.
        if exit_code is None:
            log_file = exit_code_file.parent / "installation.log"
            try:
                log_text = log_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                log_text = ""
            matches = re.findall(r"Installer exit code:\s*(-?\d+)", log_text)
            if matches:
                try:
                    exit_code = int(matches[-1])
                except ValueError:
                    exit_code = None
        if exit_code is not None:
            if exit_code not in (None, 0):
                item.status = "Failed"
                item.message = f"The installer exited with code {exit_code}. Review the preserved installation log."
                changed = True
                continue
            if exit_code == 0 and bool((item.manifest or {}).get("component_update")):
                item.status = "Installed"
                item.installed_at = now()
                item.message = "Component update installed. Northstar Desk and HTTPS remained online."
                changed = True
                continue
        if version_key(__version__) >= version_key(item.version):
            item.status = "Installed"
            item.installed_at = now()
            item.message = "Update installed and application restarted successfully."
            changed = True
        elif item.installation_started_at and now() - item.installation_started_at > timedelta(minutes=30):
            item.status = "Failed"
            item.message = "The application restarted without the expected version. Review the installation log."
            changed = True
    if changed:
        db.commit()


@router.get("")
def list_updates(user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    reconcile_installations(db)
    configured = bool((settings.update_public_key or "").strip())
    fingerprint = ""
    configuration_error = ""
    if configured:
        try:
            fingerprint = public_key_fingerprint(settings.update_public_key)
        except UpdateValidationError as exc:
            configured = False
            configuration_error = str(exc)
    rows = db.scalars(select(SystemUpdate).order_by(SystemUpdate.created_at.desc())).all()
    return {"current_version": __version__, "verification_configured": configured,
            "verification_key_fingerprint": fingerprint, "configuration_error": configuration_error,
            "updates": [update_dict(item) for item in rows]}


@router.post("/upload", status_code=201)
def upload_update(package: UploadFile = File(...), user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    temporary = None
    try:
        temporary, package_sha = stream_to_staging(package.file, package.filename or "")
        manifest = verify_package(temporary, settings.update_public_key)
        if db.scalar(select(SystemUpdate).where((SystemUpdate.version == manifest["version"]) |
                                                (SystemUpdate.package_id == str(manifest["package_id"])))):
            raise UpdateValidationError("This version or package has already been uploaded.")
        package_path, _ = finalize_staging(temporary, manifest)
        temporary = None
        item = SystemUpdate(package_id=str(manifest["package_id"]), version=manifest["version"],
                            previous_version=__version__, filename=package.filename or package_path.name,
                            package_sha256=package_sha, payload_sha256=manifest["payload_sha256"],
                            manifest=manifest, status="Validated", message="Signature, version, and payload integrity verified.",
                            staged_path=str(package_path), uploaded_by_id=user.id)
        db.add(item); db.flush()
        audit(db, "system_update.validated", "system_update", item.id, user.id,
              new={"version": item.version, "package_id": item.package_id, "sha256": package_sha})
        db.commit(); db.refresh(item)
        return update_dict(item)
    except UpdateValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This update version has already been recorded.") from exc
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        package.file.close()


@router.post("/{update_id}/install", status_code=202)
def install_update(update_id: int, payload: dict, user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    item = db.get(SystemUpdate, update_id)
    if not item:
        raise HTTPException(404, "Update not found")
    if payload.get("confirm_version") != item.version:
        raise HTTPException(400, f"Enter version {item.version} to confirm this maintenance operation.")
    if item.status not in {"Validated", "Failed"}:
        raise HTTPException(409, f"This update is already {item.status.lower()}.")
    if version_key(item.version) <= version_key(__version__):
        raise HTTPException(409, "Older or already-installed versions cannot be installed.")
    package_path = Path(item.staged_path)
    try:
        manifest = verify_package(package_path, settings.update_public_key)
        if (manifest["version"] != item.version or str(manifest["package_id"]) != item.package_id or
                manifest["payload_sha256"] != item.payload_sha256 or file_sha256(package_path) != item.package_sha256):
            raise UpdateValidationError("The staged update no longer matches its validated version-history record.")
        payload_path = package_path.parent / manifest["payload"]
        if file_sha256(payload_path) != item.payload_sha256:
            raise UpdateValidationError("The staged installer changed after validation.")
        component_update = bool(manifest.get("component_update"))
        backup = create_backup(settings.database_url, Path(settings.backup_directory))
        item.status = "Installing"; item.installation_started_at = now(); item.backup_path = str(backup)
        item.message = (
            "Verified backup created. The component will be installed while Northstar Desk remains online."
            if component_update else
            "Verified backup created. The server will restart to install the update."
        )
        audit(db, "system_update.installation_started", "system_update", item.id, user.id,
              new={"version": item.version, "backup": backup.name})
        db.commit()
        launch_installer(payload_path, item.id, component_update=component_update)
        return {"ok": True, "message": (
            "Installation scheduled. Northstar Desk will remain online."
            if component_update else "Installation scheduled. Northstar Desk will restart automatically."
        )}
    except (UpdateValidationError, RuntimeError) as exc:
        item.status = "Failed"; item.message = str(exc); db.commit()
        raise HTTPException(409, str(exc)) from exc

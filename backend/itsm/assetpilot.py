"""One-way, idempotent migration from AssetPilot into Northstar Desk."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Asset, AssetHistory, Department, Employee, Location, User


ASSET_CORE_COLUMNS = {
    "AssetId", "AssetTag", "Hostname", "SerialNumber", "Name", "Status", "Condition",
    "Category", "AssetType", "Manufacturer", "Model", "Department", "Location", "Vendor",
    "Purpose", "Company", "Project", "MacAddress", "SourceReference", "PurchaseDate",
    "PurchaseCostCents", "WarrantyExpiration", "IsArchived", "Remarks",
}


def default_assetpilot_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "AssetPilot" / "Data" / "assetpilot.db"


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"AssetPilot database was not found at {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def assetpilot_preview(path: Path | None = None) -> dict:
    source = path or default_assetpilot_path()
    connection = _connect(source)
    try:
        counts = {}
        for table in ("Assets", "Employees", "AssetAssignments", "AssetStatusHistory", "AssetNetworkAddresses"):
            try:
                counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = 0
    finally:
        connection.close()
    return {"source": str(source), "counts": counts}


def _text(value) -> str | None:
    result = str(value).strip() if value is not None else ""
    return result or None


def _date(value) -> date | None:
    value = _text(value)
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _datetime(value) -> datetime | None:
    value = _text(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _split_name(display_name: str) -> tuple[str, str]:
    name = display_name.strip()
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        return first or name, last or ""
    parts = name.split()
    return (parts[0], " ".join(parts[1:])) if len(parts) > 1 else (name, "")


def import_assetpilot(db: Session, path: Path | None = None, actor_id: int | None = None) -> dict:
    source_path = path or default_assetpilot_path()
    connection = _connect(source_path)
    try:
        source_employees = connection.execute('SELECT * FROM "Employees" ORDER BY "EmployeeId"').fetchall()
        source_assets = connection.execute('SELECT * FROM "Assets" ORDER BY "AssetId"').fetchall()
        source_assignments = connection.execute('SELECT * FROM "AssetAssignments" ORDER BY "AssignedUtc"').fetchall()
        source_status = connection.execute('SELECT * FROM "AssetStatusHistory" ORDER BY "ChangedUtc"').fetchall()
        source_addresses = connection.execute('SELECT * FROM "AssetNetworkAddresses" ORDER BY "AssetNetworkAddressId"').fetchall()
    finally:
        connection.close()

    departments = {item.name.casefold(): item for item in db.scalars(select(Department)).all()}
    locations = {item.name.casefold(): item for item in db.scalars(select(Location)).all()}

    def department_id(name):
        value = _text(name)
        if not value:
            return None
        item = departments.get(value.casefold())
        if not item:
            item = Department(name=value); db.add(item); db.flush(); departments[value.casefold()] = item
        return item.id

    def location_id(name):
        value = _text(name)
        if not value:
            return None
        item = locations.get(value.casefold())
        if not item:
            item = Location(name=value); db.add(item); db.flush(); locations[value.casefold()] = item
        return item.id

    employees_by_number = {item.employee_number.casefold(): item for item in db.scalars(select(Employee)).all()}
    employees_by_email = {item.work_email.casefold(): item for item in db.scalars(select(Employee)).all()}
    users_by_email = {item.email.casefold(): item for item in db.scalars(select(User)).all()}
    employee_source_ids: dict[int, int] = {}
    employee_created = employee_updated = 0
    for row in source_employees:
        number = _text(row["EmployeeNumber"]) or f"ASSETPILOT-{row['EmployeeId']}"
        email = (_text(row["Email"]) or f"assetpilot-{row['EmployeeId']}@invalid.local").lower()
        employee = employees_by_number.get(number.casefold()) or employees_by_email.get(email.casefold())
        first_name, last_name = _split_name(_text(row["DisplayName"]) or number)
        values = {
            "employee_number": number, "first_name": first_name, "last_name": last_name,
            "preferred_name": first_name, "work_email": email,
            "department_id": department_id(row["Department"]), "location_id": location_id(row["Location"]),
            "employment_status": "Active" if row["IsActive"] and not row["IsDeleted"] else "Inactive",
            "source": "AssetPilot",
        }
        if not employee:
            employee = Employee(**values); db.add(employee); db.flush(); employee_created += 1
            employees_by_number[number.casefold()] = employee; employees_by_email[email.casefold()] = employee
        else:
            for key, value in values.items():
                if value is not None and (getattr(employee, key) in (None, "") or employee.source == "AssetPilot"):
                    setattr(employee, key, value)
            employee_updated += 1
        user = users_by_email.get(email.casefold())
        if user and employee.user_id is None:
            employee.user_id = user.id
        employee_source_ids[row["EmployeeId"]] = employee.id
    db.flush()

    active_assignments = {}
    for row in source_assignments:
        if row["ReturnedUtc"] is None:
            active_assignments[row["AssetId"]] = row
    addresses: dict[int, list[dict]] = {}
    for row in source_addresses:
        addresses.setdefault(row["AssetId"], []).append({
            "type": row["AddressType"], "address": row["Address"], "primary": bool(row["IsPrimary"]),
            "notes": row["Notes"],
        })

    existing_assets = db.scalars(select(Asset)).all()
    by_source = {(item.source, item.source_id): item for item in existing_assets if item.source_id is not None}
    by_tag = {item.asset_tag.casefold(): item for item in existing_assets}
    by_hostname = {item.hostname.casefold(): item for item in existing_assets if item.hostname}
    by_serial = {item.serial_number.casefold(): item for item in existing_assets if item.serial_number}
    asset_source_ids: dict[int, int] = {}
    asset_created = asset_updated = 0
    for row in source_assets:
        source_id = row["AssetId"]
        tag = _text(row["AssetTag"]) or f"ASSETPILOT-{source_id}"
        hostname, serial = _text(row["Hostname"]), _text(row["SerialNumber"])
        asset = (by_source.get(("AssetPilot", source_id)) or by_tag.get(tag.casefold()) or
                 (by_hostname.get(hostname.casefold()) if hostname else None) or
                 (by_serial.get(serial.casefold()) if serial else None))
        assignment = active_assignments.get(source_id)
        assigned_employee_id = employee_source_ids.get(assignment["EmployeeId"]) if assignment else None
        extended = {key: row[key] for key in row.keys() if key not in ASSET_CORE_COLUMNS and row[key] not in (None, "")}
        if addresses.get(source_id):
            extended["network_addresses"] = addresses[source_id]
        values = {
            "asset_tag": tag, "hostname": hostname, "serial_number": serial,
            "name": _text(row["Name"]) or tag, "manufacturer": _text(row["Manufacturer"]) or "",
            "model": _text(row["Model"]) or "", "category": _text(row["Category"]) or "Computer",
            "asset_type": _text(row["AssetType"]) or "Other", "status": _text(row["Status"]) or "Active",
            "condition": _text(row["Condition"]) or "Good", "department_id": department_id(row["Department"]),
            "location_id": location_id(row["Location"]), "assigned_employee_id": assigned_employee_id,
            "vendor": _text(row["Vendor"]), "purpose": _text(row["Purpose"]), "company": _text(row["Company"]),
            "project": _text(row["Project"]), "mac_address": _text(row["MacAddress"]),
            "source_reference": _text(row["SourceReference"]), "purchase_date": _date(row["PurchaseDate"]),
            "purchase_cost_cents": row["PurchaseCostCents"], "warranty_expiration": _date(row["WarrantyExpiration"]),
            "is_archived": bool(row["IsArchived"]), "notes": _text(row["Remarks"]) or "",
            "source": "AssetPilot", "source_id": source_id, "extended_data": extended,
        }
        if not asset:
            asset = Asset(**values); db.add(asset); db.flush(); asset_created += 1
        else:
            for key, value in values.items():
                setattr(asset, key, value)
            asset_updated += 1
        by_source[("AssetPilot", source_id)] = asset; by_tag[tag.casefold()] = asset
        if hostname: by_hostname[hostname.casefold()] = asset
        if serial: by_serial[serial.casefold()] = asset
        asset_source_ids[source_id] = asset.id
    db.flush()

    imported_events = set()
    for history in db.scalars(select(AssetHistory).where(AssetHistory.event_type.in_(["assetpilot_assignment", "assetpilot_status"]))).all():
        value = history.new_value or {}
        imported_events.add((history.event_type, value.get("assetpilot_id")))
    history_created = 0
    for row in source_assignments:
        key = ("assetpilot_assignment", row["AssetAssignmentId"])
        if key in imported_events or row["AssetId"] not in asset_source_ids:
            continue
        db.add(AssetHistory(asset_id=asset_source_ids[row["AssetId"]], event_type=key[0], actor_id=actor_id,
                            created_at=_datetime(row["AssignedUtc"]) or datetime.now(),
                            new_value={"assetpilot_id": key[1], "employee_id": employee_source_ids.get(row["EmployeeId"]),
                                       "assigned_location": row["AssignedLocation"], "notes": row["Notes"],
                                       "returned_at": row["ReturnedUtc"], "return_condition": row["ReturnCondition"],
                                       "return_notes": row["ReturnNotes"]}))
        history_created += 1
    for row in source_status:
        key = ("assetpilot_status", row["AssetStatusHistoryId"])
        if key in imported_events or row["AssetId"] not in asset_source_ids:
            continue
        db.add(AssetHistory(asset_id=asset_source_ids[row["AssetId"]], event_type=key[0], actor_id=actor_id,
                            created_at=_datetime(row["ChangedUtc"]) or datetime.now(),
                            previous_value={"status": row["FromStatus"]},
                            new_value={"assetpilot_id": key[1], "status": row["ToStatus"], "reason": row["Reason"]}))
        history_created += 1
    return {"source": str(source_path), "employees_created": employee_created, "employees_updated": employee_updated,
            "assets_created": asset_created, "assets_updated": asset_updated, "history_created": history_created}

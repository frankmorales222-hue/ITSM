import sqlite3
from pathlib import Path

from sqlalchemy import func, select

from itsm.assetpilot import assetpilot_preview, import_assetpilot
from itsm.database import SessionLocal
from itsm.models import Asset, AssetHistory, Employee


def make_assetpilot(path: Path):
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE Employees (EmployeeId INTEGER, EmployeeNumber TEXT, DisplayName TEXT, Email TEXT,
          Department TEXT, Location TEXT, IsActive INTEGER, IsDeleted INTEGER);
        CREATE TABLE Assets (AssetId INTEGER, AssetTag TEXT, Hostname TEXT, SerialNumber TEXT, Name TEXT,
          Manufacturer TEXT, Model TEXT, Category TEXT, AssetType TEXT, Status TEXT, Condition TEXT,
          Department TEXT, Location TEXT, Vendor TEXT, Purpose TEXT, Company TEXT, Project TEXT,
          MacAddress TEXT, SourceReference TEXT, PurchaseDate TEXT, PurchaseCostCents INTEGER,
          WarrantyExpiration TEXT, IsArchived INTEGER, Remarks TEXT, OfficeWorkMode TEXT);
        CREATE TABLE AssetAssignments (AssetAssignmentId INTEGER, AssetId INTEGER, EmployeeId INTEGER,
          AssignedUtc TEXT, AssignedByUserId TEXT, AssignedLocation TEXT, Notes TEXT, ReturnedUtc TEXT,
          ReturnedByUserId TEXT, ReturnCondition TEXT, ReturnNotes TEXT);
        CREATE TABLE AssetStatusHistory (AssetStatusHistoryId INTEGER, AssetId INTEGER, FromStatus TEXT,
          ToStatus TEXT, ChangedUtc TEXT, ChangedByUserId TEXT, Reason TEXT);
        CREATE TABLE AssetNetworkAddresses (AssetNetworkAddressId INTEGER, AssetId INTEGER,
          AddressType TEXT, Address TEXT, IsPrimary INTEGER, Notes TEXT);
        INSERT INTO Employees VALUES (7,'AP-100','Jamie Asset','jamie.asset@example.test','Operations','Warehouse',1,0);
        INSERT INTO Assets VALUES (11,'AP-LT-001','AP-HOST-001','AP-SERIAL-001','Warehouse laptop','Dell',
          'Latitude','Computer','Laptop','Active','Good','Operations','Warehouse','Example Vendor',
          'Field work','Example Co','Migration','AA-BB-CC-DD-EE-FF','Legacy-11','2025-01-02',125000,
          '2028-01-02',0,'Imported notes','Hybrid');
        INSERT INTO AssetAssignments VALUES (21,11,7,'2026-01-01T10:00:00+00:00','admin','Warehouse','Issued',NULL,NULL,NULL,NULL);
        INSERT INTO AssetStatusHistory VALUES (31,11,'Stock','Active','2026-01-01T10:00:00+00:00','admin','Assigned');
        INSERT INTO AssetNetworkAddresses VALUES (41,11,'MAC','AA-BB-CC-DD-EE-FF',1,'Primary adapter');
        """)


def test_assetpilot_import_is_complete_and_idempotent():
    source = Path("data/test_assetpilot_source.db"); source.unlink(missing_ok=True); make_assetpilot(source)
    try:
        assert assetpilot_preview(source)["counts"]["Assets"] == 1
        with SessionLocal() as db:
            first = import_assetpilot(db, source); db.commit()
            asset = db.scalar(select(Asset).where(Asset.asset_tag == "AP-LT-001"))
            employee = db.scalar(select(Employee).where(Employee.employee_number == "AP-100"))
            assert first["assets_created"] == 1 and first["employees_created"] == 1
            assert asset.assigned_employee_id == employee.id
            assert asset.extended_data["OfficeWorkMode"] == "Hybrid"
            assert asset.extended_data["network_addresses"][0]["address"] == "AA-BB-CC-DD-EE-FF"
            history_count = db.scalar(select(func.count(AssetHistory.id)).where(AssetHistory.asset_id == asset.id))
            second = import_assetpilot(db, source); db.commit()
            assert second["assets_created"] == 0 and second["assets_updated"] == 1
            assert db.scalar(select(func.count(Asset.id)).where(Asset.asset_tag == "AP-LT-001")) == 1
            assert db.scalar(select(func.count(AssetHistory.id)).where(AssetHistory.asset_id == asset.id)) == history_count
    finally:
        source.unlink(missing_ok=True)

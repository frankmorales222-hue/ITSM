import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "backend"))

from itsm.assetpilot import default_assetpilot_path, import_assetpilot
from itsm.database import SessionLocal
from itsm.models import Role, User
from itsm.services import audit
from sqlalchemy import select


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import AssetPilot into the ITSM Asset Inventory")
    parser.add_argument("--source", type=Path, default=default_assetpilot_path())
    args = parser.parse_args()
    with SessionLocal() as db:
        administrator = db.scalar(select(User).where(User.role == Role.ADMIN).order_by(User.id))
        result = import_assetpilot(db, args.source, administrator.id if administrator else None)
        audit(db, "assetpilot.imported", "inventory", None, administrator.id if administrator else None, new=result)
        db.commit()
    print(result)

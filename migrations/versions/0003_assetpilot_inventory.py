"""Expand the native inventory for AssetPilot records and workflows."""
from alembic import op
import sqlalchemy as sa

revision = "0003_assetpilot_inventory"
down_revision = "0002_config_items"
branch_labels = None
depends_on = None


COLUMNS = {
    "name": sa.Column("name", sa.String(160), nullable=False, server_default=""),
    "category": sa.Column("category", sa.String(80), nullable=False, server_default="Computer"),
    "purchase_cost_cents": sa.Column("purchase_cost_cents", sa.Integer(), nullable=True),
    "vendor": sa.Column("vendor", sa.String(120), nullable=True),
    "purpose": sa.Column("purpose", sa.String(160), nullable=True),
    "company": sa.Column("company", sa.String(120), nullable=True),
    "project": sa.Column("project", sa.String(120), nullable=True),
    "mac_address": sa.Column("mac_address", sa.String(80), nullable=True),
    "source_reference": sa.Column("source_reference", sa.String(240), nullable=True),
    "source": sa.Column("source", sa.String(40), nullable=False, server_default="Manual"),
    "source_id": sa.Column("source_id", sa.Integer(), nullable=True),
    "is_archived": sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    "extended_data": sa.Column("extended_data", sa.JSON(), nullable=False, server_default="{}"),
}


def upgrade():
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns("assets")}
    missing = [column for name, column in COLUMNS.items() if name not in existing]
    if missing:
        with op.batch_alter_table("assets") as batch:
            for column in missing:
                batch.add_column(column)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("assets")}
    if "organization_id" not in existing and "uq_assets_source_source_id" not in indexes:
        op.create_index("uq_assets_source_source_id", "assets", ["source", "source_id"], unique=True,
                        sqlite_where=sa.text("source_id IS NOT NULL"))


def downgrade():
    bind = op.get_bind()
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("assets")}
    if "uq_assets_source_source_id" in indexes:
        op.drop_index("uq_assets_source_source_id", table_name="assets")
    existing = {column["name"] for column in sa.inspect(bind).get_columns("assets")}
    with op.batch_alter_table("assets") as batch:
        for name in reversed(list(COLUMNS)):
            if name in existing:
                batch.drop_column(name)

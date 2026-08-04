"""Remove the pre-organization AssetPilot source index."""

from alembic import op
import sqlalchemy as sa


revision = "0006_remove_legacy_asset_source_index"
down_revision = "0005_studio_approvals_reports"
branch_labels = None
depends_on = None


def upgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("assets")}
    if "uq_assets_source_source_id" in indexes:
        op.drop_index("uq_assets_source_source_id", table_name="assets")


def downgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("assets")}
    if "uq_assets_source_source_id" not in indexes:
        op.create_index("uq_assets_source_source_id", "assets", ["source", "source_id"], unique=True,
                        sqlite_where=sa.text("source_id IS NOT NULL"))

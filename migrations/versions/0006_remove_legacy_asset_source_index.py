"""Remove the pre-organization AssetPilot source index."""

from alembic import op
import sqlalchemy as sa


revision = "0006_remove_legacy_asset_source_index"
down_revision = "0005_studio_approvals_reports"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Alembic creates version_num as VARCHAR(32).  This is the first revision
    # whose identifier exceeds that limit, so widen the tracking column before
    # Alembic records this revision.  Keeping this here also repairs databases
    # left at revision 0005 by an earlier failed installer.
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("assets")}
    if "uq_assets_source_source_id" in indexes:
        op.drop_index("uq_assets_source_source_id", table_name="assets")


def downgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("assets")}
    if "uq_assets_source_source_id" not in indexes:
        op.create_index("uq_assets_source_source_id", "assets", ["source", "source_id"], unique=True,
                        sqlite_where=sa.text("source_id IS NOT NULL"))

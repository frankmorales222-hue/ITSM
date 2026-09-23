"""Add signed offline system update history.

Revision ID: 0020_signed_system_updates
Revises: 0019_endpoint_enrollment_owner
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_signed_system_updates"
down_revision = "0019_endpoint_enrollment_owner"
branch_labels = None
depends_on = None


def upgrade():
    # The historical initial migration creates current metadata on a brand-new
    # evaluation database. Existing installations at 0019 do not have this
    # table, so create it only when it is actually absent.
    if "system_updates" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "system_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("previous_version", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("package_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="Validated"),
        sa.Column("message", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("staged_path", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("backup_path", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("installation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("package_id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index("ix_system_updates_package_id", "system_updates", ["package_id"])
    op.create_index("ix_system_updates_version", "system_updates", ["version"])
    op.create_index("ix_system_updates_status", "system_updates", ["status"])
    op.create_index("ix_system_updates_uploaded_by_id", "system_updates", ["uploaded_by_id"])
    op.create_index("ix_system_updates_created_at", "system_updates", ["created_at"])


def downgrade():
    if "system_updates" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("system_updates")

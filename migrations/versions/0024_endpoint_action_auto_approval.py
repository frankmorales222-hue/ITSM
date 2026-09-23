"""Add endpoint-action retry and auto-approval tracking.

Revision ID: 0024_endpoint_action_auto
Revises: 0023_smart_self_service
"""
from alembic import op
import sqlalchemy as sa


revision = "0024_endpoint_action_auto"
down_revision = "0023_smart_self_service"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "endpoint_actions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("endpoint_actions")}
    additions = {
        "auto_approved": sa.Column("auto_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        "auto_approved_at": sa.Column("auto_approved_at", sa.DateTime(timezone=True), nullable=True),
        "auto_approval_reason": sa.Column("auto_approval_reason", sa.String(255), nullable=False, server_default=""),
        "retry_count": sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("endpoint_actions", column)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("endpoint_actions")}
    if "ix_endpoint_actions_dispatched_at" not in indexes:
        op.create_index("ix_endpoint_actions_dispatched_at", "endpoint_actions", ["dispatched_at"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "endpoint_actions" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("endpoint_actions")}
    if "ix_endpoint_actions_dispatched_at" in indexes:
        op.drop_index("ix_endpoint_actions_dispatched_at", table_name="endpoint_actions")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("endpoint_actions")}
    for name in ("retry_count", "auto_approval_reason", "auto_approved_at", "auto_approved"):
        if name in columns:
            op.drop_column("endpoint_actions", name)

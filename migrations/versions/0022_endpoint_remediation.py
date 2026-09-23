"""Add requester-approved endpoint remediation queue.

Revision ID: 0022_endpoint_remediation
Revises: 0021_ticket_live_chat
"""
from alembic import op
import sqlalchemy as sa

revision = "0022_endpoint_remediation"
down_revision = "0021_ticket_live_chat"
branch_labels = None
depends_on = None


def upgrade():
    if "endpoint_actions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "endpoint_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("agent_id", sa.Integer(), sa.ForeignKey("endpoint_agents.id"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("target", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="Pending approval"),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_summary", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_endpoint_actions_organization_id", "endpoint_actions", ["organization_id"])
    op.create_index("ix_endpoint_actions_agent_id", "endpoint_actions", ["agent_id"])
    op.create_index("ix_endpoint_actions_ticket_id", "endpoint_actions", ["ticket_id"])
    op.create_index("ix_endpoint_actions_action_type", "endpoint_actions", ["action_type"])
    op.create_index("ix_endpoint_actions_status", "endpoint_actions", ["status"])
    op.create_index("ix_endpoint_actions_requested_by_id", "endpoint_actions", ["requested_by_id"])
    op.create_index("ix_endpoint_actions_agent_status", "endpoint_actions", ["agent_id", "status"])
    op.create_index("ix_endpoint_actions_ticket_created", "endpoint_actions", ["ticket_id", "created_at"])


def downgrade():
    if "endpoint_actions" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("endpoint_actions")

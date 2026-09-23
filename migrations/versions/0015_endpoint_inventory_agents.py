"""Add endpoint inventory agents and snapshots.

Revision ID: 0015_endpoint_inventory_agents
Revises: 0014_password_reset_tokens
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_endpoint_inventory_agents"
down_revision = "0014_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "agent_enrollment_tokens" not in existing:
        op.create_table(
            "agent_enrollment_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("label", sa.String(120), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_agent_enrollment_tokens_organization_id", "agent_enrollment_tokens", ["organization_id"])
        op.create_index("ix_agent_enrollment_tokens_token_hash", "agent_enrollment_tokens", ["token_hash"])
        op.create_index("ix_agent_enrollment_tokens_expires_at", "agent_enrollment_tokens", ["expires_at"])
    if "endpoint_agents" not in existing:
        op.create_table(
            "endpoint_agents",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("device_id", sa.String(64), nullable=False),
            sa.Column("credential_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("hostname", sa.String(120), nullable=False),
            sa.Column("agent_version", sa.String(40), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("observed_user_email", sa.String(255), nullable=True),
            sa.Column("consecutive_user_observations", sa.Integer(), nullable=False),
            sa.Column("assignment_state", sa.String(40), nullable=False),
            sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_inventory_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_ip", sa.String(80), nullable=False),
            sa.Column("last_error", sa.String(500), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "device_id"),
        )
        op.create_index("ix_endpoint_agents_organization_id", "endpoint_agents", ["organization_id"])
        op.create_index("ix_endpoint_agents_asset_id", "endpoint_agents", ["asset_id"])
        op.create_index("ix_endpoint_agents_device_id", "endpoint_agents", ["device_id"])
        op.create_index("ix_endpoint_agents_credential_hash", "endpoint_agents", ["credential_hash"])
        op.create_index("ix_endpoint_agents_last_seen_at", "endpoint_agents", ["last_seen_at"])
    if "asset_inventory_snapshots" not in existing:
        op.create_table(
            "asset_inventory_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("endpoint_agents.id"), nullable=False),
            sa.Column("schema_version", sa.Integer(), nullable=False),
            sa.Column("inventory_hash", sa.String(64), nullable=False),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("inventory", sa.JSON(), nullable=False),
        )
        op.create_index("ix_asset_inventory_snapshots_organization_id", "asset_inventory_snapshots", ["organization_id"])
        op.create_index("ix_asset_inventory_snapshots_asset_id", "asset_inventory_snapshots", ["asset_id"])
        op.create_index("ix_asset_inventory_snapshots_agent_id", "asset_inventory_snapshots", ["agent_id"])
        op.create_index("ix_asset_inventory_snapshots_inventory_hash", "asset_inventory_snapshots", ["inventory_hash"])
        op.create_index("ix_asset_inventory_snapshots_collected_at", "asset_inventory_snapshots", ["collected_at"])
        op.create_index("ix_asset_inventory_snapshots_received_at", "asset_inventory_snapshots", ["received_at"])


def downgrade():
    op.drop_table("asset_inventory_snapshots")
    op.drop_table("endpoint_agents")
    op.drop_table("agent_enrollment_tokens")

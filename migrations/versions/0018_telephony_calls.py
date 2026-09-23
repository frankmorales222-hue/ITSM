"""Track idempotent RingCentral call-to-ticket events.

Revision ID: 0018_telephony_calls
Revises: 0017_microsoft_sso_identity
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_telephony_calls"
down_revision = "0017_microsoft_sso_identity"
branch_labels = None
depends_on = None


def upgrade():
    inspector=sa.inspect(op.get_bind())
    if "telephony_calls" in inspector.get_table_names(): return
    op.create_table(
        "telephony_calls",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("connection_id",sa.Integer(),sa.ForeignKey("integration_connections.id"),nullable=False),
        sa.Column("provider",sa.String(40),nullable=False),
        sa.Column("session_id",sa.String(180),nullable=False),
        sa.Column("event_id",sa.String(180),nullable=False,server_default=""),
        sa.Column("direction",sa.String(20),nullable=False,server_default="Inbound"),
        sa.Column("caller_number",sa.String(60),nullable=False,server_default=""),
        sa.Column("destination_number",sa.String(60),nullable=False,server_default=""),
        sa.Column("queue_id",sa.String(100),nullable=False,server_default=""),
        sa.Column("status",sa.String(40),nullable=False,server_default="Received"),
        sa.Column("answered_extension_id",sa.String(100),nullable=False,server_default=""),
        sa.Column("ticket_id",sa.Integer(),sa.ForeignKey("tickets.id"),nullable=True),
        sa.Column("safe_payload",sa.JSON(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("organization_id",sa.Integer(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.UniqueConstraint("organization_id","provider","session_id",name="uq_telephony_calls_org_provider_session"),
    )
    for column in ("connection_id","provider","session_id","ticket_id","organization_id"):
        op.create_index(f"ix_telephony_calls_{column}","telephony_calls",[column])


def downgrade():
    op.drop_table("telephony_calls")

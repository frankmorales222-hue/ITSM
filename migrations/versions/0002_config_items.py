"""Add editable core configuration catalog."""
from alembic import op
import sqlalchemy as sa

revision = "0002_config_items"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "config_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("section", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("section", "name"),
    )
    op.create_index("ix_config_items_section", "config_items", ["section"])
    op.bulk_insert(table, [
        {"section":"teams","name":"Teams and queues","value":{"default_queue":"Service Desk","routing_mode":"least_active"},"description":"Default ownership and routing behavior","sensitive":False},
        {"section":"categories","name":"Categories","value":{"values":["General","Access","Software","Hardware","Onboarding","Network","Security"]},"description":"Available ticket categories","sensitive":False},
        {"section":"assignment","name":"Assignment rules","value":{"fallback_team":"Service Desk","exclude_unavailable":True,"category_first":True},"description":"Routing rule controls","sensitive":False},
        {"section":"sla","name":"SLA policies","value":{"Critical":{"first_response_hours":1,"resolution_hours":4},"High":{"first_response_hours":4,"resolution_hours":16},"Medium":{"first_response_hours":8,"resolution_hours":40},"Low":{"first_response_hours":16,"resolution_hours":80}},"description":"Priority-based service targets","sensitive":False},
        {"section":"calendar","name":"Business hours","value":{"timezone":"America/New_York","days":["Monday","Tuesday","Wednesday","Thursday","Friday"],"start":"08:00","end":"17:00","holidays":[]},"description":"Default support calendar","sensitive":False},
        {"section":"notifications","name":"Notification templates","value":{"ticket_created":"Your request {ticket_number} was received.","ticket_resolved":"Your request {ticket_number} was resolved."},"description":"User-facing templates","sensitive":False},
        {"section":"email","name":"Email settings","value":{"host":"","port":993,"encryption":"TLS","support_address":"","poll_seconds":60,"unknown_sender":"exception","attachment_policy":"accept_metadata_only"},"description":"Non-secret mailbox settings","sensitive":False},
        {"section":"authentication","name":"Local authentication","value":{"session_minutes":480,"lockout_attempts":5,"lockout_minutes":15,"minimum_password_length":12},"description":"Local security policy","sensitive":False},
        {"section":"retention","name":"Data retention","value":{"tickets_days":2555,"audit_days":2555,"automation_failures_days":365},"description":"Retention policy","sensitive":False},
    ])


def downgrade():
    op.drop_index("ix_config_items_section", table_name="config_items")
    op.drop_table("config_items")

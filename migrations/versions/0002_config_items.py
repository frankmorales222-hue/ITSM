"""Add editable core configuration catalog."""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "0002_config_items"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    if "organizations" in existing_tables and not bind.scalar(sa.text("SELECT COUNT(*) FROM organizations")):
        bind.execute(sa.text("INSERT INTO organizations (id, name, slug, timezone, support_email, support_phone, logo_url, active, created_at, updated_at) "
                             "VALUES (1, 'Primary Organization', 'primary', 'America/New_York', '', '', '', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    config_columns = {column["name"] for column in inspector.get_columns("config_items")} if "config_items" in existing_tables else set()
    table_columns = ([sa.column("organization_id", sa.Integer)] if "organization_id" in config_columns else []) + [
                     sa.column("section", sa.String), sa.column("name", sa.String),
                     sa.column("value", sa.JSON), sa.column("description", sa.String),
                     sa.column("sensitive", sa.Boolean), sa.column("updated_at", sa.DateTime(timezone=True))]
    table = sa.table("config_items", *table_columns)
    if "config_items" not in inspector.get_table_names():
        op.create_table(
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
    if bind.scalar(sa.select(sa.func.count()).select_from(table)):
        return
    rows = [
        {"section":"teams","name":"Teams and queues","value":{"default_queue":"Service Desk","routing_mode":"least_active"},"description":"Default ownership and routing behavior","sensitive":False},
        {"section":"categories","name":"Categories","value":{"values":["General","Access","Software","Hardware","Onboarding","Network","Security"]},"description":"Available ticket categories","sensitive":False},
        {"section":"assignment","name":"Assignment rules","value":{"method":"least_active","fallback_team":"Service Desk","exclude_unavailable":True,"category_first":True},"description":"Routing rule controls","sensitive":False},
        {"section":"sla","name":"SLA policies","value":{"Critical":{"first_response_hours":1,"resolution_hours":4},"High":{"first_response_hours":4,"resolution_hours":16},"Medium":{"first_response_hours":8,"resolution_hours":40},"Low":{"first_response_hours":16,"resolution_hours":80}},"description":"Priority-based service targets","sensitive":False},
        {"section":"calendar","name":"Business hours","value":{"timezone":"America/New_York","days":["Monday","Tuesday","Wednesday","Thursday","Friday"],"start":"08:00","end":"17:00","holidays":[]},"description":"Default support calendar","sensitive":False},
        {"section":"notifications","name":"Notification templates","value":{"ticket_created":"Your request {ticket_number} was received.","ticket_resolved":"Your request {ticket_number} was resolved."},"description":"User-facing templates","sensitive":False},
        {"section":"email","name":"Email settings","value":{"host":"","port":993,"encryption":"TLS","support_address":"","poll_seconds":60,"unknown_sender":"exception","attachment_policy":"accept_metadata_only"},"description":"Non-secret mailbox settings","sensitive":False},
        {"section":"authentication","name":"Local authentication","value":{"session_minutes":480,"lockout_attempts":5,"lockout_minutes":15,"minimum_password_length":12},"description":"Local security policy","sensitive":False},
        {"section":"retention","name":"Data retention","value":{"tickets_days":2555,"audit_days":2555,"automation_failures_days":365},"description":"Retention policy","sensitive":False},
    ]
    timestamp = datetime.now(timezone.utc)
    for row in rows:
        row["updated_at"] = timestamp
        if "organization_id" in config_columns: row["organization_id"] = 1
    op.bulk_insert(table, rows)


def downgrade():
    op.drop_index("ix_config_items_section", table_name="config_items")
    op.drop_table("config_items")

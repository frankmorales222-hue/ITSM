"""Add organization boundaries and configurable RingCentral integration."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0004_organizations_integrations"
down_revision = "0003_assetpilot_inventory"
branch_labels = None
depends_on = None


TENANT_TABLES = [
    "departments", "locations", "teams", "users", "employees", "assets", "tickets",
    "audit_events", "email_messages", "notifications", "automation_failures",
    "announcements", "feedback", "config_items",
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "organizations" not in inspector.get_table_names():
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("slug", sa.String(80), nullable=False),
            sa.Column("timezone", sa.String(80), nullable=False, server_default="America/New_York"),
            sa.Column("support_email", sa.String(255), nullable=False, server_default=""),
            sa.Column("support_phone", sa.String(40), nullable=False, server_default=""),
            sa.Column("logo_url", sa.String(500), nullable=False, server_default=""),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)
        organizations = sa.table("organizations", sa.column("id", sa.Integer), sa.column("name", sa.String),
                                 sa.column("slug", sa.String), sa.column("timezone", sa.String),
                                 sa.column("support_email", sa.String), sa.column("support_phone", sa.String),
                                 sa.column("logo_url", sa.String), sa.column("active", sa.Boolean),
                                 sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime))
        timestamp = datetime.now(timezone.utc)
        op.bulk_insert(organizations, [{"id": 1, "name": "Primary Organization", "slug": "primary",
                                        "timezone": "America/New_York", "support_email": "", "support_phone": "",
                                        "logo_url": "", "active": True, "created_at": timestamp, "updated_at": timestamp}])

    for table_name in TENANT_TABLES:
        columns = {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
        if "organization_id" not in columns:
            column = (sa.Column("organization_id", sa.Integer(), nullable=True)
                      if bind.dialect.name == "sqlite"
                      else sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True))
            op.add_column(table_name, column)
            op.execute(sa.text(f"UPDATE {table_name} SET organization_id = 1 WHERE organization_id IS NULL"))
            op.create_index(f"ix_{table_name}_organization_id", table_name, ["organization_id"])

    user_columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "ringcentral_extension_id" not in user_columns:
        op.add_column("users", sa.Column("ringcentral_extension_id", sa.String(80), nullable=True))
    if "ringcentral_extension_number" not in user_columns:
        op.add_column("users", sa.Column("ringcentral_extension_number", sa.String(30), nullable=True))

    if "integration_secrets" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "integration_secrets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("provider", sa.String(80), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("encrypted_value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("organization_id", "provider", "name"),
        )
        op.create_index("ix_integration_secrets_organization_id", "integration_secrets", ["organization_id"])
        op.create_index("ix_integration_secrets_provider", "integration_secrets", ["provider"])

    config = sa.table("config_items", sa.column("organization_id", sa.Integer), sa.column("section", sa.String),
                      sa.column("name", sa.String), sa.column("value", sa.JSON), sa.column("description", sa.String),
                      sa.column("sensitive", sa.Boolean), sa.column("updated_at", sa.DateTime(timezone=True)))
    exists = bind.scalar(sa.select(sa.func.count()).select_from(config).where(config.c.section == "ringcentral"))
    if not exists:
        op.bulk_insert(config, [{
            "organization_id": 1, "section": "ringcentral", "name": "RingCentral phone integration",
            "value": {"enabled": False, "environment": "production", "connection_mode": "websocket",
                      "client_id": "", "support_number": "", "queue_extension": "", "routing_mode": "rotating",
                      "ticket_trigger": "answered", "default_team": "Service Desk", "default_category": "Phone Support",
                      "default_priority": "Medium", "caller_matching": "phone_number", "unknown_caller": "create_ticket",
                      "open_ticket_on_answer": True, "create_missed_call_ticket": True},
            "description": "Per-organization call routing and automatic ticket behavior",
            "sensitive": False, "updated_at": datetime.now(timezone.utc),
        }])


def downgrade():
    if "integration_secrets" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("integration_secrets")
    for column in ("ringcentral_extension_number", "ringcentral_extension_id"):
        if column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns("users")}:
            op.drop_column("users", column)
    for table_name in reversed(TENANT_TABLES):
        if "organization_id" in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}:
            op.drop_index(f"ix_{table_name}_organization_id", table_name=table_name)
            op.drop_column(table_name, "organization_id")
    if "organizations" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("organizations")

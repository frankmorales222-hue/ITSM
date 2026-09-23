"""Add configurable administration resources without changing historical records."""
from alembic import op
import sqlalchemy as sa


revision = "0009_administration_foundation"
down_revision = "0008_requester_snapshot"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    bind = op.get_bind()
    current_tables = {
        "support_queues", "user_groups", "user_group_memberships", "service_categories",
        "routing_rules", "notification_rules", "integration_connections", "integration_logs",
    }
    # Revision 0001 creates the current metadata on a brand-new installation.
    # In that path these tables already exist and the normal application seed
    # supplies their initial records after the migration chain completes.
    if current_tables.issubset(set(sa.inspect(bind).get_table_names())):
        return
    op.create_table("support_queues", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""), sa.Column("assignment_strategy", sa.String(60), nullable=False, server_default="round_robin"),
        sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(), sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_support_queues_name", "support_queues", ["name"]); op.create_index("ix_support_queues_team_id", "support_queues", ["team_id"])
    op.create_table("user_groups", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(140), nullable=False), sa.Column("group_type", sa.String(60), nullable=False, server_default="Custom"),
        sa.Column("description", sa.String(500), nullable=False, server_default=""), sa.Column("source", sa.String(40), nullable=False, server_default="Local"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), *timestamps(), sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_user_groups_name", "user_groups", ["name"])
    op.create_table("user_group_memberships", sa.Column("group_id", sa.Integer(), sa.ForeignKey("user_groups.id"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True), sa.Column("membership_role", sa.String(30), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("service_categories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(140), nullable=False), sa.Column("parent_id", sa.Integer(), sa.ForeignKey("service_categories.id"), nullable=True),
        sa.Column("level", sa.String(30), nullable=False, server_default="category"), sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"), sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), *timestamps(), sa.UniqueConstraint("organization_id", "parent_id", "name"))
    op.create_index("ix_service_categories_name", "service_categories", ["name"]); op.create_index("ix_service_categories_parent_id", "service_categories", ["parent_id"])
    op.create_table("routing_rules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("priority_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="[]"), sa.Column("actions", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), *timestamps(), sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_routing_rules_priority_order", "routing_rules", ["priority_order"])
    op.create_table("notification_rules", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False), sa.Column("trigger", sa.String(80), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False, server_default="[]"), sa.Column("recipients", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("template", sa.JSON(), nullable=False, server_default="{}"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(), sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_notification_rules_trigger", "notification_rules", ["trigger"])
    op.create_table("integration_connections", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False), sa.Column("name", sa.String(140), nullable=False), sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("configuration", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="Disabled"), sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True), sa.Column("last_error", sa.String(500), nullable=False, server_default=""),
        sa.Column("records_processed", sa.Integer(), nullable=False, server_default="0"), *timestamps(), sa.UniqueConstraint("organization_id", "kind", "name"))
    op.create_index("ix_integration_connections_kind", "integration_connections", ["kind"])
    op.create_table("integration_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), sa.ForeignKey("integration_connections.id"), nullable=False), sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("event", sa.String(100), nullable=False), sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_integration_logs_connection_id", "integration_logs", ["connection_id"])

    bind = op.get_bind(); now = sa.func.current_timestamp()
    for organization_id in bind.execute(sa.text("SELECT id FROM organizations")).scalars().all():
        for name, level, order in [("Hardware","category",10),("Software","category",20),("Access","category",30),("Network","category",40),("Security","category",50)]:
            bind.execute(sa.text("INSERT INTO service_categories (organization_id,name,level,description,sort_order,configuration,active,created_at,updated_at) VALUES (:o,:n,:l,'',:s,'{}',TRUE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o":organization_id,"n":name,"l":level,"s":order})
        for kind, name, provider in [("directory","Microsoft Entra ID","Microsoft Entra ID"),("directory","Active Directory / LDAP","LDAP"),("email","Service Desk Email","Generic SMTP/IMAP"),("telephony","Telephony / Communications","RingCentral")]:
            bind.execute(sa.text("INSERT INTO integration_connections (organization_id,kind,name,provider,enabled,configuration,status,last_error,records_processed,created_at,updated_at) VALUES (:o,:k,:n,:p,FALSE,'{}','Disabled','',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o":organization_id,"k":kind,"n":name,"p":provider})
        for team_id, team_name, queue_name in bind.execute(sa.text("SELECT id,name,queue_name FROM teams WHERE organization_id=:o"), {"o":organization_id}).all():
            bind.execute(sa.text("INSERT INTO support_queues (organization_id,name,team_id,description,assignment_strategy,configuration,active,created_at,updated_at) VALUES (:o,:n,:t,:d,'round_robin','{}',TRUE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o":organization_id,"n":queue_name,"t":team_id,"d":f"Default queue for {team_name}"})


def downgrade():
    for table in ["integration_logs","integration_connections","notification_rules","routing_rules","service_categories","user_group_memberships","user_groups","support_queues"]:
        op.drop_table(table)

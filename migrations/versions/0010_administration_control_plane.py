"""Build the organization-scoped Administration control plane.

Revision ID: 0010_administration_control_plane
Revises: 0009_administration_foundation
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_administration_control_plane"
down_revision = "0009_administration_foundation"
branch_labels = None
depends_on = None


def json_default(value: str):
    return sa.text(f"'{value}'")


def add_columns(table: str, columns: list[sa.Column]):
    for column in columns:
        op.add_column(table, column)


def upgrade():
    bind = op.get_bind()
    # Some installations reached revision 0009 before descriptive revision
    # identifiers were introduced. Repair their legacy Alembic column before
    # this 33-character revision is recorded. The packaged-server preflight
    # performs the same repair as defense in depth.
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
    current_tables = {"group_types", "role_definitions", "team_memberships", "queue_team_eligibility",
                      "user_role_assignments", "routing_rule_versions", "event_catalog", "domain_events"}
    user_columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if current_tables.issubset(set(sa.inspect(bind).get_table_names())) and "alternate_email" in user_columns:
        return
    op.create_table("group_types",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False), sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("icon", sa.String(40), nullable=False, server_default="group"), sa.Column("color", sa.String(20), nullable=False, server_default="#176453"),
        sa.Column("purpose", sa.String(200), nullable=False, server_default=""), sa.Column("allowed_uses", sa.JSON(), nullable=False, server_default=json_default("[]")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_group_types_name", "group_types", ["name"])

    op.create_table("role_definitions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""), sa.Column("permissions", sa.JSON(), nullable=False, server_default=json_default("{}")),
        sa.Column("parent_role_id", sa.Integer(), sa.ForeignKey("role_definitions.id"), nullable=True), sa.Column("system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "key"), sa.UniqueConstraint("organization_id", "name"))
    op.create_index("ix_role_definitions_key", "role_definitions", ["key"])

    op.create_table("team_memberships",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("membership_role", sa.String(30), nullable=False, server_default="member"), sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("capacity_override", sa.Integer(), nullable=True), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "team_id", "user_id"))
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"]); op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])

    op.create_table("queue_team_eligibility",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("queue_id", sa.Integer(), sa.ForeignKey("support_queues.id"), nullable=False), sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("eligibility_priority", sa.Integer(), nullable=False, server_default="100"), sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("schedule", sa.JSON(), nullable=False, server_default=json_default("{}")), sa.Column("capacity_override", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "queue_id", "team_id"))
    op.create_index("ix_queue_team_eligibility_queue_id", "queue_team_eligibility", ["queue_id"]); op.create_index("ix_queue_team_eligibility_team_id", "queue_team_eligibility", ["team_id"])

    op.create_table("user_role_assignments",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("role_definition_id", sa.Integer(), sa.ForeignKey("role_definitions.id"), nullable=False),
        sa.Column("source", sa.String(40), nullable=False, server_default="Direct"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "user_id", "role_definition_id"))
    op.create_index("ix_user_role_assignments_user_id", "user_role_assignments", ["user_id"]); op.create_index("ix_user_role_assignments_role_definition_id", "user_role_assignments", ["role_definition_id"])

    op.create_table("routing_rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("routing_rule_id", sa.Integer(), sa.ForeignKey("routing_rules.id"), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default=json_default("{}")), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()))
    op.create_index("ix_routing_rule_versions_routing_rule_id", "routing_rule_versions", ["routing_rule_id"])

    op.create_table("event_catalog",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("key", sa.String(120), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("category", sa.String(60), nullable=False, server_default="ticket"), sa.Column("reportable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("custom", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "key"))
    op.create_index("ix_event_catalog_key", "event_catalog", ["key"])

    op.create_table("domain_events",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("event_key", sa.String(120), nullable=False), sa.Column("aggregate_type", sa.String(80), nullable=False), sa.Column("aggregate_id", sa.String(100), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True), sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=json_default("{}")), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "idempotency_key"))
    op.create_index("ix_domain_events_event_key", "domain_events", ["event_key"]); op.create_index("ix_domain_events_aggregate", "domain_events", ["aggregate_type", "aggregate_id"])

    add_columns("users", [
        sa.Column("alternate_email", sa.String(255), nullable=False, server_default=""), sa.Column("employee_number", sa.String(80), nullable=False, server_default=""),
        sa.Column("phone", sa.String(60), nullable=False, server_default=""), sa.Column("job_title", sa.String(120), nullable=False, server_default=""),
        sa.Column("department_name", sa.String(120), nullable=False, server_default=""), sa.Column("location_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("manager_user_id", sa.Integer(), nullable=True), sa.Column("timezone", sa.String(80), nullable=False, server_default="America/New_York"),
        sa.Column("preferred_language", sa.String(20), nullable=False, server_default="en"), sa.Column("notification_preferences", sa.JSON(), nullable=False, server_default=json_default("{}")),
        sa.Column("auth_source", sa.String(40), nullable=False, server_default="Local"), sa.Column("role_source", sa.String(40), nullable=False, server_default="Local role catalog"),
        sa.Column("team_source", sa.String(40), nullable=False, server_default="Direct assignment"), sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("teams", [
        sa.Column("key", sa.String(80), nullable=True), sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("lead_user_id", sa.Integer(), nullable=True), sa.Column("backup_lead_user_id", sa.Integer(), nullable=True), sa.Column("region", sa.String(80), nullable=False, server_default=""),
        sa.Column("supported_locations", sa.JSON(), nullable=False, server_default=json_default("[]")), sa.Column("timezone", sa.String(80), nullable=False, server_default="America/New_York"),
        sa.Column("business_hours", sa.JSON(), nullable=False, server_default=json_default("{}")), sa.Column("supported_services", sa.JSON(), nullable=False, server_default=json_default("[]")),
        sa.Column("supported_categories", sa.JSON(), nullable=False, server_default=json_default("[]")), sa.Column("default_capacity", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("escalation_team_id", sa.Integer(), nullable=True), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("support_queues", [sa.Column("key", sa.String(80), nullable=True), sa.Column("manager_user_id", sa.Integer(), nullable=True),
        sa.Column("priority_order", sa.Integer(), nullable=False, server_default="100"), sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("user_groups", [sa.Column("group_type_id", sa.Integer(), nullable=True), sa.Column("manager_user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(255), nullable=False, server_default=""), sa.Column("region", sa.String(80), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="America/New_York"), sa.Column("escalation_contact", sa.String(255), nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("service_categories", [sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("routing_rules", [sa.Column("description", sa.String(500), nullable=False, server_default=""), sa.Column("trigger", sa.String(80), nullable=False, server_default="ticket.created"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("stop_processing", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("overwrite_existing", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("reevaluate_fields", sa.JSON(), nullable=False, server_default=json_default("[]")),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True), sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("notification_rules", [sa.Column("classification", sa.String(30), nullable=False, server_default="customer"), sa.Column("locale", sa.String(20), nullable=False, server_default="en"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("rate_limit", sa.JSON(), nullable=False, server_default=json_default("{}")),
        sa.Column("suppress_actor", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1")])
    add_columns("integration_connections", [sa.Column("secret_refs", sa.JSON(), nullable=False, server_default=json_default("{}")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), sa.Column("version", sa.Integer(), nullable=False, server_default="1")])

    bind = op.get_bind()
    role_permissions = {
        "end_user":{"tickets":["view_own","create"]}, "technician":{"tickets":["view_team","edit","assign"],"assets":["view"]},
        "team_lead":{"tickets":["view_team","edit","assign"],"reports":["view_team"]}, "manager":{"tickets":["view_all","edit","approve"],"reports":["view_all","export"]},
        "admin":{"administration":["administer"],"integrations":["configure"],"audit":["view"],"tickets":["view_all","edit","assign","approve"]},
        "auditor":{"tickets":["view_all"],"reports":["view_all","export"],"audit":["view"]}}
    role_names={"end_user":"End User","technician":"Technician","team_lead":"Team Lead","manager":"Manager","admin":"Administrator","auditor":"Auditor"}
    group_types=[("Support","Teams that deliver service",10),("Department","Business departments",20),("Security","Security and access groups",30),("Approval","Approval authorities",40),("Distribution","Notification distribution",50),("Asset ownership","Asset custodians",60),("Reporting","Reporting audiences",70),("Custom","Organization-defined use",80)]
    event_keys=["ticket.created","ticket.assigned","ticket.reassigned","ticket.updated","ticket.public_reply","ticket.internal_note","ticket.waiting_on_requester","ticket.resolved","ticket.closed","ticket.reopened","approval.requested","approval.reminder","approval.approved","approval.rejected","sla.warning","sla.breached","incident.major_declared","incident.status_changed","change.submitted","change.approved","change.rejected","change.scheduled","call.received","call.answered","call.missed","call.abandoned","voicemail.received","routing.failed","integration.failed","user.created","user.deactivated","asset.assigned","asset.returned"]
    for org in bind.execute(sa.text("SELECT id FROM organizations")).scalars():
        for key,name in role_names.items():
            bind.execute(sa.text("INSERT INTO role_definitions (organization_id,key,name,description,permissions,system,active,version,created_at,updated_at) VALUES (:o,:k,:n,:d,:p,TRUE,TRUE,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"o":org,"k":key,"n":name,"d":f"System {name} role","p":__import__('json').dumps(role_permissions[key])})
        for name,purpose,order in group_types:
            bind.execute(sa.text("INSERT INTO group_types (organization_id,name,description,icon,color,purpose,allowed_uses,sort_order,active,version,created_at,updated_at) VALUES (:o,:n,'','group','#176453',:p,'[]',:s,TRUE,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"o":org,"n":name,"p":purpose,"s":order})
        custom_id=bind.execute(sa.text("SELECT id FROM group_types WHERE organization_id=:o AND name='Custom'"),{"o":org}).scalar()
        bind.execute(sa.text("UPDATE user_groups SET group_type_id=:g WHERE organization_id=:o"),{"g":custom_id,"o":org})
        for key in event_keys:
            bind.execute(sa.text("INSERT INTO event_catalog (organization_id,key,name,description,category,reportable,custom,active,created_at,updated_at) VALUES (:o,:k,:n,'',:c,TRUE,FALSE,TRUE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{"o":org,"k":key,"n":key.replace('.',' ').replace('_',' ').title(),"c":key.split('.')[0]})
        bind.execute(sa.text("UPDATE teams SET key=lower(replace(name,' ','-')) WHERE organization_id=:o AND key IS NULL"),{"o":org})
        bind.execute(sa.text("UPDATE support_queues SET key=lower(replace(name,' ','-')) WHERE organization_id=:o AND key IS NULL"),{"o":org})
        bind.execute(sa.text("INSERT INTO team_memberships (organization_id,team_id,user_id,membership_role,is_primary,active,created_at,updated_at) SELECT organization_id,team_id,id,'member',TRUE,TRUE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM users WHERE organization_id=:o AND team_id IS NOT NULL"),{"o":org})
        bind.execute(sa.text("INSERT INTO queue_team_eligibility (organization_id,queue_id,team_id,eligibility_priority,weight,schedule,active,created_at,updated_at) SELECT organization_id,id,team_id,100,100,'{}',TRUE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM support_queues WHERE organization_id=:o"),{"o":org})


def downgrade():
    for table, columns in {
        "integration_connections":["version","archived_at","secret_refs"], "notification_rules":["version","archived_at","suppress_actor","rate_limit","status","locale","classification"],
        "routing_rules":["version","archived_at","last_matched_at","match_count","effective_until","effective_from","reevaluate_fields","overwrite_existing","stop_processing","status","trigger","description"],
        "service_categories":["version","archived_at"], "user_groups":["version","archived_at","escalation_contact","timezone","region","email","manager_user_id","group_type_id"],
        "support_queues":["version","archived_at","priority_order","manager_user_id","key"], "teams":["version","archived_at","active","escalation_team_id","default_capacity","supported_categories","supported_services","business_hours","timezone","supported_locations","region","backup_lead_user_id","lead_user_id","description","key"],
        "users":["version","archived_at","team_source","role_source","auth_source","notification_preferences","preferred_language","timezone","manager_user_id","location_name","department_name","job_title","phone","employee_number","alternate_email"]}.items():
        for column in columns: op.drop_column(table,column)
    for table in ["domain_events","event_catalog","routing_rule_versions","user_role_assignments","queue_team_eligibility","team_memberships","role_definitions","group_types"]:
        op.drop_table(table)

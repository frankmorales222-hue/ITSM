"""Add configurable forms, approval workflows, and saved reports."""

from alembic import op
import sqlalchemy as sa


revision = "0005_studio_approvals_reports"
down_revision = "0004_organizations_integrations"
branch_labels = None
depends_on = None


def _seed_current_schema(bind):
    forms = sa.table("form_definitions", sa.column("id", sa.Integer), sa.column("organization_id", sa.Integer),
                     sa.column("slug", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
                     sa.column("category", sa.String), sa.column("icon", sa.String), sa.column("fields", sa.JSON),
                     sa.column("active", sa.Boolean), sa.column("published", sa.Boolean),
                     sa.column("created_at", sa.DateTime(timezone=True)), sa.column("updated_at", sa.DateTime(timezone=True)))
    workflows = sa.table("approval_workflows", sa.column("organization_id", sa.Integer), sa.column("name", sa.String),
                         sa.column("form_definition_id", sa.Integer), sa.column("steps", sa.JSON), sa.column("active", sa.Boolean),
                         sa.column("created_at", sa.DateTime(timezone=True)), sa.column("updated_at", sa.DateTime(timezone=True)))
    templates = [
        ("incident-report", "Incident Report", "Report an operational, security, or service incident.", "Incident", "incident", [
            {"id":"incident-type","key":"incident_type","label":"Incident type","type":"select","required":True,"help":"Choose the closest match.","options":["Service disruption","Security","Privacy","Safety","Other"]},
            {"id":"incident-time","key":"occurred_at","label":"When did it happen?","type":"date","required":True,"help":"","options":[]},
            {"id":"incident-detail","key":"details","label":"What happened?","type":"long_text","required":True,"help":"Include impact and actions already taken.","options":[]}]),
        ("change-management", "Change Management", "Request, assess, approve, and schedule a controlled change.", "Change", "change", [
            {"id":"change-reason","key":"business_reason","label":"Business reason","type":"long_text","required":True,"help":"Why is this change needed?","options":[]},
            {"id":"change-plan","key":"implementation_plan","label":"Implementation plan","type":"long_text","required":True,"help":"Describe the planned steps.","options":[]},
            {"id":"change-risk","key":"risk_level","label":"Risk level","type":"select","required":True,"help":"","options":["Low","Medium","High","Emergency"]},
            {"id":"change-backout","key":"backout_plan","label":"Backout plan","type":"long_text","required":True,"help":"How will the change be reversed?","options":[]}]),
        ("it-support", "IT Support", "Request technical assistance for a user, device, or service.", "General", "support", [
            {"id":"support-service","key":"service","label":"Affected service","type":"short_text","required":True,"help":"Application, device, or service name.","options":[]},
            {"id":"support-detail","key":"details","label":"What do you need help with?","type":"long_text","required":True,"help":"Include error messages and when the problem started.","options":[]}]),
    ]
    for organization_id in bind.execute(sa.text("SELECT id FROM organizations")).scalars().all():
        if bind.scalar(sa.select(sa.func.count()).select_from(forms).where(forms.c.organization_id == organization_id)):
            continue
        for slug, name, description, category, icon, fields in templates:
            bind.execute(forms.insert().values(organization_id=organization_id, slug=slug, name=name,
                                               description=description, category=category, icon=icon, fields=fields,
                                               active=True, published=True, created_at=sa.func.now(), updated_at=sa.func.now()))
        change_id = bind.scalar(sa.select(forms.c.id).where(forms.c.organization_id == organization_id,
                                                            forms.c.slug == "change-management"))
        bind.execute(workflows.insert().values(organization_id=organization_id, name="Change approval",
                                               form_definition_id=change_id,
                                               steps=[{"name":"Manager approval","approver_role":"manager","approver_user_id":None}],
                                               active=True, created_at=sa.func.now(), updated_at=sa.func.now()))


def upgrade():
    bind = op.get_bind()
    existing_tables = set(sa.inspect(bind).get_table_names())
    current_tables = {"form_definitions", "approval_workflows", "approval_requests", "approval_decisions", "report_definitions"}
    ticket_columns = {column["name"] for column in sa.inspect(bind).get_columns("tickets")}
    if current_tables.issubset(existing_tables) and {"form_definition_id", "custom_data"}.issubset(ticket_columns):
        _seed_current_schema(bind)
        return
    op.create_table(
        "form_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("category", sa.String(100), nullable=False, server_default="General"),
        sa.Column("icon", sa.String(30), nullable=False, server_default="form"),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "slug"),
    )
    op.create_index("ix_form_definitions_organization_id", "form_definitions", ["organization_id"])
    op.create_index("ix_form_definitions_slug", "form_definitions", ["slug"])
    op.create_index("ix_form_definitions_active", "form_definitions", ["active"])
    op.create_index("ix_form_definitions_published", "form_definitions", ["published"])

    op.create_table(
        "approval_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("form_definition_id", sa.Integer(), sa.ForeignKey("form_definitions.id"), nullable=False, unique=True),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_approval_workflows_organization_id", "approval_workflows", ["organization_id"])
    op.create_index("ix_approval_workflows_form_definition_id", "approval_workflows", ["form_definition_id"], unique=True)

    op.add_column("tickets", sa.Column("form_definition_id", sa.Integer(), nullable=True))
    op.add_column("tickets", sa.Column("custom_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_index("ix_tickets_form_definition_id", "tickets", ["form_definition_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key("fk_tickets_form_definition_id", "tickets", "form_definitions", ["form_definition_id"], ["id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False, unique=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("approval_workflows.id"), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("current_approver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="Pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("organization_id", "ticket_id", "workflow_id", "requested_by_id", "current_approver_id", "status"):
        op.create_index(f"ix_approval_requests_{column}", "approval_requests", [column], unique=column == "ticket_id")

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id"), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("approver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("organization_id", "approval_request_id", "approver_id"):
        op.create_index(f"ix_approval_decisions_{column}", "approval_decisions", [column])

    op.create_table(
        "report_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index("ix_report_definitions_organization_id", "report_definitions", ["organization_id"])

    forms = sa.table("form_definitions", sa.column("id", sa.Integer), sa.column("organization_id", sa.Integer),
                     sa.column("slug", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
                     sa.column("category", sa.String), sa.column("icon", sa.String), sa.column("fields", sa.JSON),
                     sa.column("active", sa.Boolean), sa.column("published", sa.Boolean))
    workflows = sa.table("approval_workflows", sa.column("organization_id", sa.Integer), sa.column("name", sa.String),
                         sa.column("form_definition_id", sa.Integer), sa.column("steps", sa.JSON), sa.column("active", sa.Boolean))
    organizations = bind.execute(sa.text("SELECT id FROM organizations")).scalars().all()
    templates = [
        {"slug": "incident-report", "name": "Incident Report", "description": "Report an operational, security, or service incident.",
         "category": "Incident", "icon": "incident", "fields": [
             {"id": "incident-type", "key": "incident_type", "label": "Incident type", "type": "select", "required": True, "help": "Choose the closest match.", "options": ["Service disruption", "Security", "Privacy", "Safety", "Other"]},
             {"id": "incident-time", "key": "occurred_at", "label": "When did it happen?", "type": "date", "required": True, "help": "", "options": []},
             {"id": "incident-detail", "key": "details", "label": "What happened?", "type": "long_text", "required": True, "help": "Include impact and actions already taken.", "options": []}],
         "active": True, "published": True},
        {"slug": "change-management", "name": "Change Management", "description": "Request, assess, approve, and schedule a controlled change.",
         "category": "Change", "icon": "change", "fields": [
             {"id": "change-reason", "key": "business_reason", "label": "Business reason", "type": "long_text", "required": True, "help": "Why is this change needed?", "options": []},
             {"id": "change-plan", "key": "implementation_plan", "label": "Implementation plan", "type": "long_text", "required": True, "help": "Describe the planned steps.", "options": []},
             {"id": "change-risk", "key": "risk_level", "label": "Risk level", "type": "select", "required": True, "help": "", "options": ["Low", "Medium", "High", "Emergency"]},
             {"id": "change-backout", "key": "backout_plan", "label": "Backout plan", "type": "long_text", "required": True, "help": "How will the change be reversed?", "options": []}],
         "active": True, "published": True},
        {"slug": "it-support", "name": "IT Support", "description": "Request technical assistance for a user, device, or service.",
         "category": "General", "icon": "support", "fields": [
             {"id": "support-service", "key": "service", "label": "Affected service", "type": "short_text", "required": True, "help": "Application, device, or service name.", "options": []},
             {"id": "support-detail", "key": "details", "label": "What do you need help with?", "type": "long_text", "required": True, "help": "Include error messages and when the problem started.", "options": []}],
         "active": True, "published": True},
    ]
    for organization_id in organizations:
        for template in templates:
            bind.execute(forms.insert().values(organization_id=organization_id, **template))
        change_id = bind.scalar(sa.select(forms.c.id).where(forms.c.organization_id == organization_id,
                                                            forms.c.slug == "change-management"))
        bind.execute(workflows.insert().values(organization_id=organization_id, name="Change approval",
                                               form_definition_id=change_id,
                                               steps=[{"name": "Manager approval", "approver_role": "manager", "approver_user_id": None}],
                                               active=True))


def downgrade():
    op.drop_table("report_definitions")
    op.drop_table("approval_decisions")
    op.drop_table("approval_requests")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_tickets_form_definition_id", "tickets", type_="foreignkey")
    op.drop_index("ix_tickets_form_definition_id", table_name="tickets")
    op.drop_column("tickets", "custom_data")
    op.drop_column("tickets", "form_definition_id")
    op.drop_table("approval_workflows")
    op.drop_table("form_definitions")

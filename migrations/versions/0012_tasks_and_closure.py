"""Add reusable task templates and ticket closure checklists.

Revision ID: 0012_tasks_and_closure
Revises: 0011_incident_vertical_slice
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_tasks_and_closure"
down_revision = "0011_incident_vertical_slice"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    workflow_columns = {column["name"] for column in sa.inspect(bind).get_columns("approval_workflows")}
    if {"task_templates", "ticket_checklists"}.issubset(tables) and {"task_template_ids", "closure_requirements"}.issubset(workflow_columns):
        return
    op.add_column("approval_workflows", sa.Column("task_template_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("approval_workflows", sa.Column("closure_requirements", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "task_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False, server_default=""),
        sa.Column("items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name"),
    )
    op.create_index("ix_task_templates_organization_id", "task_templates", ["organization_id"])
    op.create_index("ix_task_templates_name", "task_templates", ["name"])
    op.create_index("ix_task_templates_active", "task_templates", ["active"])
    op.create_table(
        "ticket_checklists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("task_template_id", sa.Integer(), sa.ForeignKey("task_templates.id"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(30), nullable=False, server_default="Active"),
        sa.Column("required_for_closure", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ticket_checklists_organization_id", "ticket_checklists", ["organization_id"])
    op.create_index("ix_ticket_checklists_ticket_id", "ticket_checklists", ["ticket_id"])
    op.create_index("ix_ticket_checklists_task_template_id", "ticket_checklists", ["task_template_id"])
    op.create_index("ix_ticket_checklists_status", "ticket_checklists", ["status"])


def downgrade():
    op.drop_table("ticket_checklists")
    op.drop_table("task_templates")
    op.drop_column("approval_workflows", "closure_requirements")
    op.drop_column("approval_workflows", "task_template_ids")

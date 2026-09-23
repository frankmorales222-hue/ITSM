"""Add enterprise endpoint identity matching fields.

Revision ID: 0016_enterprise_agent_identity
Revises: 0015_endpoint_inventory_agents
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_enterprise_agent_identity"
down_revision = "0015_endpoint_inventory_agents"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {item["name"] for item in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    employee_columns = _columns(bind, "employees")
    with op.batch_alter_table("employees") as batch:
        if "alternate_emails" not in employee_columns:
            batch.add_column(sa.Column("alternate_emails", sa.JSON(), nullable=False, server_default="[]"))
        if "account_name" not in employee_columns:
            batch.add_column(sa.Column("account_name", sa.String(120), nullable=False, server_default=""))
        if "directory_object_id" not in employee_columns:
            batch.add_column(sa.Column("directory_object_id", sa.String(80), nullable=False, server_default=""))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("employees")}
    if "ix_employees_account_name" not in indexes:
        op.create_index("ix_employees_account_name", "employees", ["account_name"])
    if "ix_employees_directory_object_id" not in indexes:
        op.create_index("ix_employees_directory_object_id", "employees", ["directory_object_id"])

    agent_columns = _columns(bind, "endpoint_agents")
    with op.batch_alter_table("endpoint_agents") as batch:
        if "observed_user" not in agent_columns:
            batch.add_column(sa.Column("observed_user", sa.JSON(), nullable=False, server_default="{}"))
        if "identity_match_method" not in agent_columns:
            batch.add_column(sa.Column("identity_match_method", sa.String(40), nullable=False, server_default=""))
        if "matched_employee_id" not in agent_columns:
            batch.add_column(sa.Column("matched_employee_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_endpoint_agents_matched_employee", "employees", ["matched_employee_id"], ["id"])
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("endpoint_agents")}
    if "ix_endpoint_agents_matched_employee_id" not in indexes:
        op.create_index("ix_endpoint_agents_matched_employee_id", "endpoint_agents", ["matched_employee_id"])


def downgrade():
    op.drop_index("ix_endpoint_agents_matched_employee_id", table_name="endpoint_agents")
    with op.batch_alter_table("endpoint_agents") as batch:
        batch.drop_column("matched_employee_id")
        batch.drop_column("identity_match_method")
        batch.drop_column("observed_user")
    op.drop_index("ix_employees_directory_object_id", table_name="employees")
    op.drop_index("ix_employees_account_name", table_name="employees")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("directory_object_id")
        batch.drop_column("account_name")
        batch.drop_column("alternate_emails")

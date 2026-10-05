"""Store endpoint update and self-repair state.

Revision ID: 0013_agent_health_state
Revises: 0012_tasks_and_closure
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_agent_health_state"
down_revision = "0012_tasks_and_closure"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("endpoint_agents")}
    if "update_state" not in columns:
        op.add_column("endpoint_agents", sa.Column("update_state", sa.JSON(), nullable=False, server_default="{}"))
    if "self_repair_state" not in columns:
        op.add_column("endpoint_agents", sa.Column("self_repair_state", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("endpoint_agents", "self_repair_state")
    op.drop_column("endpoint_agents", "update_state")

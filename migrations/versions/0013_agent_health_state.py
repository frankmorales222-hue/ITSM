"""Store endpoint update and self-repair state.

The numeric prefix is intentionally out of sequence. Release 0.4.96 shipped
this revision identifier after revision 0024, and production databases already
store ``0013_agent_health_state``. Never rename this revision; future
migrations must descend from the current single head.

Revision ID: 0013_agent_health_state
Revises: 0024_endpoint_action_auto
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_agent_health_state"
down_revision = "0024_endpoint_action_auto"
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

"""Record the user who initiated endpoint enrollment.

Revision ID: 0019_endpoint_enrollment_owner
Revises: 0018_telephony_calls
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_endpoint_enrollment_owner"
down_revision = "0018_telephony_calls"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite supports ADD COLUMN directly. Avoid recreating endpoint_agents:
    # Alembic's batch column sorter can report a false circular dependency on
    # this table after the enterprise identity migration. The API validates the
    # user reference and the ORM retains the relationship for new schemas.
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("endpoint_agents")}
    if "enrolled_by_user_id" not in columns:
        op.add_column("endpoint_agents", sa.Column("enrolled_by_user_id", sa.Integer(), nullable=True))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("endpoint_agents")}
    if "ix_endpoint_agents_enrolled_by_user_id" not in indexes:
        op.create_index("ix_endpoint_agents_enrolled_by_user_id", "endpoint_agents", ["enrolled_by_user_id"])


def downgrade():
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("endpoint_agents")}
    if "ix_endpoint_agents_enrolled_by_user_id" in indexes:
        op.drop_index("ix_endpoint_agents_enrolled_by_user_id", table_name="endpoint_agents")
    columns = {item["name"] for item in sa.inspect(bind).get_columns("endpoint_agents")}
    if "enrolled_by_user_id" in columns:
        op.drop_column("endpoint_agents", "enrolled_by_user_id")

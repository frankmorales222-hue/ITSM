"""Preserve opened-by and requester context on historical tickets."""
from alembic import op
import sqlalchemy as sa


revision = "0008_requester_snapshot"
down_revision = "0007_form_templates_and_test_form"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("tickets")}
    if "opened_by_id" not in columns:
        op.add_column("tickets", sa.Column("opened_by_id", sa.Integer(), nullable=True))
        op.create_index("ix_tickets_opened_by_id", "tickets", ["opened_by_id"])
    if "requester_snapshot" not in columns:
        op.add_column("tickets", sa.Column("requester_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    bind.execute(sa.text("UPDATE tickets SET opened_by_id = requester_id WHERE opened_by_id IS NULL"))


def downgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("tickets")}
    if "requester_snapshot" in columns:
        op.drop_column("tickets", "requester_snapshot")
    if "opened_by_id" in columns:
        op.drop_index("ix_tickets_opened_by_id", table_name="tickets")
        op.drop_column("tickets", "opened_by_id")

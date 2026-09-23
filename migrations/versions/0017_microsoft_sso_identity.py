"""Add immutable Microsoft Entra identity links.

Revision ID: 0017_microsoft_sso_identity
Revises: 0016_enterprise_agent_identity
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_microsoft_sso_identity"
down_revision = "0016_enterprise_agent_identity"
branch_labels = None
depends_on = None


def upgrade():
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("users")}
    with op.batch_alter_table("users") as batch:
        if "entra_tenant_id" not in columns:
            batch.add_column(sa.Column("entra_tenant_id", sa.String(36), nullable=True))
        if "entra_object_id" not in columns:
            batch.add_column(sa.Column("entra_object_id", sa.String(80), nullable=True))
        if "entra_subject" not in columns:
            batch.add_column(sa.Column("entra_subject", sa.String(255), nullable=True))
    inspector = sa.inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("users")}
    if "ix_users_entra_tenant_id" not in indexes:
        op.create_index("ix_users_entra_tenant_id", "users", ["entra_tenant_id"])
    unique_names = {item.get("name") for item in inspector.get_unique_constraints("users")}
    with op.batch_alter_table("users") as batch:
        if "uq_users_entra_object" not in unique_names:
            batch.create_unique_constraint("uq_users_entra_object", ["entra_tenant_id", "entra_object_id"])
        if "uq_users_entra_subject" not in unique_names:
            batch.create_unique_constraint("uq_users_entra_subject", ["entra_tenant_id", "entra_subject"])


def downgrade():
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_entra_subject", type_="unique")
        batch.drop_constraint("uq_users_entra_object", type_="unique")
    op.drop_index("ix_users_entra_tenant_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("entra_subject")
        batch.drop_column("entra_object_id")
        batch.drop_column("entra_tenant_id")

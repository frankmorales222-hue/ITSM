"""Add secure password reset tokens.

Revision ID: 0014_password_reset_tokens
Revises: 0013_help_desk_experience
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_password_reset_tokens"
down_revision = "0013_help_desk_experience"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "password_reset_tokens" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_ip", sa.String(80), nullable=False, server_default=""),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_organization_id", "password_reset_tokens", ["organization_id"])
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_token_hash", "password_reset_tokens", ["token_hash"])
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])


def downgrade():
    op.drop_table("password_reset_tokens")

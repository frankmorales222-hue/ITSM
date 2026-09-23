"""Add curated Smart Self-Service knowledge and outcome tracking.

Revision ID: 0023_smart_self_service
Revises: 0022_endpoint_remediation
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_smart_self_service"
down_revision = "0022_endpoint_remediation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "knowledge_articles" not in tables:
        op.create_table(
            "knowledge_articles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("title", sa.String(240), nullable=False),
            sa.Column("problem_summary", sa.Text(), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("category", sa.String(100), nullable=False, server_default="General"),
            sa.Column("applicability", sa.JSON(), nullable=False),
            sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("auto_send_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=True),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_knowledge_articles_organization_id", "knowledge_articles", ["organization_id"])
        op.create_index("ix_knowledge_articles_title", "knowledge_articles", ["title"])
        op.create_index("ix_knowledge_articles_category", "knowledge_articles", ["category"])
        op.create_index("ix_knowledge_articles_status", "knowledge_articles", ["status"])
        op.create_index("ix_knowledge_articles_source_ticket_id", "knowledge_articles", ["source_ticket_id"])
        op.create_index("ix_knowledge_articles_org_status_category", "knowledge_articles", ["organization_id", "status", "category"])
    tables = set(sa.inspect(bind).get_table_names())
    if "knowledge_article_versions" not in tables:
        op.create_table(
            "knowledge_article_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("article_id", sa.Integer(), sa.ForeignKey("knowledge_articles.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("article_id", "version", name="uq_knowledge_article_version"),
        )
        op.create_index("ix_knowledge_article_versions_organization_id", "knowledge_article_versions", ["organization_id"])
        op.create_index("ix_knowledge_article_versions_article_id", "knowledge_article_versions", ["article_id"])
    tables = set(sa.inspect(bind).get_table_names())
    if "self_service_attempts" not in tables:
        op.create_table(
            "self_service_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
            sa.Column("article_id", sa.Integer(), sa.ForeignKey("knowledge_articles.id"), nullable=False),
            sa.Column("article_version", sa.Integer(), nullable=False),
            sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("match_reason", sa.JSON(), nullable=False),
            sa.Column("article_snapshot", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="offered"),
            sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("outcome_source", sa.String(30), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("ticket_id", "article_id", "article_version", name="uq_self_service_ticket_article_version"),
        )
        op.create_index("ix_self_service_attempts_organization_id", "self_service_attempts", ["organization_id"])
        op.create_index("ix_self_service_attempts_ticket_id", "self_service_attempts", ["ticket_id"])
        op.create_index("ix_self_service_attempts_article_id", "self_service_attempts", ["article_id"])
        op.create_index("ix_self_service_attempts_status", "self_service_attempts", ["status"])
        op.create_index("ix_self_service_attempts_org_status", "self_service_attempts", ["organization_id", "status"])


def downgrade():
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("self_service_attempts", "knowledge_article_versions", "knowledge_articles"):
        if table in tables:
            op.drop_table(table)

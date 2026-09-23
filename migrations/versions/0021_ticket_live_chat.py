"""Add durable ticket live-chat sessions.

Revision ID: 0021_ticket_live_chat
Revises: 0020_signed_system_updates
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_ticket_live_chat"
down_revision = "0020_signed_system_updates"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "ticket_chat_sessions" not in inspector.get_table_names():
        op.create_table(
            "ticket_chat_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
            sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("accepted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="requested"),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_ticket_chat_sessions_organization_id", "ticket_chat_sessions", ["organization_id"])
        op.create_index("ix_ticket_chat_sessions_ticket_id", "ticket_chat_sessions", ["ticket_id"])
        op.create_index("ix_ticket_chat_sessions_assigned_user_id", "ticket_chat_sessions", ["assigned_user_id"])
        op.create_index("ix_ticket_chat_sessions_status", "ticket_chat_sessions", ["status"])
        op.create_index("ix_ticket_chat_sessions_last_activity_at", "ticket_chat_sessions", ["last_activity_at"])
        op.create_index("ix_ticket_chat_sessions_ticket_status", "ticket_chat_sessions", ["ticket_id", "status"])
        op.create_index("ix_ticket_chat_sessions_assignee_status", "ticket_chat_sessions", ["assigned_user_id", "status"])

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    message_columns = {column["name"] for column in inspector.get_columns("ticket_messages")}
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("ticket_messages") as batch:
            if "chat_session_id" not in message_columns:
                batch.add_column(sa.Column("chat_session_id", sa.Integer(), nullable=True))
            if "client_message_id" not in message_columns:
                batch.add_column(sa.Column("client_message_id", sa.String(length=64), nullable=True))
    else:
        # PostgreSQL upgrades use native, independently recoverable ALTERs. An
        # inline unnamed foreign key inside batch mode failed on real 0020
        # installations even though fresh-schema tests appeared green.
        if "chat_session_id" not in message_columns:
            op.add_column("ticket_messages", sa.Column("chat_session_id", sa.Integer(), nullable=True))
        if "client_message_id" not in message_columns:
            op.add_column("ticket_messages", sa.Column("client_message_id", sa.String(length=64), nullable=True))

    inspector = sa.inspect(bind)
    foreign_keys = inspector.get_foreign_keys("ticket_messages")
    if not any(item.get("referred_table") == "ticket_chat_sessions" and
               item.get("constrained_columns") == ["chat_session_id"] for item in foreign_keys):
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ticket_messages") as batch:
                batch.create_foreign_key("fk_ticket_messages_chat_session_id", "ticket_chat_sessions",
                                         ["chat_session_id"], ["id"])
        else:
            op.create_foreign_key("fk_ticket_messages_chat_session_id", "ticket_messages",
                                  "ticket_chat_sessions", ["chat_session_id"], ["id"])

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("ticket_messages")}
    if "ix_ticket_messages_chat_session_id" not in indexes:
        op.create_index("ix_ticket_messages_chat_session_id", "ticket_messages", ["chat_session_id"])
    uniques = {item["name"] for item in sa.inspect(bind).get_unique_constraints("ticket_messages")}
    if "uq_ticket_message_chat_client" not in uniques:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ticket_messages") as batch:
                batch.create_unique_constraint("uq_ticket_message_chat_client", ["chat_session_id", "client_message_id"])
        else:
            op.create_unique_constraint("uq_ticket_message_chat_client", "ticket_messages",
                                        ["chat_session_id", "client_message_id"])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "ticket_messages" in inspector.get_table_names():
        columns = {item["name"] for item in inspector.get_columns("ticket_messages")}
        uniques = {item["name"] for item in inspector.get_unique_constraints("ticket_messages")}
        indexes = {item["name"] for item in inspector.get_indexes("ticket_messages")}
        foreign_keys = {
            item.get("name")
            for item in inspector.get_foreign_keys("ticket_messages")
            if item.get("constrained_columns") == ["chat_session_id"]
        }
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("ticket_messages") as batch:
                if "uq_ticket_message_chat_client" in uniques:
                    batch.drop_constraint("uq_ticket_message_chat_client", type_="unique")
                if "fk_ticket_messages_chat_session_id" in foreign_keys:
                    batch.drop_constraint("fk_ticket_messages_chat_session_id", type_="foreignkey")
                if "ix_ticket_messages_chat_session_id" in indexes:
                    batch.drop_index("ix_ticket_messages_chat_session_id")
                if "client_message_id" in columns:
                    batch.drop_column("client_message_id")
                if "chat_session_id" in columns:
                    batch.drop_column("chat_session_id")
        else:
            if "uq_ticket_message_chat_client" in uniques:
                op.drop_constraint("uq_ticket_message_chat_client", "ticket_messages", type_="unique")
            if "fk_ticket_messages_chat_session_id" in foreign_keys:
                op.drop_constraint("fk_ticket_messages_chat_session_id", "ticket_messages", type_="foreignkey")
            if "ix_ticket_messages_chat_session_id" in indexes:
                op.drop_index("ix_ticket_messages_chat_session_id", table_name="ticket_messages")
            if "client_message_id" in columns:
                op.drop_column("ticket_messages", "client_message_id")
            if "chat_session_id" in columns:
                op.drop_column("ticket_messages", "chat_session_id")
    if "ticket_chat_sessions" in sa.inspect(bind).get_table_names():
        op.drop_table("ticket_chat_sessions")

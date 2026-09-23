"""Add configurable Help Desk Settings and standard role descriptions.

Revision ID: 0013_help_desk_experience
Revises: 0012_tasks_and_closure
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "0013_help_desk_experience"
down_revision = "0012_tasks_and_closure"
branch_labels = None
depends_on = None

DEFAULTS = {
    "help_desk_title": "Help Desk",
    "tickets_per_page": 50,
    "auto_reload_seconds": 30,
    "autoclose_days": 5,
    "reply_form_position": "bottom",
    "conversation_order": "oldest_first",
    "customer_portal": "required_login",
    "session_minutes": 480,
    "auto_assign": True,
    "allow_reopen": True,
    "require_email": True,
    "require_subject": True,
    "require_message": True,
    "time_tracking": True,
    "ticket_ratings": True,
    "attachments_enabled": True,
    "max_files_per_reply": 10,
    "max_file_size_mb": 25,
    "allowed_file_types": ["png", "jpg", "jpeg", "gif", "pdf", "docx", "xlsx", "csv", "txt", "zip"],
    "login_attempts": 5,
    "lockout_minutes": 15,
}

ROLE_DESCRIPTIONS = {
    "end_user": "Requester: create requests and view only their own tickets.",
    "technician": "Technician: work assigned and team tickets; view linked assets.",
    "team_lead": "Team Lead: technician access plus team assignment and workload oversight.",
    "manager": "Service Desk Manager: organization-wide reporting, approvals, and service oversight.",
    "admin": "Administrator: full configuration, security, integrations, and service management.",
    "auditor": "Auditor: read-only tickets, reports, exports, and audit evidence.",
}

def upgrade():
    bind = op.get_bind()
    for organization_id in bind.execute(sa.text("SELECT id FROM organizations")).scalars():
        exists = bind.execute(sa.text("SELECT id FROM config_items WHERE organization_id=:o AND section='help_desk'"), {"o": organization_id}).scalar()
        if not exists:
            bind.execute(sa.text("INSERT INTO config_items (organization_id,section,name,value,description,sensitive,updated_at) VALUES (:o,'help_desk','Help Desk Settings',:v,'Ticket behavior, staff workflow, customer access, security, and attachment limits.',FALSE,CURRENT_TIMESTAMP)"), {"o": organization_id, "v": json.dumps(DEFAULTS)})
        for key, description in ROLE_DESCRIPTIONS.items():
            bind.execute(sa.text("UPDATE role_definitions SET description=:d, updated_at=CURRENT_TIMESTAMP WHERE organization_id=:o AND key=:k AND system=TRUE"), {"o": organization_id, "k": key, "d": description})

def downgrade():
    op.execute(sa.text("DELETE FROM config_items WHERE section='help_desk' AND name='Help Desk Settings'"))

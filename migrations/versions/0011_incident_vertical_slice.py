"""Add the configurable incident submission vertical slice.

Revision ID: 0011_incident_vertical_slice
Revises: 0010_administration_control_plane
"""
from alembic import op
import json
import sqlalchemy as sa

revision = "0011_incident_vertical_slice"
down_revision = "0010_administration_control_plane"
branch_labels = None
depends_on = None


def j(value):
    return sa.text("'" + json.dumps(value).replace("'", "''") + "'")


def upgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    ticket_columns = {column["name"] for column in sa.inspect(bind).get_columns("tickets")}
    form_columns = {column["name"] for column in sa.inspect(bind).get_columns("form_definitions")}
    if {"form_definition_versions", "ticket_attachments"}.issubset(tables) and "mode" in ticket_columns and "form_type" in form_columns:
        return
    for column in [
        sa.Column("mode", sa.String(60), nullable=False, server_default="Web Form"),
        sa.Column("level", sa.String(40), nullable=False, server_default="Tier 1"),
        sa.Column("impact_details", sa.Text(), nullable=False, server_default=""),
        sa.Column("site_location", sa.String(140), nullable=False, server_default=""),
        sa.Column("item", sa.String(140), nullable=True),
        sa.Column("emails_to_notify", sa.JSON(), nullable=False, server_default=j([])),
        sa.Column("calculated_priority", sa.String(20), nullable=False, server_default="Medium"),
        sa.Column("priority_source", sa.String(30), nullable=False, server_default="calculated"),
        sa.Column("routing_trace", sa.JSON(), nullable=False, server_default=j([])),
        sa.Column("sla_policy_key", sa.String(80), nullable=False, server_default=""),
        sa.Column("sla_explanation", sa.String(500), nullable=False, server_default=""),
    ]:
        op.add_column("tickets", column)

    for column in [
        sa.Column("form_type", sa.String(40), nullable=False, server_default="service_request"),
        sa.Column("portal_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("default_for_type", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requester_layout", sa.JSON(), nullable=False, server_default=j([])),
        sa.Column("technician_layout", sa.JSON(), nullable=False, server_default=j([])),
        sa.Column("lifecycle_state", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]:
        op.add_column("form_definitions", column)
    for name, columns in [
        ("ix_form_definitions_form_type", ["form_type"]),
        ("ix_form_definitions_portal_visible", ["portal_visible"]),
        ("ix_form_definitions_default_for_type", ["default_for_type"]),
        ("ix_form_definitions_lifecycle_state", ["lifecycle_state"]),
    ]:
        op.create_index(name, "form_definitions", columns)

    op.create_table(
        "form_definition_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("form_definition_id", sa.Integer(), sa.ForeignKey("form_definitions.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default=j({})),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("organization_id", "form_definition_id", "version"),
    )
    op.create_index("ix_form_definition_versions_form_definition_id", "form_definition_versions", ["form_definition_id"])

    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_name", sa.String(255), nullable=False, unique=True),
        sa.Column("content_type", sa.String(120), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_ticket_attachments_ticket_id", "ticket_attachments", ["ticket_id"])

    taxonomy = {
        "request_types": [
            {"key": "incident", "name": "Incident"},
            {"key": "information", "name": "Request for Information"},
            {"key": "service_request", "name": "Service Request"},
        ],
        "modes": [{"key": x.lower().replace(" ", "_"), "name": x} for x in ["Email", "Live Chat", "Mobile Application", "Phone Call", "Web Form"]],
        "levels": [{"key": f"tier_{n}", "name": f"Tier {n}"} for n in range(1, 5)],
        "impacts": [{"key": x.lower(), "name": x} for x in ["Low", "Medium", "High"]],
        "urgencies": [{"key": x.lower(), "name": x} for x in ["Low", "Medium", "High"]],
        "priorities": [{"key": x.lower(), "name": x} for x in ["Critical", "High", "Medium", "Normal", "Low"]],
        "statuses": [
            {"key": "open", "name": "Open", "description": "Newly submitted work", "color": "#397da1", "lifecycle": "active", "sla_runs": True, "order": 10, "active": True},
            {"key": "in_progress", "name": "In Progress", "description": "Work is underway", "color": "#176453", "lifecycle": "active", "sla_runs": True, "order": 20, "active": True},
            {"key": "on_hold", "name": "On Hold", "description": "Temporarily paused", "color": "#e4a934", "lifecycle": "paused", "sla_runs": False, "order": 30, "active": True},
            {"key": "pending_verification", "name": "Pending Verification", "description": "Awaiting confirmation", "color": "#7867a5", "lifecycle": "paused", "sla_runs": False, "order": 40, "active": True},
            {"key": "staging", "name": "Staging", "description": "Fix is being prepared", "color": "#6b7d8b", "lifecycle": "active", "sla_runs": True, "order": 50, "active": True},
            {"key": "resolved", "name": "Resolved", "description": "Service restored", "color": "#41906e", "lifecycle": "resolved", "sla_runs": False, "order": 60, "active": True},
            {"key": "closed", "name": "Closed", "description": "Work completed", "color": "#56615d", "lifecycle": "closed", "sla_runs": False, "order": 70, "active": True},
            {"key": "canceled", "name": "Canceled", "description": "Request withdrawn", "color": "#9a7569", "lifecycle": "closed", "sla_runs": False, "order": 80, "active": True},
            {"key": "rejected", "name": "Rejected", "description": "Request was not accepted", "color": "#bc382d", "lifecycle": "closed", "sla_runs": False, "order": 90, "active": True},
        ],
    }
    matrix = {
        "priorities": ["Critical", "High", "Medium", "Normal", "Low"],
        "cells": {
            "High|High": "Critical", "High|Medium": "High", "High|Low": "Medium",
            "Medium|High": "High", "Medium|Medium": "Normal", "Medium|Low": "Low",
            "Low|High": "Medium", "Low|Medium": "Low", "Low|Low": "Low",
        },
    }
    slas = {"policies": [
        {"key": "critical", "name": "Critical", "priority": "Critical", "response_minutes": 15, "resolution_minutes": 60, "calendar": "default_business_hours", "pause_statuses": ["On Hold", "Pending Verification"], "active": True},
        {"key": "high", "name": "High", "priority": "High", "response_minutes": 30, "resolution_minutes": 120, "calendar": "default_business_hours", "pause_statuses": ["On Hold", "Pending Verification"], "active": True},
        {"key": "medium", "name": "Medium", "priority": "Medium", "response_minutes": 60, "resolution_minutes": 240, "calendar": "default_business_hours", "pause_statuses": ["On Hold", "Pending Verification"], "active": True},
        {"key": "normal", "name": "Normal", "priority": "Normal", "response_minutes": 120, "resolution_minutes": 480, "calendar": "default_business_hours", "pause_statuses": ["On Hold", "Pending Verification"], "active": True},
        {"key": "low", "name": "Low", "priority": "Low", "response_minutes": 240, "resolution_minutes": 960, "calendar": "default_business_hours", "pause_statuses": ["On Hold", "Pending Verification"], "active": True},
    ]}
    fields = [
        {"id": "incident-classification", "key": "", "label": "Classification", "type": "section", "required": False, "help": "Describe how the incident entered the service desk.", "options": [], "placeholder": "", "width": "full", "icon": "tag", "max_length": None, "visibility": "visible", "read_only": False, "show_when": None},
        {"id": "incident-request-details", "key": "", "label": "Request details", "type": "section", "required": False, "help": "Explain the interruption and its business effect.", "options": [], "placeholder": "", "width": "full", "icon": "document", "max_length": None, "visibility": "visible", "read_only": False, "show_when": None},
        {"id": "incident-assignment", "key": "", "label": "Assignment and categorization", "type": "section", "required": False, "help": "Routing is calculated from these values.", "options": [], "placeholder": "", "width": "full", "icon": "route", "max_length": None, "visibility": "visible", "read_only": False, "show_when": None},
    ]
    bind = op.get_bind()
    for org in bind.execute(sa.text("SELECT id FROM organizations")).scalars():
        for section, name, value, description in [
            ("incident_taxonomy", "Incident classification values", taxonomy, "Request types, modes, levels, impacts, urgencies, priorities, and lifecycle-aware statuses."),
            ("incident_priority_matrix", "Incident impact and urgency matrix", matrix, "Every impact and urgency combination maps to a configurable priority."),
            ("incident_sla", "Incident SLA policies", slas, "Priority-based response and resolution targets stored in minutes."),
        ]:
            bind.execute(sa.text("INSERT INTO config_items (organization_id,section,name,value,description,sensitive,updated_at) VALUES (:o,:s,:n,:v,:d,FALSE,CURRENT_TIMESTAMP)"), {"o": org, "s": section, "n": name, "v": json.dumps(value), "d": description})
        existing = bind.execute(sa.text("SELECT id FROM form_definitions WHERE organization_id=:o AND slug='new-incident'"), {"o": org}).scalar()
        if not existing:
            bind.execute(sa.text("INSERT INTO form_definitions (organization_id,slug,name,description,category,icon,fields,active,is_template,published,form_type,portal_visible,default_for_type,requester_layout,technician_layout,lifecycle_state,version,created_at,updated_at) VALUES (:o,'new-incident','New Incident','Report an interruption or degraded service.','General','incident',:f,TRUE,FALSE,TRUE,'incident',TRUE,TRUE,:r,:t,'published',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o": org, "f": json.dumps(fields), "r": json.dumps(["Classification", "Requester and asset context", "Categorization", "Request details"]), "t": json.dumps(["Classification", "Requester and asset context", "Assignment", "Categorization", "Request details", "Resolution"])})
        for index, name in enumerate(["Access and Identity", "Applications", "Email and Collaboration", "Hardware", "Medical Devices", "Network and Connectivity", "Operating Systems", "Printers", "Security", "Telephony"], 1):
            if not bind.execute(sa.text("SELECT id FROM service_categories WHERE organization_id=:o AND parent_id IS NULL AND name=:n"), {"o": org, "n": name}).scalar():
                bind.execute(sa.text("INSERT INTO service_categories (organization_id,name,parent_id,level,description,sort_order,configuration,active,version,created_at,updated_at) VALUES (:o,:n,NULL,'category','',:s,'{}',TRUE,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o": org, "n": name, "s": index * 10})

        hardware_id = bind.execute(sa.text("SELECT id FROM service_categories WHERE organization_id=:o AND parent_id IS NULL AND name='Hardware'"), {"o": org}).scalar()
        endpoint_id = bind.execute(sa.text("SELECT id FROM service_categories WHERE organization_id=:o AND parent_id=:p AND name='Endpoint Devices'"), {"o": org, "p": hardware_id}).scalar()
        if hardware_id and not endpoint_id:
            bind.execute(sa.text("INSERT INTO service_categories (organization_id,name,parent_id,level,description,sort_order,configuration,active,version,created_at,updated_at) VALUES (:o,'Endpoint Devices',:p,'subcategory','Computers, displays, docks, and related endpoints',10,'{}',TRUE,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o": org, "p": hardware_id})
            endpoint_id = bind.execute(sa.text("SELECT id FROM service_categories WHERE organization_id=:o AND parent_id=:p AND name='Endpoint Devices'"), {"o": org, "p": hardware_id}).scalar()
        if endpoint_id:
            for item_order, item_name in enumerate(["Laptop", "Desktop", "Monitor", "Docking Station"], 1):
                if not bind.execute(sa.text("SELECT id FROM service_categories WHERE organization_id=:o AND parent_id=:p AND name=:n"), {"o": org, "p": endpoint_id, "n": item_name}).scalar():
                    bind.execute(sa.text("INSERT INTO service_categories (organization_id,name,parent_id,level,description,sort_order,configuration,active,version,created_at,updated_at) VALUES (:o,:n,:p,'item','',:s,'{}',TRUE,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o": org, "p": endpoint_id, "n": item_name, "s": item_order * 10})

        queue_row = bind.execute(sa.text("SELECT q.id, q.team_id FROM support_queues q WHERE q.organization_id=:o AND q.name='Devices' AND q.active=TRUE"), {"o": org}).first()
        if queue_row and not bind.execute(sa.text("SELECT id FROM routing_rules WHERE organization_id=:o AND name='Route hardware incidents'"), {"o": org}).scalar():
            conditions = {"logic": "AND", "conditions": [{"field": "category", "operator": "equals", "value": "Hardware"}]}
            actions = {"queue_id": queue_row.id, "team_id": queue_row.team_id, "assignment_method": "least_active"}
            bind.execute(sa.text("INSERT INTO routing_rules (organization_id,name,priority_order,conditions,actions,active,description,trigger,status,stop_processing,overwrite_existing,reevaluate_fields,match_count,version,created_at,updated_at) VALUES (:o,'Route hardware incidents',10,:c,:a,TRUE,'Send hardware incidents to the endpoint support queue','ticket.created','active',TRUE,FALSE,'[]',0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {"o": org, "c": json.dumps(conditions), "a": json.dumps(actions)})


def downgrade():
    op.drop_table("ticket_attachments")
    op.drop_table("form_definition_versions")
    for name in ["ix_form_definitions_lifecycle_state", "ix_form_definitions_default_for_type", "ix_form_definitions_portal_visible", "ix_form_definitions_form_type"]:
        op.drop_index(name, table_name="form_definitions")
    for column in ["version", "archived_at", "lifecycle_state", "technician_layout", "requester_layout", "default_for_type", "portal_visible", "form_type"]:
        op.drop_column("form_definitions", column)
    for column in ["sla_explanation", "sla_policy_key", "routing_trace", "priority_source", "calculated_priority", "emails_to_notify", "item", "site_location", "impact_details", "level", "mode"]:
        op.drop_column("tickets", column)

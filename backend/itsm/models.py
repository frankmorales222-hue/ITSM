import enum
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship
from .database import Base


def now():
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    END_USER = "end_user"
    TECHNICIAN = "technician"
    TEAM_LEAD = "team_lead"
    MANAGER = "manager"
    ADMIN = "admin"
    AUDITOR = "auditor"


class TicketStatus(str, enum.Enum):
    NEW = "New"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    WAITING_USER = "Waiting on User"
    WAITING_VENDOR = "Waiting on Vendor"
    WAITING_APPROVAL = "Waiting on Approval"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    CANCELLED = "Cancelled"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class OrganizationMixin:
    """Marks records that must always be isolated to one organization."""
    __tenant_scoped__ = True

    @declared_attr
    def organization_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    support_email: Mapped[str] = mapped_column(String(255), default="")
    support_phone: Mapped[str] = mapped_column(String(40), default="")
    logo_url: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Department(OrganizationMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Location(OrganizationMixin, Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Team(OrganizationMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    queue_name: Mapped[str] = mapped_column(String(100))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    skills: Mapped[list] = mapped_column(JSON, default=list)


class User(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.END_USER, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability: Mapped[str] = mapped_column(String(30), default="Available")
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    ringcentral_extension_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ringcentral_extension_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    team: Mapped[Team | None] = relationship()


class Employee(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("organization_id", "employee_number"), UniqueConstraint("organization_id", "work_email"))
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_number: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    preferred_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    work_email: Mapped[str] = mapped_column(String(255))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    job_title: Mapped[str] = mapped_column(String(120), default="Employee")
    employment_status: Mapped[str] = mapped_column(String(40), default="Active")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    support_region: Mapped[str] = mapped_column(String(60), default="East")
    vip: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(30), default="Manual")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), unique=True, nullable=True)
    department: Mapped[Department | None] = relationship()
    location: Mapped[Location | None] = relationship()


class Asset(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("organization_id", "asset_tag"),
                      UniqueConstraint("organization_id", "hostname"), UniqueConstraint("organization_id", "serial_number"),
                      Index("uq_assets_org_source_source_id", "organization_id", "source", "source_id", unique=True))
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(60), index=True)
    hostname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160), default="")
    category: Mapped[str] = mapped_column(String(80), default="Computer")
    asset_type: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(40), default="Stock")
    condition: Mapped[str] = mapped_column(String(40), default="Good")
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    assigned_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_expiration: Mapped[date | None] = mapped_column(Date, nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(160), nullable=True)
    company: Mapped[str | None] = mapped_column(String(120), nullable=True)
    project: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="Manual")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    extended_data: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned_employee: Mapped[Employee | None] = relationship()
    location: Mapped[Location | None] = relationship()
    department: Mapped[Department | None] = relationship()


class AssetHistory(Base):
    __tablename__ = "asset_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Sequence(Base):
    __tablename__ = "sequences"
    prefix: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


class Ticket(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "tickets"
    __table_args__ = (UniqueConstraint("organization_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(20), index=True)
    request_type: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str] = mapped_column(Text)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.NEW, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", index=True)
    impact: Mapped[str] = mapped_column(String(20), default="Medium")
    urgency: Mapped[str] = mapped_column(String(20), default="Medium")
    priority_override_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="General")
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_action_owner: Mapped[str] = mapped_column(String(120), default="IT")
    next_action: Mapped[str] = mapped_column(String(240), default="Initial triage")
    waiting_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolution_due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    restricted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reopened_count: Mapped[int] = mapped_column(Integer, default=0)
    route_reason: Mapped[str] = mapped_column(String(240), default="Default queue fallback")
    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    employee: Mapped[Employee | None] = relationship(foreign_keys=[employee_id])
    assigned_user: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    team: Mapped[Team] = relationship()
    assets: Mapped[list[Asset]] = relationship(secondary="ticket_assets")
    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketAsset(Base):
    __tablename__ = "ticket_assets"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="public")
    source: Mapped[str] = mapped_column(String(30), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship()


class TicketHistory(Base):
    __tablename__ = "ticket_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __tenant_scoped__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    record_type: Mapped[str] = mapped_column(String(80), index=True)
    record_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class EmailMessage(OrganizationMixin, Base):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("organization_id", "message_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(500), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    sender: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(500))
    attachment_metadata: Mapped[list] = mapped_column(JSON, default=list)
    processing_status: Mapped[str] = mapped_column(String(30), default="processed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(OrganizationMixin, Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    event: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(30), default="in_app")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AutomationFailure(OrganizationMixin, Base):
    __tablename__ = "automation_failures"
    id: Mapped[int] = mapped_column(primary_key=True)
    failure_type: Mapped[str] = mapped_column(String(100), index=True)
    summary: Mapped[str] = mapped_column(String(500))
    safe_details: Mapped[dict] = mapped_column(JSON, default=dict)
    related_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Open")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Announcement(OrganizationMixin, Base):
    __tablename__ = "announcements"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30), default="info")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Feedback(OrganizationMixin, Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    feedback_type: Mapped[str] = mapped_column(String(60))
    current_page: Mapped[str] = mapped_column(String(240))
    user_role: Mapped[str] = mapped_column(String(40))
    app_version: Mapped[str] = mapped_column(String(30))
    related_record_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ConfigItem(OrganizationMixin, Base):
    __tablename__ = "config_items"
    __table_args__ = (UniqueConstraint("organization_id", "section", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    section: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(String(500), default="")
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class IntegrationSecret(OrganizationMixin, Base):
    __tablename__ = "integration_secrets"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(100))
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

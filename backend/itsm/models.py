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
    OPEN = "Open"
    NEW = "New"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    PENDING_VERIFICATION = "Pending Verification"
    STAGING = "Staging"
    WAITING_USER = "Waiting on User"
    WAITING_VENDOR = "Waiting on Vendor"
    WAITING_APPROVAL = "Waiting on Approval"
    RESOLVED = "Resolved"
    CLOSED = "Closed"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"


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
    key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    # Application-validated references avoid a users<->teams DDL cycle on SQLite.
    lead_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backup_lead_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region: Mapped[str] = mapped_column(String(80), default="")
    supported_locations: Mapped[list] = mapped_column(JSON, default=list)
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    business_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    supported_services: Mapped[list] = mapped_column(JSON, default=list)
    supported_categories: Mapped[list] = mapped_column(JSON, default=list)
    default_capacity: Mapped[int] = mapped_column(Integer, default=10)
    escalation_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TeamMembership(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("organization_id", "team_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    membership_role: Mapped[str] = mapped_column(String(30), default="member")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    capacity_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupportQueue(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "support_queues"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    assignment_strategy: Mapped[str] = mapped_column(String(60), default="round_robin")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    priority_order: Mapped[int] = mapped_column(Integer, default=100)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    team: Mapped[Team] = relationship()


class QueueTeamEligibility(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "queue_team_eligibility"
    __table_args__ = (UniqueConstraint("organization_id", "queue_id", "team_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    queue_id: Mapped[int] = mapped_column(ForeignKey("support_queues.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    eligibility_priority: Mapped[int] = mapped_column(Integer, default=100)
    weight: Mapped[int] = mapped_column(Integer, default=100)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict)
    capacity_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class User(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("entra_tenant_id", "entra_object_id", name="uq_users_entra_object"),
        UniqueConstraint("entra_tenant_id", "entra_subject", name="uq_users_entra_subject"),
    )
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
    alternate_email: Mapped[str] = mapped_column(String(255), default="")
    employee_number: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    job_title: Mapped[str] = mapped_column(String(120), default="")
    department_name: Mapped[str] = mapped_column(String(120), default="")
    location_name: Mapped[str] = mapped_column(String(120), default="")
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    preferred_language: Mapped[str] = mapped_column(String(20), default="en")
    notification_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    auth_source: Mapped[str] = mapped_column(String(40), default="Local")
    # Microsoft identities are linked by immutable tenant/object identifiers.
    # Email remains a discovery attribute and is never the durable identity key.
    entra_tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    entra_object_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entra_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_source: Mapped[str] = mapped_column(String(40), default="Local role catalog")
    team_source: Mapped[str] = mapped_column(String(40), default="Direct assignment")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    team: Mapped[Team | None] = relationship(foreign_keys=[team_id])


class RoleDefinition(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "role_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "key"), UniqueConstraint("organization_id", "name"))
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    parent_role_id: Mapped[int | None] = mapped_column(ForeignKey("role_definitions.id"), nullable=True)
    system: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class UserRoleAssignment(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "user_role_assignments"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "role_definition_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_definition_id: Mapped[int] = mapped_column(ForeignKey("role_definitions.id"), index=True)
    source: Mapped[str] = mapped_column(String(40), default="Direct")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class GroupType(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "group_types"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    icon: Mapped[str] = mapped_column(String(40), default="group")
    color: Mapped[str] = mapped_column(String(20), default="#176453")
    purpose: Mapped[str] = mapped_column(String(200), default="")
    allowed_uses: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class UserGroup(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "user_groups"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    group_type: Mapped[str] = mapped_column(String(60), default="Custom")
    description: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(40), default="Local")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    group_type_id: Mapped[int | None] = mapped_column(ForeignKey("group_types.id"), nullable=True)
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), default="")
    region: Mapped[str] = mapped_column(String(80), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="America/New_York")
    escalation_contact: Mapped[str] = mapped_column(String(255), default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class UserGroupMembership(Base):
    __tablename__ = "user_group_memberships"
    group_id: Mapped[int] = mapped_column(ForeignKey("user_groups.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    membership_role: Mapped[str] = mapped_column(String(30), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ServiceCategory(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "service_categories"
    __table_args__ = (UniqueConstraint("organization_id", "parent_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("service_categories.id"), nullable=True, index=True)
    level: Mapped[str] = mapped_column(String(30), default="category")
    description: Mapped[str] = mapped_column(String(500), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Employee(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("organization_id", "employee_number"), UniqueConstraint("organization_id", "work_email"))
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_number: Mapped[str] = mapped_column(String(40))
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    preferred_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    work_email: Mapped[str] = mapped_column(String(255))
    alternate_emails: Mapped[list] = mapped_column(JSON, default=list)
    account_name: Mapped[str] = mapped_column(String(120), default="", index=True)
    directory_object_id: Mapped[str] = mapped_column(String(80), default="", index=True)
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


class AgentEnrollmentToken(OrganizationMixin, Base):
    __tablename__ = "agent_enrollment_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="Windows endpoint enrollment")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EndpointAgent(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "endpoint_agents"
    __table_args__ = (
        UniqueConstraint("organization_id", "device_id"),
        UniqueConstraint("credential_hash"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    credential_hash: Mapped[str] = mapped_column(String(64), index=True)
    hostname: Mapped[str] = mapped_column(String(120), default="")
    agent_version: Mapped[str] = mapped_column(String(40), default="")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="Enrolled")
    observed_user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_user: Mapped[dict] = mapped_column(JSON, default=dict)
    identity_match_method: Mapped[str] = mapped_column(String(40), default="")
    matched_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True, index=True)
    enrolled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    consecutive_user_observations: Mapped[int] = mapped_column(Integer, default=0)
    assignment_state: Mapped[str] = mapped_column(String(40), default="No observation")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_inventory_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str] = mapped_column(String(80), default="")
    last_error: Mapped[str] = mapped_column(String(500), default="")
    asset: Mapped[Asset | None] = relationship()


class EndpointAction(OrganizationMixin, Base, TimestampMixin):
    """Audited remediation dispatched to an endpoint agent."""
    __tablename__ = "endpoint_actions"
    __table_args__ = (
        Index("ix_endpoint_actions_agent_status", "agent_id", "status"),
        Index("ix_endpoint_actions_ticket_created", "ticket_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("endpoint_agents.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(40), index=True)
    target: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="Pending approval", index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_approval_reason: Mapped[str] = mapped_column(String(255), default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str] = mapped_column(String(500), default="")
    agent: Mapped[EndpointAgent] = relationship()


class AssetInventorySnapshot(OrganizationMixin, Base):
    __tablename__ = "asset_inventory_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("endpoint_agents.id"), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    inventory_hash: Mapped[str] = mapped_column(String(64), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    inventory: Mapped[dict] = mapped_column(JSON, default=dict)


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
    opened_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.NEW, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", index=True)
    impact: Mapped[str] = mapped_column(String(20), default="Medium")
    urgency: Mapped[str] = mapped_column(String(20), default="Medium")
    mode: Mapped[str] = mapped_column(String(60), default="Web Form")
    level: Mapped[str] = mapped_column(String(40), default="Tier 1")
    impact_details: Mapped[str] = mapped_column(Text, default="")
    site_location: Mapped[str] = mapped_column(String(140), default="")
    item: Mapped[str | None] = mapped_column(String(140), nullable=True)
    emails_to_notify: Mapped[list] = mapped_column(JSON, default=list)
    calculated_priority: Mapped[str] = mapped_column(String(20), default="Medium")
    priority_source: Mapped[str] = mapped_column(String(30), default="calculated")
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
    routing_trace: Mapped[list] = mapped_column(JSON, default=list)
    sla_policy_key: Mapped[str] = mapped_column(String(80), default="")
    sla_explanation: Mapped[str] = mapped_column(String(500), default="")
    form_definition_id: Mapped[int | None] = mapped_column(ForeignKey("form_definitions.id"), nullable=True, index=True)
    custom_data: Mapped[dict] = mapped_column(JSON, default=dict)
    requester_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    opened_by: Mapped[User | None] = relationship(foreign_keys=[opened_by_id])
    employee: Mapped[Employee | None] = relationship(foreign_keys=[employee_id])
    assigned_user: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    team: Mapped[Team] = relationship()
    assets: Mapped[list[Asset]] = relationship(secondary="ticket_assets")
    messages: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")
    attachments: Mapped[list["TicketAttachment"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")


class TicketAsset(Base):
    __tablename__ = "ticket_assets"
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True)


class TicketAttachment(OrganizationMixin, Base):
    __tablename__ = "ticket_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ticket: Mapped[Ticket] = relationship(back_populates="attachments")


class TicketChatSession(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "ticket_chat_sessions"
    __table_args__ = (
        Index("ix_ticket_chat_sessions_ticket_status", "ticket_id", "status"),
        Index("ix_ticket_chat_sessions_assignee_status", "assigned_user_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    ticket: Mapped[Ticket] = relationship()


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        UniqueConstraint("chat_session_id", "client_message_id", name="uq_ticket_message_chat_client"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    chat_session_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_chat_sessions.id"), nullable=True, index=True)
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class PasswordResetToken(OrganizationMixin, Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    requested_ip: Mapped[str] = mapped_column(String(80), default="")
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


class KnowledgeArticle(OrganizationMixin, Base, TimestampMixin):
    """Curated, tenant-owned troubleshooting guidance used by Smart Self-Service."""
    __tablename__ = "knowledge_articles"
    __table_args__ = (
        Index("ix_knowledge_articles_org_status_category", "organization_id", "status", "category"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(240), index=True)
    problem_summary: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(100), default="General", index=True)
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    auto_send_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeArticleVersion(OrganizationMixin, Base):
    __tablename__ = "knowledge_article_versions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_knowledge_article_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SelfServiceAttempt(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "self_service_attempts"
    __table_args__ = (
        UniqueConstraint("ticket_id", "article_id", "article_version", name="uq_self_service_ticket_article_version"),
        Index("ix_self_service_attempts_org_status", "organization_id", "status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id"), index=True)
    article_version: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer, default=0)
    match_reason: Mapped[dict] = mapped_column(JSON, default=dict)
    article_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="offered", index=True)
    offered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_source: Mapped[str | None] = mapped_column(String(30), nullable=True)


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


class RoutingRule(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "routing_rules"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    priority_order: Mapped[int] = mapped_column(Integer, default=100, index=True)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    trigger: Mapped[str] = mapped_column(String(80), default="ticket.created", index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    stop_processing: Mapped[bool] = mapped_column(Boolean, default=True)
    overwrite_existing: Mapped[bool] = mapped_column(Boolean, default=False)
    reevaluate_fields: Mapped[list] = mapped_column(JSON, default=list)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    last_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class RoutingRuleVersion(OrganizationMixin, Base):
    __tablename__ = "routing_rule_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    routing_rule_id: Mapped[int] = mapped_column(ForeignKey("routing_rules.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotificationRule(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "notification_rules"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    trigger: Mapped[str] = mapped_column(String(80), index=True)
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    template: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    classification: Mapped[str] = mapped_column(String(30), default="customer", index=True)
    locale: Mapped[str] = mapped_column(String(20), default="en")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    rate_limit: Mapped[dict] = mapped_column(JSON, default=dict)
    suppress_actor: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class EventCatalogItem(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "event_catalog"
    __table_args__ = (UniqueConstraint("organization_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(60), default="ticket")
    reportable: Mapped[bool] = mapped_column(Boolean, default=True)
    custom: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DomainEvent(OrganizationMixin, Base):
    __tablename__ = "domain_events"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class IntegrationConnection(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("organization_id", "kind", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(140))
    provider: Mapped[str] = mapped_column(String(80), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="Disabled")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    secret_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class IntegrationLog(OrganizationMixin, Base):
    __tablename__ = "integration_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("integration_connections.id"), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    event: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class TelephonyCall(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "telephony_calls"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "session_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("integration_connections.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="RingCentral", index=True)
    session_id: Mapped[str] = mapped_column(String(180), index=True)
    event_id: Mapped[str] = mapped_column(String(180), default="")
    direction: Mapped[str] = mapped_column(String(20), default="Inbound")
    caller_number: Mapped[str] = mapped_column(String(60), default="")
    destination_number: Mapped[str] = mapped_column(String(60), default="")
    queue_id: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(40), default="Received")
    answered_extension_id: Mapped[str] = mapped_column(String(100), default="")
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    safe_payload: Mapped[dict] = mapped_column(JSON, default=dict)


class IntegrationSecret(OrganizationMixin, Base):
    __tablename__ = "integration_secrets"
    __table_args__ = (UniqueConstraint("organization_id", "provider", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(100))
    encrypted_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class FormDefinition(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "form_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(1000), default="")
    category: Mapped[str] = mapped_column(String(100), default="General")
    icon: Mapped[str] = mapped_column(String(30), default="form")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    form_type: Mapped[str] = mapped_column(String(40), default="service_request", index=True)
    portal_visible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    default_for_type: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    requester_layout: Mapped[list] = mapped_column(JSON, default=list)
    technician_layout: Mapped[list] = mapped_column(JSON, default=list)
    lifecycle_state: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FormDefinitionVersion(OrganizationMixin, Base):
    __tablename__ = "form_definition_versions"
    __table_args__ = (UniqueConstraint("organization_id", "form_definition_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    form_definition_id: Mapped[int] = mapped_column(ForeignKey("form_definitions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApprovalWorkflow(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "approval_workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    form_definition_id: Mapped[int] = mapped_column(ForeignKey("form_definitions.id"), unique=True, index=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    task_template_ids: Mapped[list] = mapped_column(JSON, default=list)
    closure_requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TaskTemplate(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "task_templates"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(String(1000), default="")
    items: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TicketChecklist(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "ticket_checklists"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    task_template_id: Mapped[int | None] = mapped_column(ForeignKey("task_templates.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    items: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)
    required_for_closure: Mapped[bool] = mapped_column(Boolean, default=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "approval_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), unique=True, index=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("approval_workflows.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    current_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="Pending", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalDecision(OrganizationMixin, Base):
    __tablename__ = "approval_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    approval_request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id"), index=True)
    step_index: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    decision: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReportDefinition(OrganizationMixin, Base, TimestampMixin):
    __tablename__ = "report_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(1000), default="")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SystemUpdate(Base):
    """Append-only release history for signed offline server updates."""
    __tablename__ = "system_updates"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    previous_version: Mapped[str] = mapped_column(String(30), default="")
    filename: Mapped[str] = mapped_column(String(255))
    package_sha256: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="Validated", index=True)
    message: Mapped[str] = mapped_column(String(1000), default="")
    staged_path: Mapped[str] = mapped_column(String(1000), default="")
    backup_path: Mapped[str] = mapped_column(String(1000), default="")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    installation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

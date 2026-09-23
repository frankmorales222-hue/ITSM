from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class PasswordResetIn(BaseModel):
    token: str = Field(min_length=32, max_length=300)
    new_password: str


class TicketCreate(BaseModel):
    request_type: str
    subject: str = Field(min_length=4, max_length=240)
    description: str = Field(min_length=10, max_length=20000)
    asset_ids: list[int] = []
    impact: str = "Medium"
    urgency: str = "Medium"
    restricted: bool = False
    requester_id: int | None = None
    form_definition_id: int | None = None
    custom_data: dict = Field(default_factory=dict)


class IncidentCreate(BaseModel):
    client_request_id: str = Field(min_length=12, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    request_type: str = "Incident"
    status: str = "Open"
    mode: str = "Web Form"
    level: str = "Tier 1"
    impact: str = "Medium"
    impact_details: str = Field(default="", max_length=4000)
    urgency: str = "Medium"
    priority_override: str | None = None
    priority_override_reason: str | None = Field(default=None, max_length=240)
    requester_id: int | None = None
    on_behalf_of_id: int | None = None
    site_location: str = Field(default="", max_length=140)
    site_override_reason: str | None = Field(default=None, max_length=240)
    asset_ids: list[int] = Field(default_factory=list, max_length=50)
    configuration_item_ids: list[int] = Field(default_factory=list, max_length=50)
    team_id: int | None = None
    assigned_user_id: int | None = None
    category_id: int
    subcategory_id: int | None = None
    item_id: int | None = None
    subject: str = Field(min_length=4, max_length=240)
    description: str = Field(min_length=10, max_length=20000)
    emails_to_notify: list[str] = Field(default_factory=list, max_length=20)
    form_definition_id: int | None = None
    custom_data: dict = Field(default_factory=dict)


class IncidentSettingsUpdate(BaseModel):
    taxonomy: dict
    priority_matrix: dict
    sla: dict


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    kind: str = "public"


class TicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    priority_override_reason: str | None = None
    category: str | None = None
    assigned_user_id: int | None = None
    team_id: int | None = None
    next_action_owner: str | None = None
    next_action: str | None = None
    waiting_reason: str | None = None
    follow_up_at: datetime | None = None
    resolution_summary: str | None = None


class TicketReassignment(BaseModel):
    """A deliberate transfer to a selected support queue and optional technician."""
    queue_id: int
    assigned_user_id: int | None = None
    reason: str | None = Field(default=None, max_length=240)


class BulkUpdate(BaseModel):
    ticket_ids: list[int]
    status: str | None = None
    assigned_user_id: int | None = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    display_name: str
    role: str
    team_id: int | None = None
    temporary_password: str
    ringcentral_extension_number: str | None = None


class PasswordReset(BaseModel):
    temporary_password: str


class UserUpdate(BaseModel):
    active: bool | None = None
    must_change_password: bool | None = None
    role: str | None = None
    team_id: int | None = None
    availability: str | None = None
    ringcentral_extension_id: str | None = None
    ringcentral_extension_number: str | None = None
    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    alternate_email: str | None = ""
    employee_number: str | None = ""
    phone: str | None = ""
    job_title: str | None = ""
    department_name: str | None = ""
    location_name: str | None = ""
    manager_user_id: int | None = None
    timezone: str | None = None
    preferred_language: str | None = None
    notification_preferences: dict | None = None
    auth_source: str | None = None
    role_source: str | None = None
    team_source: str | None = None
    role_definition_ids: list[int] | None = None
    team_ids: list[int] | None = None
    group_ids: list[int] | None = None
    version: int | None = None


class SelfProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str = Field(default="", max_length=60)


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=2, max_length=160)
    temporary_password: str = Field(min_length=12, max_length=256)
    role: str = "end_user"
    team_id: int | None = None
    alternate_email: str = ""
    employee_number: str = ""
    phone: str = ""
    job_title: str = ""
    department_name: str = ""
    location_name: str = ""
    manager_user_id: int | None = None
    timezone: str = "America/New_York"
    preferred_language: str = "en"
    notification_preferences: dict = Field(default_factory=dict)
    auth_source: str = "Local"
    role_definition_ids: list[int] = Field(default_factory=list)
    team_ids: list[int] = Field(default_factory=list)
    group_ids: list[int] = Field(default_factory=list)
    ringcentral_extension_id: str | None = None
    ringcentral_extension_number: str | None = None


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(min_length=2, max_length=80)
    support_email: str = ""
    support_phone: str = ""
    logo_url: str = ""


class IntegrationSecretsUpdate(BaseModel):
    client_secret: str | None = None
    jwt_credential: str | None = None
    clear: list[str] = Field(default_factory=list)


class AssetCreate(BaseModel):
    asset_tag: str
    hostname: str | None = None
    serial_number: str | None = None
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    category: str = "Computer"
    asset_type: str
    status: str = "Stock"
    condition: str = "Good"
    assigned_employee_id: int | None = None
    location_id: int | None = None
    department_id: int | None = None
    purchase_date: date | None = None
    purchase_cost_cents: int | None = None
    warranty_expiration: date | None = None
    vendor: str | None = None
    purpose: str | None = None
    company: str | None = None
    project: str | None = None
    mac_address: str | None = None
    notes: str = ""


class AssetUpdate(BaseModel):
    asset_tag: str | None = None
    hostname: str | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    name: str | None = None
    category: str | None = None
    asset_type: str | None = None
    status: str | None = None
    condition: str | None = None
    location_id: int | None = None
    department_id: int | None = None
    purchase_date: date | None = None
    purchase_cost_cents: int | None = None
    warranty_expiration: date | None = None
    vendor: str | None = None
    purpose: str | None = None
    company: str | None = None
    project: str | None = None
    mac_address: str | None = None
    notes: str | None = None


class AssetAssign(BaseModel):
    employee_id: int | None = None
    status: str = "Active"


class FeedbackIn(BaseModel):
    feedback_type: str
    current_page: str
    related_record_id: str | None = None
    text: str = Field(min_length=3, max_length=5000)


class FailureResolve(BaseModel):
    resolution_note: str


class ConfigUpdate(BaseModel):
    value: dict


class EmailIngest(BaseModel):
    message_id: str
    in_reply_to: str | None = None
    references: list[str] = []
    sender: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str
    text_body: str
    headers: dict[str, str] = {}
    attachments: list[dict] = []


class FormDefinitionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,99}$")
    description: str = Field(default="", max_length=1000)
    category: str = Field(default="General", min_length=1, max_length=100)
    icon: str = Field(default="form", max_length=30)
    fields: list[dict] = Field(default_factory=list, max_length=100)
    active: bool = True
    is_template: bool = False
    published: bool = False
    form_type: str = "service_request"
    portal_visible: bool = True
    default_for_type: bool = False
    requester_layout: list = Field(default_factory=list)
    technician_layout: list = Field(default_factory=list)
    lifecycle_state: str = "draft"
    version: int | None = None


class FormSubmissionIn(BaseModel):
    subject: str = Field(min_length=4, max_length=240)
    values: dict = Field(default_factory=dict)
    requester_id: int | None = None
    asset_ids: list[int] = Field(default_factory=list)
    impact: str = "Medium"
    urgency: str = "Medium"


class GroupIn(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    group_type: str = Field(default="Custom", max_length=60)
    description: str = Field(default="", max_length=500)
    source: str = Field(default="Local", max_length=40)
    active: bool = True
    member_ids: list[int] = Field(default_factory=list)
    owner_ids: list[int] = Field(default_factory=list)
    group_type_id: int | None = None
    manager_user_id: int | None = None
    email: str = ""
    region: str = ""
    timezone: str = "America/New_York"
    escalation_contact: str = ""
    version: int | None = None


class GroupTypeIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    icon: str = Field(default="group", max_length=40)
    color: str = Field(default="#176453", pattern=r"^#[0-9A-Fa-f]{6}$")
    purpose: str = Field(default="", max_length=200)
    allowed_uses: list[str] = Field(default_factory=list)
    sort_order: int = 100
    active: bool = True
    version: int | None = None


class RoleDefinitionIn(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    permissions: dict[str, list[str]] = Field(default_factory=dict)
    parent_role_id: int | None = None
    active: bool = True
    version: int | None = None


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    description: str = Field(default="", max_length=500)
    lead_user_id: int | None = None
    backup_lead_user_id: int | None = None
    member_ids: list[int] = Field(default_factory=list)
    primary_member_ids: list[int] = Field(default_factory=list)
    region: str = Field(default="", max_length=80)
    supported_locations: list[str] = Field(default_factory=list)
    timezone: str = "America/New_York"
    business_hours: dict = Field(default_factory=dict)
    supported_services: list[str] = Field(default_factory=list)
    supported_categories: list[int] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    default_capacity: int = Field(default=10, ge=1, le=1000)
    escalation_team_id: int | None = None
    active: bool = True
    version: int | None = None


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=140)
    parent_id: int | None = None
    level: str = Field(default="category", pattern=r"^(category|subcategory|item)$")
    description: str = Field(default="", max_length=500)
    sort_order: int = 0
    configuration: dict = Field(default_factory=dict)
    active: bool = True
    version: int | None = None


class QueueIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    team_id: int
    description: str = Field(default="", max_length=500)
    assignment_strategy: str = "round_robin"
    configuration: dict = Field(default_factory=dict)
    active: bool = True
    key: str = Field(default="", max_length=80)
    manager_user_id: int | None = None
    priority_order: int = 100
    eligible_teams: list[dict] = Field(default_factory=list)
    version: int | None = None


class RoutingRuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    priority_order: int = 100
    conditions: dict | list[dict] = Field(default_factory=lambda: {"logic": "AND", "conditions": []})
    actions: dict = Field(default_factory=dict)
    active: bool = True
    description: str = Field(default="", max_length=500)
    trigger: str = "ticket.created"
    status: str = Field(default="active", pattern=r"^(draft|active)$")
    stop_processing: bool = True
    overwrite_existing: bool = False
    reevaluate_fields: list[str] = Field(default_factory=list)
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    version: int | None = None


class NotificationRuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    trigger: str = Field(min_length=2, max_length=80)
    conditions: list[dict] = Field(default_factory=list)
    recipients: list[dict] = Field(default_factory=list)
    template: dict = Field(default_factory=dict)
    active: bool = True
    classification: str = Field(default="customer", pattern=r"^(customer|internal)$")
    locale: str = "en"
    status: str = Field(default="draft", pattern=r"^(draft|active)$")
    rate_limit: dict = Field(default_factory=dict)
    suppress_actor: bool = True
    version: int | None = None


class IntegrationConnectionIn(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    kind: str = Field(pattern=r"^(directory|email|telephony)$")
    provider: str = Field(min_length=2, max_length=80)
    enabled: bool = False
    configuration: dict = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    clear_secrets: list[str] = Field(default_factory=list)
    version: int | None = None


class GuidedIntegrationStartIn(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    kind: str = Field(pattern=r"^(directory|email|telephony)$")
    provider: str = Field(pattern=r"^(Microsoft Entra ID|Microsoft 365|RingCentral)$")
    configuration: dict = Field(default_factory=dict)


class ProviderApplicationRegistrationIn(BaseModel):
    client_id: str = Field(min_length=5, max_length=300)
    client_secret: str = Field(default="", max_length=2000)
    environment: str = Field(default="production", pattern=r"^(production|sandbox|devtest)$")


class ApprovalWorkflowIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    form_definition_id: int
    steps: list[dict] = Field(min_length=1, max_length=20)
    task_template_ids: list[int] = Field(default_factory=list)
    closure_requirements: dict = Field(default_factory=lambda: {"require_resolution_summary": True, "require_checklists": True})
    active: bool = True


class TaskTemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    items: list[dict] = Field(min_length=1, max_length=100)
    active: bool = True
    version: int | None = None


class ChecklistItemUpdate(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    completed: bool
    note: str = Field(default="", max_length=2000)


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(Approved|Rejected)$")
    comment: str = Field(default="", max_length=5000)


class ReportDefinitionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    configuration: dict
    active: bool = True

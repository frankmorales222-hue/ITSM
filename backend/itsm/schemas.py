from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
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
    role: str | None = None
    team_id: int | None = None
    availability: str | None = None
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
    published: bool = False


class FormSubmissionIn(BaseModel):
    subject: str = Field(min_length=4, max_length=240)
    values: dict = Field(default_factory=dict)
    requester_id: int | None = None
    asset_ids: list[int] = Field(default_factory=list)
    impact: str = "Medium"
    urgency: str = "Medium"


class ApprovalWorkflowIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    form_definition_id: int
    steps: list[dict] = Field(min_length=1, max_length=20)
    active: bool = True


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(pattern=r"^(Approved|Rejected)$")
    comment: str = Field(default="", max_length=5000)


class ReportDefinitionIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    configuration: dict
    active: bool = True

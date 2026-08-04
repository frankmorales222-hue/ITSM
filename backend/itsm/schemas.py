from datetime import datetime
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


class PasswordReset(BaseModel):
    temporary_password: str


class AssetCreate(BaseModel):
    asset_tag: str
    hostname: str | None = None
    serial_number: str | None = None
    manufacturer: str
    model: str
    asset_type: str
    status: str = "Stock"
    condition: str = "Good"
    assigned_employee_id: int | None = None
    notes: str = ""


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

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import QueueTeamEligibility, SupportQueue, Team, TeamMembership, Ticket, TicketStatus, User


PROVIDER_SCHEMAS: dict[str, dict[str, Any]] = {
    "Microsoft Entra ID": {"kind":"directory","fields":[],"secrets":[]},
    "LDAP": {"kind":"directory","fields":["server","port","tls_mode","base_dn","bind_dn","user_search_base","user_filter","group_search_base","group_filter","unique_id_attribute","email_attribute","sync_schedule"],"secrets":["bind_password"]},
    "Active Directory / LDAP": {"kind":"directory","fields":["server","port","tls_mode","base_dn","bind_dn","user_search_base","user_filter","group_search_base","group_filter","unique_id_attribute","email_attribute","sync_schedule"],"secrets":["bind_password"]},
    "SCIM 2.0": {"kind":"directory","fields":["base_url","auth_method","users_path","groups_path","matching_attribute","scope_filter"],"secrets":["bearer_token","oauth_client_secret"]},
    "Microsoft 365": {"kind":"email","fields":[],"secrets":[]},
    "Google Workspace": {"kind":"email","fields":["client_id","mailbox","sender_name","reply_to","delivery_mode","polling_interval"],"secrets":["client_secret","service_account_json"]},
    "Generic SMTP / IMAP": {"kind":"email","fields":["smtp_host","smtp_port","smtp_tls","imap_host","imap_port","imap_tls","username","from_address","reply_to","inbound_folder","processed_folder","polling_interval"],"secrets":["password"]},
    "Generic SMTP/IMAP": {"kind":"email","fields":["smtp_host","smtp_port","smtp_tls","imap_host","imap_port","imap_tls","username","from_address","reply_to","inbound_folder","processed_folder","polling_interval"],"secrets":["password"]},
    "RingCentral": {"kind":"telephony","fields":[],"secrets":[]},
}


EVENTS = [
    "ticket.created","ticket.assigned","ticket.reassigned","ticket.updated","ticket.public_reply","ticket.requester_reply","technician.replied","user.replied","ticket.internal_note","ticket.waiting_on_requester","ticket.resolved","ticket.closed","ticket.reopened",
    "approval.requested","approval.reminder","approval.approved","approval.rejected","sla.warning","sla.breached","incident.major_declared","incident.status_changed",
    "change.submitted","change.approved","change.rejected","change.scheduled","call.received","call.answered","call.missed","call.abandoned","voicemail.received",
    "routing.failed","integration.failed","user.created","user.deactivated","asset.assigned","asset.returned",
    "chat.requested","chat.message","ticket.requester_closed","teams.session_created","endpoint.action_approval"
]


NOTIFICATION_TEMPLATES = {
    "ticket.created": ("Request received", "customer", "[{{ticket.number}}] Request received: {{ticket.subject}}", "Hello {{requester.first_name}},\n\nWe received your request and created ticket {{ticket.number}}.\n\nSubject: {{ticket.subject}}\nStatus: {{ticket.status}}\nPriority: {{ticket.priority}}\nSubmitted: {{ticket.created_at_local}}\n\nReview or update your request: {{ticket.url}}\n\nPlease reply without changing the ticket number in the subject.\n\nThank you,\n{{organization.support_name}}"),
    "ticket.assigned": ("Ticket assigned", "internal", "[{{ticket.number}}] Assigned: {{ticket.subject}}", "Hello {{assignee.first_name}},\n\n{{ticket.number}} has been assigned to you in {{queue.name}}.\nPriority: {{ticket.priority}}\nRequester: {{requester.name}}\nOpen ticket: {{ticket.url}}"),
    "ticket.public_reply": ("Technician response", "customer", "[{{ticket.number}}] New response: {{ticket.subject}}", "Hello {{requester.first_name}},\n\n{{actor.name}} added a response to {{ticket.number}}.\n\n{{message.preview}}\n\nReply or view the request: {{ticket.url}}"),
    "ticket.requester_reply": ("Ticket requester response", "internal", "[{{ticket.number}}] Requester replied: {{ticket.subject}}", "Hello {{assignee.first_name}},\n\n{{requester.name}} replied to {{ticket.number}}.\n\n{{message.preview}}\n\nOpen the request: {{ticket.url}}"),
    "technician.replied": ("Email technician response", "customer", "[{{ticket.number}}] New response: {{ticket.subject}}", "Hello {{requester.first_name}},\n\n{{assignee.name}} added a response to {{ticket.number}}.\n\n{{message.preview}}\n\nReply by email or open the request: {{ticket.url}}"),
    "user.replied": ("Email requester response", "internal", "[{{ticket.number}}] Requester replied: {{ticket.subject}}", "Hello {{assignee.first_name}},\n\n{{requester.name}} replied to {{ticket.number}}.\n\n{{message.preview}}\n\nOpen the request: {{ticket.url}}"),
    "ticket.waiting_on_requester": ("Waiting for requester", "customer", "[{{ticket.number}}] We need your response", "Hello {{requester.first_name}},\n\nWe need additional information before work can continue on {{ticket.number}}.\n\n{{message.preview}}\n\nRespond here: {{ticket.url}}"),
    "ticket.resolved": ("Ticket resolved", "customer", "[{{ticket.number}}] Resolved: {{ticket.subject}}", "Hello {{requester.first_name}},\n\nYour request {{ticket.number}} has been resolved.\nResolution: {{ticket.resolution_summary}}\n\nReview the resolution: {{ticket.url}}"),
    "ticket.closed": ("Ticket closed", "customer", "[{{ticket.number}}] Closed: {{ticket.subject}}", "Hello {{requester.first_name}},\n\n{{ticket.number}} is now closed. Thank you for working with {{organization.support_name}}."),
    "ticket.requester_closed": ("Requester closed ticket", "internal", "[{{ticket.number}}] Closed by requester: {{ticket.subject}}", "{{requester.name}} asked to close {{ticket.number}}. The request and closure note are available here: {{ticket.url}}"),
    "chat.requested": ("Live help requested", "internal", "[{{ticket.number}}] Live help requested", "{{requester.name}} requested live help on {{ticket.number}}. Open the ticket to join the secure chat: {{ticket.url}}"),
    "chat.message": ("New live-chat message", "internal", "[{{ticket.number}}] New live-chat message", "A new secure live-chat message is available on {{ticket.number}}: {{ticket.url}}"),
    "teams.session_created": ("Teams support session", "customer", "[{{ticket.number}}] Join your Teams support session", "Your technician created a secure Microsoft Teams support session for {{ticket.number}}. Open the ticket to join: {{ticket.url}}"),
    "endpoint.action_approval": ("Endpoint action approval", "customer", "[{{ticket.number}}] Approval required for endpoint support", "Your technician requested permission to perform a secure endpoint support action. Open {{ticket.number}} to approve or decline: {{ticket.url}}"),
    "ticket.reopened": ("Ticket reopened", "internal", "[{{ticket.number}}] Reopened: {{ticket.subject}}", "{{ticket.number}} was reopened by {{actor.name}}. Review the request: {{ticket.url}}"),
    "approval.requested": ("Approval requested", "internal", "[{{ticket.number}}] Approval required: {{ticket.subject}}", "Hello {{approver.first_name}},\n\nYour approval is required for {{ticket.number}}.\nRequested by: {{requester.name}}\nApprove or reject: {{approval.url}}"),
    "approval.approved": ("Approval approved", "customer", "[{{ticket.number}}] Approved: {{ticket.subject}}", "Hello {{requester.first_name}},\n\nThe approval for {{ticket.number}} was approved by {{approver.name}}. Work will continue."),
    "approval.rejected": ("Approval rejected", "customer", "[{{ticket.number}}] Approval declined: {{ticket.subject}}", "Hello {{requester.first_name}},\n\nThe approval for {{ticket.number}} was declined.\nReason: {{approval.comment}}\nView request: {{ticket.url}}"),
    "sla.warning": ("SLA warning", "internal", "[{{ticket.number}}] SLA warning: action required", "{{ticket.number}} is approaching its {{sla.name}} target. Remaining time: {{sla.remaining}}. Open ticket: {{ticket.url}}"),
    "sla.breached": ("SLA breached", "internal", "[{{ticket.number}}] SLA breached: {{ticket.subject}}", "{{ticket.number}} breached its {{sla.name}} target at {{sla.breached_at_local}}. Escalation owner: {{queue.manager}}."),
    "incident.major_declared": ("Major incident declared", "internal", "[MAJOR INCIDENT] {{ticket.number}} — {{ticket.subject}}", "A major incident has been declared.\nImpact: {{ticket.impact}}\nOwner: {{assignee.name}}\nStatus page: {{incident.status_url}}"),
    "incident.status_changed": ("Major incident update", "customer", "[{{ticket.number}}] Incident update: {{ticket.status}}", "Current status: {{ticket.status}}\nLatest update: {{incident.latest_update}}\nNext update: {{incident.next_update_at_local}}"),
    "change.submitted": ("Change submitted", "internal", "[{{ticket.number}}] Change submitted: {{ticket.subject}}", "Change {{ticket.number}} was submitted by {{requester.name}}. Risk: {{change.risk}}. Review: {{ticket.url}}"),
    "change.scheduled": ("Change scheduled", "customer", "[{{ticket.number}}] Change scheduled for {{change.start_at_local}}", "Change {{ticket.number}} is scheduled from {{change.start_at_local}} to {{change.end_at_local}}. Service: {{service.name}}."),
    "change.approved": ("Change approved", "internal", "[{{ticket.number}}] Change approved", "Change {{ticket.number}} was approved by {{approver.name}} and may proceed within its approved window."),
    "change.rejected": ("Change rejected", "customer", "[{{ticket.number}}] Change rejected", "Change {{ticket.number}} was rejected. Reason: {{approval.comment}}. Review: {{ticket.url}}"),
    "routing.failed": ("Routing failure", "internal", "[{{ticket.number}}] Routing failed", "No routing rule or fallback queue could accept {{ticket.number}}. Review the routing trace: {{routing.trace_url}}"),
    "integration.failed": ("Integration failure", "internal", "Integration failure: {{integration.name}}", "{{integration.name}} failed at {{event.occurred_at_local}}. Error: {{integration.error}}. Review logs: {{integration.url}}"),
    "call.missed": ("Missed call", "internal", "Missed support call from {{caller.display}}", "A call to {{call.did}} was missed at {{call.started_at_local}}. Caller: {{caller.display}}. Create or review ticket: {{call.url}}"),
    "voicemail.received": ("Voicemail received", "internal", "New voicemail from {{caller.display}}", "A voicemail was received at {{call.received_at_local}}. Duration: {{call.duration}}. Open voicemail: {{call.url}}"),
}


def value_at(sample: dict, field: str):
    current: Any = sample
    for part in field.split("."):
        if not isinstance(current, dict): return None
        current = current.get(part)
    return current


def evaluate_leaf(condition: dict, sample: dict) -> tuple[bool, str]:
    field, operator, expected = condition.get("field", ""), condition.get("operator", "equals"), condition.get("value")
    actual = value_at(sample, field)
    left, right = str(actual or "").lower(), str(expected or "").lower()
    operations = {
        "equals": lambda: left == right, "does_not_equal": lambda: left != right, "contains": lambda: right in left,
        "does_not_contain": lambda: right not in left, "starts_with": lambda: left.startswith(right), "ends_with": lambda: left.endswith(right),
        "is_empty": lambda: actual in (None,"",[]), "is_not_empty": lambda: actual not in (None,"",[]),
        "in": lambda: actual in (expected if isinstance(expected,list) else [expected]), "not_in": lambda: actual not in (expected if isinstance(expected,list) else [expected]),
        "greater_than": lambda: float(actual) > float(expected), "less_than": lambda: float(actual) < float(expected),
        "matches": lambda: bool(re.search(str(expected), str(actual or ""))),
    }
    try: matched = bool(operations.get(operator, operations["equals"])())
    except (TypeError, ValueError, re.error): matched = False
    return matched, f"{field} {operator} {expected!r}: actual={actual!r} -> {'matched' if matched else 'did not match'}"


def evaluate_group(node: Any, sample: dict) -> tuple[bool, list[str]]:
    if isinstance(node, list):
        results=[evaluate_group(item,sample) for item in node]; return all(x[0] for x in results), [line for x in results for line in x[1]]
    if not isinstance(node, dict): return False,["Invalid condition"]
    if "conditions" in node:
        results=[evaluate_group(item,sample) for item in node.get("conditions",[])]; mode=node.get("logic","AND").upper()
        matched=(all(x[0] for x in results) if mode=="AND" else any(x[0] for x in results))
        return matched,[f"{mode} group -> {'matched' if matched else 'did not match'}",*[line for x in results for line in x[1]]]
    matched,line=evaluate_leaf(node,sample); return matched,[line]


def queue_simulation(db: Session, queue: SupportQueue) -> dict:
    links=db.scalars(select(QueueTeamEligibility).where(QueueTeamEligibility.queue_id==queue.id,QueueTeamEligibility.active.is_(True)).order_by(QueueTeamEligibility.eligibility_priority)).all()
    team_ids=[x.team_id for x in links] or [queue.team_id]
    teams=db.scalars(select(Team).where(Team.id.in_(team_ids),Team.active.is_(True))).all()
    memberships=db.scalars(select(TeamMembership).where(TeamMembership.team_id.in_(team_ids),TeamMembership.active.is_(True))).all()
    users={u.id:u for u in db.scalars(select(User).where(User.id.in_([m.user_id for m in memberships]),User.active.is_(True))).all()}
    active_counts=dict(db.execute(select(Ticket.assigned_user_id,func.count(Ticket.id)).where(Ticket.assigned_user_id.in_(list(users)),Ticket.status.not_in([TicketStatus.RESOLVED,TicketStatus.CLOSED,TicketStatus.CANCELLED])).group_by(Ticket.assigned_user_id)).all()) if users else {}
    eligible=[]; excluded=[]
    for membership in memberships:
        account=users.get(membership.user_id)
        if not account: continue
        detail={"id":account.id,"name":account.display_name,"team_id":membership.team_id,"availability":account.availability,"active_work":active_counts.get(account.id,0)}
        if account.availability=="Available": eligible.append(detail)
        else: excluded.append({**detail,"reason":f"Availability is {account.availability}"})
    selected=None
    if eligible:
        if queue.assignment_strategy in {"least_active","lowest_workload"}: selected=min(eligible,key=lambda x:(x["active_work"],x["name"]))
        else: selected=sorted(eligible,key=lambda x:x["name"])[0]
    return {"queue":{"id":queue.id,"name":queue.name},"eligible_teams":[{"id":t.id,"name":t.name} for t in teams],"eligible_technicians":eligible,"excluded_technicians":excluded,"assignment_strategy":queue.assignment_strategy,"selected_technician":selected}


def provider_requirements(provider: str) -> dict:
    return PROVIDER_SCHEMAS.get(provider,{"fields":["base_url"],"secrets":["api_secret"]})

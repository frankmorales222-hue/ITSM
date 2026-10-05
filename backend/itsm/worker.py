"""Background worker for IMAP intake, notifications, SLA checks, and heartbeat.

Mailbox passwords are read from Windows Credential Manager through keyring. Run
scripts/configure-mail-secret.ps1 once, then set the non-secret IMAP variables.
"""
import email
import hashlib
import imaplib
import os
import re
import smtplib
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from email.header import decode_header, make_header
from email.policy import default
from email.message import EmailMessage as OutboundEmail
from email.utils import make_msgid
import keyring
from sqlalchemy import func, select
from .database import SessionLocal
from .models import ConfigItem, EmailMessage, Employee, FormDefinition, IntegrationLog, Notification, Organization, Role, SystemState, Team, Ticket, TicketAttachment, TicketMessage, TicketStatus, User, now
from .services import audit, close_ticket_from_requester_message, fail_automation, inbound_email_routing_sample, is_automated_email, next_ticket_number, notification_delivery_enabled, outbound_email_delivery_enabled, notify, route_incident, sla_dates, ticket_email_subject, ticket_from_email_subject, ticket_from_reply_subject
from .config import settings
from .assetpilot import ensure_asset_employee_user, import_assetpilot
from .identity import provision_end_user
from .microsoft_mail import connected_mailbox, mailbox_address, mark_read, message_mime, send_notification, unread_messages
from .self_service import evaluate_ticket, record_email_outcome, return_unanswered_to_it


_MAIL_MAX_ATTEMPTS = 3
_HTTPS_CERTIFICATE_CHECK_INTERVAL = timedelta(hours=1)


def _mail_retry_key(graph_message_id: str) -> str:
    digest = hashlib.sha256(graph_message_id.encode("utf-8")).hexdigest()
    return f"mail_retry:{digest}"


def _mail_retry_state(db, graph_message_id: str) -> SystemState | None:
    return db.get(SystemState, _mail_retry_key(graph_message_id))


def _message_already_processed(db, item: dict) -> bool:
    message_id = str(item.get("internetMessageId") or "").strip()
    return bool(message_id and db.scalar(select(EmailMessage.id).where(
        EmailMessage.message_id == message_id)))


def text_body(message):
    candidates = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_disposition() == "attachment": continue
        if part.get_content_type() == "text/plain":
            try: candidates.append(part.get_content())
            except Exception: pass
    body = "\n".join(candidates).strip()
    body = re.split(r"\nOn .+ wrote:\s*\n|\nFrom:\s.+\nSent:\s", body, maxsplit=1)[0]
    # Outlook represents inline images as [cid:image001.png@...].  The image
    # itself is stored below as a ticket attachment, so do not leave opaque
    # transport markers in the conversation.
    body = re.sub(r"\[cid:[^\]]+\]", "", body, flags=re.IGNORECASE)
    return body[:20000]


def attachment_metadata(message):
    result = []
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            payload = part.get_payload(decode=True) or b""
            result.append({"name": str(make_header(decode_header(filename))), "content_type": part.get_content_type(), "size": len(payload)})
    return result


_INBOUND_ATTACHMENT_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".zip"}
_INBOUND_ATTACHMENT_LIMIT = 25 * 1024 * 1024


def _save_inbound_attachments(db, message, ticket: Ticket, requester: User) -> int:
    """Persist safe email attachments, including Outlook inline CID images.

    The email worker intentionally keeps the original email record, but support
    staff need the actual files on the ticket as well.  This mirrors the portal
    upload policy and does not change ticket routing or message processing.
    """
    storage_root = Path(settings.data_directory) / "attachments"
    storage_root.mkdir(parents=True, exist_ok=True)
    saved = 0
    for part in message.walk() if message.is_multipart() else [message]:
        filename = part.get_filename()
        content_id = str(part.get("Content-ID") or "").strip("<>")
        if not filename and not content_id:
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload or len(payload) > _INBOUND_ATTACHMENT_LIMIT:
            continue
        decoded_name = str(make_header(decode_header(filename))) if filename else content_id.split("@", 1)[0]
        safe_name = Path(decoded_name or "attachment").name.replace("\x00", "")[:240]
        suffix = Path(safe_name).suffix.lower()
        if suffix not in _INBOUND_ATTACHMENT_EXTENSIONS:
            continue
        storage_name = f"{uuid.uuid4().hex}{suffix}"
        try:
            (storage_root / storage_name).write_bytes(payload)
        except OSError:
            continue
        db.add(TicketAttachment(ticket_id=ticket.id, original_name=safe_name,
                                storage_name=storage_name, content_type=part.get_content_type(),
                                size_bytes=len(payload), uploaded_by_id=requester.id))
        saved += 1
    return saved


def _message_references(message) -> list[str]:
    """Extract normalized RFC message IDs from reply headers."""
    values = [str(message.get("In-Reply-To") or ""), str(message.get("References") or "")]
    references = []
    for value in values:
        references.extend(re.findall(r"<[^<>\s]+>", value))
    return list(dict.fromkeys(reference.strip() for reference in references if reference.strip()))


def _record_outbound_message(db, ticket: Ticket | None, sender: str, recipient: str,
                             subject: str, message_id: str | None) -> None:
    """Associate a sent provider message with its ticket for future replies."""
    normalized = (message_id or "").strip()
    if not ticket or not normalized:
        return
    if db.scalar(select(EmailMessage).where(EmailMessage.message_id == normalized)):
        return
    db.add(EmailMessage(message_id=normalized, ticket_id=ticket.id, sender=sender,
                        subject=subject, attachment_metadata=[], processing_status="outbound"))


def process_message(db, raw: bytes):
    msg = email.message_from_bytes(raw, policy=default)
    message_id = msg.get("Message-ID")
    if not message_id or db.scalar(select(EmailMessage).where(EmailMessage.message_id == message_id)): return "duplicate"
    subject = str(make_header(decode_header(msg.get("Subject", "No subject"))))
    headers = {k: str(v) for k,v in msg.items()}
    sender = email.utils.parseaddr(msg.get("From", ""))[1].lower()
    attachments = attachment_metadata(msg)
    if is_automated_email(headers, subject): status="ignored_automatic"; ticket=None
    else:
        requester = db.scalar(select(User).where(func.lower(User.email) == sender.lower(), User.active.is_(True)))
        if not requester:
            employee = db.scalar(select(Employee).where(func.lower(Employee.work_email) == sender.lower(), Employee.employment_status == "Active"))
            requester = ensure_asset_employee_user(db, employee) if employee else None
        if not requester and sender:
            organization_id = db.info.get("organization_id")
            if organization_id:
                sender_name = email.utils.parseaddr(msg.get("From", ""))[0]
                requester, _created = provision_end_user(
                    db,
                    organization_id=int(organization_id),
                    email=sender,
                    display_name=sender_name,
                    auth_source="Email",
                    role_source="Inbound email requester",
                )
        if not requester:
            fail_automation(db,"email_requester","Requester could not be identified",{"sender":sender,"message_id":message_id}); status="failed"; ticket=None
        else:
            refs = _message_references(msg)
            prior = db.scalar(select(EmailMessage).where(EmailMessage.message_id.in_([r for r in refs if r])).order_by(EmailMessage.id.desc())) if any(refs) else None
            ticket = db.get(Ticket, prior.ticket_id) if prior and prior.ticket_id else None
            if not ticket: ticket = ticket_from_email_subject(db, subject)
            if not ticket: ticket = ticket_from_reply_subject(db, subject, requester.id)
            if ticket:
                allowed = requester.id in {ticket.requester_id, ticket.assigned_user_id} or requester.role in {Role.TEAM_LEAD, Role.MANAGER, Role.ADMIN}
                if not allowed:
                    fail_automation(db,"email_authorization","Sender is not allowed to update this ticket",{"sender":sender,"ticket_number":ticket.number}); status="failed"; ticket=None
                else:
                    body=text_body(msg) or "Email reply received."
                    db.add(TicketMessage(ticket_id=ticket.id,author_id=requester.id,body=body,kind="public",source="email")); status="threaded"
                    if requester.id == ticket.requester_id:
                        self_service_outcome = record_email_outcome(db, ticket, requester, body)
                        closed = bool(self_service_outcome and self_service_outcome.status == "fixed")
                        if not self_service_outcome:
                            closed=close_ticket_from_requester_message(db,ticket,requester,body,"email")
                        if not closed and not self_service_outcome:
                            notify(db,ticket.assigned_user_id,"user.replied",f"[{ticket.number}] Requester replied: {ticket.subject}",body[:200],ticket.id,email=True)
                        if not closed and ticket.status == TicketStatus.WAITING_USER: ticket.status=TicketStatus.IN_PROGRESS
                    else:
                        ticket.first_responded_at=ticket.first_responded_at or now()
                        notify(db,ticket.requester_id,"technician.replied",f"[{ticket.number}] New response: {ticket.subject}",body[:200],ticket.id,email=True)
            else:
                body = text_body(msg)
                sample = inbound_email_routing_sample(db, requester, sender, subject, body)
                team,tech,reason,trace=route_incident(db,sample,requester); first,due=sla_dates("Medium")
                ticket=Ticket(number=next_ticket_number(db,"Report an issue"),request_type="Report an issue",subject=subject[:240],description=text_body(msg),requester_id=requester.id,team_id=team.id,assigned_user_id=tech.id if tech else None,status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW,priority="Medium",impact="Medium",urgency="Medium",category="General",route_reason=reason,first_response_due=first,resolution_due=due)
                ticket.routing_trace = trace
                db.add(ticket);db.flush();db.add(TicketMessage(ticket_id=ticket.id,author_id=requester.id,body=text_body(msg),kind="public",source="email"));status="created"
                notify(db,requester.id,"ticket.created",f"[{ticket.number}] Request received: {ticket.subject}","Your email was received and a ticket was created.",ticket.id,email=True)
                notify(db,tech.id if tech else None,"ticket.assigned",f"[{ticket.number}] Assigned: {ticket.subject}",f"Created by email from {requester.display_name}.",ticket.id,email=True)
    saved_attachments = _save_inbound_attachments(db, msg, ticket, requester) if ticket and requester else 0
    db.add(EmailMessage(message_id=message_id,in_reply_to=msg.get("In-Reply-To"),ticket_id=ticket.id if ticket else None,sender=sender,subject=subject,attachment_metadata=attachments,processing_status=status))
    audit(db,f"email.{status}","ticket",ticket.id if ticket else None,new={"message_id":message_id,"attachments":len(attachments),"saved_attachments":saved_attachments});return status


def sla_job(db):
    config=db.scalar(select(ConfigItem).where(ConfigItem.section=="incident_sla"))
    policies=(config.value or {}).get("policies",[]) if config else []
    open_tickets=db.scalars(select(Ticket).where(Ticket.status.notin_([TicketStatus.RESOLVED,TicketStatus.CLOSED,TicketStatus.CANCELLED]))).all()
    for ticket in open_tickets:
        if (ticket.custom_data or {}).get("sla_paused_at"): continue
        remaining=ticket.resolution_due.replace(tzinfo=ticket.resolution_due.tzinfo or now().tzinfo)-now()
        event="sla.breached" if remaining.total_seconds()<0 else "sla.warning" if remaining<timedelta(hours=4) else None
        if event and not db.scalar(select(Notification).where(Notification.ticket_id==ticket.id,Notification.event==event)):
            notify(db,ticket.assigned_user_id,event,f"{ticket.number} {'breached' if event.endswith('breached') else 'approaching'} SLA",ticket.subject,ticket.id)
        policy=next((item for item in policies if item.get("key")==ticket.sla_policy_key),{})
        lifetime=max(1,(ticket.resolution_due.replace(tzinfo=ticket.resolution_due.tzinfo or now().tzinfo)-ticket.created_at.replace(tzinfo=ticket.created_at.tzinfo or now().tzinfo)).total_seconds())
        elapsed=max(0,(now()-ticket.created_at.replace(tzinfo=ticket.created_at.tzinfo or now().tzinfo)).total_seconds())
        percent=int(elapsed*100/lifetime)
        escalations=policy.get("escalations") or [{"percent":75,"recipients":["assignee","team_lead"],"email":False},{"percent":100,"recipients":["assignee","team_lead","manager"],"email":True}]
        for escalation in escalations:
            threshold=int(escalation.get("percent",100)); escalation_event=f"sla.escalation.{threshold}"
            if percent<threshold or db.scalar(select(Notification).where(Notification.ticket_id==ticket.id,Notification.event==escalation_event)): continue
            recipient_ids=[]
            team=db.get(Team,ticket.team_id)
            requester=db.get(User,ticket.requester_id)
            for recipient in escalation.get("recipients",[]):
                if recipient=="assignee" and ticket.assigned_user_id: recipient_ids.append(ticket.assigned_user_id)
                elif recipient=="requester": recipient_ids.append(ticket.requester_id)
                elif recipient=="team_lead" and team and team.lead_user_id: recipient_ids.append(team.lead_user_id)
                elif recipient=="manager" and requester and requester.manager_user_id: recipient_ids.append(requester.manager_user_id)
            for user_id in set(recipient_ids):
                notify(db,user_id,escalation_event,f"{ticket.number} reached {threshold}% of SLA",ticket.subject,ticket.id,email=bool(escalation.get("email")))


def email_notification_job(db):
    if not notification_delivery_enabled(db) or not outbound_email_delivery_enabled(db):
        pending=db.scalars(select(Notification).where(Notification.delivery_status=="pending_email")).all()
        for notification in pending:
            notification.delivery_status="suppressed"
            audit(db,"notification.email_suppressed","notification",notification.id,new={
                "event":notification.event,"recipient_user_id":notification.user_id,
                "subject":notification.title,"reason":"Outbound email delivery is disabled"})
        return 0
    graph = connected_mailbox(db)
    if graph:
        pending = db.scalars(select(Notification).where(Notification.delivery_status == "pending_email")
                             .order_by(Notification.created_at).limit(50)).all()
        delivered = 0
        for notification in pending:
            recipient = db.get(User, notification.user_id)
            if not recipient or not recipient.email:
                notification.delivery_status = "failed"
                fail_automation(db, "notification", "Email recipient is unavailable", {"notification_id": notification.id}, "notification", notification.id)
                continue
            ticket = db.get(Ticket, notification.ticket_id) if notification.ticket_id else None
            destination = f"ticket/{ticket.id}" if ticket else "tickets"
            link = f"{settings.public_url.rstrip('/')}/#{destination}"
            email_subject = ticket_email_subject(ticket, notification.title)
            try:
                outbound_id = send_notification(db, graph, recipient.email, email_subject, notification.body, link)
                _record_outbound_message(db, ticket, mailbox_address(graph), recipient.email,
                                         email_subject, outbound_id)
                notification.delivery_status = "sent"; delivered += 1
                audit(db,"notification.email_sent","notification",notification.id,new={
                    "provider":"Microsoft 365","event":notification.event,"recipient_user_id":recipient.id,
                    "recipient_name":recipient.display_name,"recipient_email":recipient.email,"subject":email_subject,
                    "ticket_id":ticket.id if ticket else None,"ticket_number":ticket.number if ticket else ""})
                db.commit()
            except Exception as exc:
                db.rollback()
                notification = db.get(Notification, notification.id)
                notification.delivery_status = "failed"
                fail_automation(db,"notification","Microsoft 365 email notification failed",
                                {"notification_id":notification.id,"error":str(exc)[:300]},"notification",notification.id)
                db.commit()
        return delivered
    host = os.getenv("ITSM_SMTP_HOST")
    if not host:
        return 0
    port = int(os.getenv("ITSM_SMTP_PORT", "587")); username = os.getenv("ITSM_SMTP_USERNAME", "")
    sender = os.getenv("ITSM_SMTP_FROM", username); use_tls = os.getenv("ITSM_SMTP_USE_TLS", "true").lower() == "true"
    target = os.getenv("ITSM_SMTP_SECRET_TARGET", "NorthstarDesk/smtp")
    password = keyring.get_password(target, username) if username else None
    if username and not password:
        raise RuntimeError("SMTP credential is not available in Windows Credential Manager")
    pending = db.scalars(select(Notification).where(Notification.delivery_status == "pending_email")
                         .order_by(Notification.created_at).limit(50)).all()
    if not pending:
        return 0
    delivered = 0
    with smtplib.SMTP(host, port, timeout=30) as client:
        if use_tls: client.starttls()
        if username: client.login(username, password)
        for notification in pending:
            recipient = db.get(User, notification.user_id)
            if not recipient or not recipient.email:
                notification.delivery_status = "failed"
                fail_automation(db, "notification", "Email recipient is unavailable",
                                {"notification_id": notification.id}, "notification", notification.id)
                continue
            message = OutboundEmail(); message["From"] = sender; message["To"] = recipient.email
            ticket=db.get(Ticket,notification.ticket_id) if notification.ticket_id else None
            email_subject = ticket_email_subject(ticket, notification.title)
            message["Subject"] = email_subject
            message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1] if "@" in sender else None)
            destination = "approvals" if notification.event == "approval.requested" else "tickets"
            link = f"{settings.public_url.rstrip('/')}/#{destination}" if notification.ticket_id else settings.public_url
            message.set_content(f"{notification.body}\n\nOpen Northstar Desk: {link}\n")
            try:
                client.send_message(message)
                _record_outbound_message(db, ticket, sender, recipient.email, email_subject, message["Message-ID"])
                notification.delivery_status = "sent"; delivered += 1
                audit(db,"notification.email_sent","notification",notification.id,new={
                    "provider":"SMTP","event":notification.event,"recipient_user_id":recipient.id,
                    "recipient_name":recipient.display_name,"recipient_email":recipient.email,"subject":email_subject,
                    "ticket_id":ticket.id if ticket else None,"ticket_number":ticket.number if ticket else ""})
                db.commit()
            except Exception as exc:
                db.rollback()
                notification = db.get(Notification, notification.id)
                notification.delivery_status = "failed"
                fail_automation(db, "notification", "Email notification failed",
                                {"notification_id": notification.id, "error": str(exc)[:300]}, "notification", notification.id)
                db.commit()
    return delivered


def microsoft_mailbox_job(db):
    connection=connected_mailbox(db)
    if not connection: return 0
    processed=0
    for item in unread_messages(db,connection):
        graph_id=item.get("id")
        if not graph_id: continue
        retry_state = _mail_retry_state(db, graph_id)
        attempts = int((retry_state.value or {}).get("attempts", 0)) if retry_state else 0
        if attempts >= _MAIL_MAX_ATTEMPTS or _message_already_processed(db, item):
            continue
        try:
            with db.begin_nested():
                result = process_message(db,message_mime(db,connection,graph_id))
                db.flush()
            if retry_state:
                db.delete(retry_state)
            db.commit()
            processed += 1 if result != "duplicate" else 0
            try:
                mark_read(db,connection,graph_id)
            except Exception as exc:
                fail_automation(db,"microsoft_mailbox","Processed message could not be marked read",
                                {"graph_message_id":graph_id,"error":str(exc)[:300]},
                                "integration",connection.id)
                db.commit()
        except Exception as exc:
            attempts += 1
            retry_state = _mail_retry_state(db, graph_id) or SystemState(key=_mail_retry_key(graph_id), value={})
            retry_state.value = {
                "graph_message_id": graph_id,
                "internet_message_id": str(item.get("internetMessageId") or ""),
                "attempts": attempts,
                "status": "manual_review" if attempts >= _MAIL_MAX_ATTEMPTS else "retrying",
                "last_error": str(exc)[:300],
                "last_attempt": now().isoformat(),
            }
            db.add(retry_state)
            summary = ("Inbound Microsoft 365 message requires manual review"
                       if attempts >= _MAIL_MAX_ATTEMPTS else
                       "Inbound Microsoft 365 message failed and will be retried")
            failure = fail_automation(db,"microsoft_mailbox",summary,
                            {"graph_message_id":graph_id,"attempt":attempts,
                             "maximum_attempts":_MAIL_MAX_ATTEMPTS,"error":str(exc)[:300]},
                            "integration",connection.id)
            failure.retry_count = attempts
            db.commit()
    connection.last_attempt_at=now(); connection.last_success_at=now(); connection.last_error=""
    connection.records_processed=(connection.records_processed or 0)+processed
    db.add(IntegrationLog(connection_id=connection.id,level="success",event="mailbox.polled",
                          details={"messages_processed":processed}))
    mail=db.get(SystemState,"mailbox") or SystemState(key="mailbox",value={})
    mail.value={"status":"Connected","provider":"Microsoft 365","last_check":now().isoformat(),"messages_processed":processed};db.add(mail)
    return processed


def custom_field_retention_job(db):
    forms={form.id:form for form in db.scalars(select(FormDefinition)).all()};removed=0
    for ticket in db.scalars(select(Ticket).where(Ticket.form_definition_id.is_not(None))).all():
        form=forms.get(ticket.form_definition_id);data=dict(ticket.custom_data or {});changed=[]
        for field in (form.fields or []) if form else []:
            days=field.get("retention_days");key=field.get("key")
            if days and key in data and ticket.created_at.replace(tzinfo=ticket.created_at.tzinfo or now().tzinfo)<now()-timedelta(days=int(days)):
                data.pop(key,None);changed.append(key);removed+=1
        if changed:
            ticket.custom_data=data;audit(db,"custom_fields.retained_data_removed","ticket",ticket.id,new={"field_keys":changed})
    return removed


def assetpilot_sync_job(db):
    """Idempotently synchronize the bundled AssetPilot database on a short cadence."""
    if not settings.assetpilot_enabled:
        return 0
    source = None if settings.database_url.startswith("postgresql") else (
        Path(settings.assetpilot_database_path) if settings.assetpilot_database_path else None
    )
    if not settings.database_url.startswith("postgresql") and (not source or not source.is_file()):
        return 0
    state = db.get(SystemState, "assetpilot_sync") or SystemState(key="assetpilot_sync", value={})
    value = dict(state.value or {})
    last_attempt = value.get("last_attempt")
    if last_attempt:
        try:
            previous = datetime.fromisoformat(last_attempt)
            if now() - previous < timedelta(minutes=max(1, settings.assetpilot_sync_minutes)):
                return int(value.get("assets_seen", 0))
        except (TypeError, ValueError):
            pass
    attempted_at = now()
    try:
        result = import_assetpilot(db, source)
        state.value = {
            "status": "Ready",
            "last_attempt": attempted_at.isoformat(),
            "last_success": now().isoformat(),
            "assets_seen": result["assets_created"] + result["assets_updated"],
            "employees_seen": result["employees_created"] + result["employees_updated"],
            "last_error": "",
        }
        db.add(state)
        return int(state.value["assets_seen"])
    except Exception as exc:
        state.value = {
            **value,
            "status": "Error",
            "last_attempt": attempted_at.isoformat(),
            "last_error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }
        db.add(state)
        return 0


def smart_self_service_job(db):
    """Evaluate unrated open tickets idempotently; the feature is off by default."""
    from .models import SelfServiceAttempt
    closed = [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED, TicketStatus.REJECTED]
    tickets = db.scalars(select(Ticket).where(
        Ticket.status.notin_(closed),
        ~Ticket.id.in_(select(SelfServiceAttempt.ticket_id)),
    ).order_by(Ticket.created_at).limit(100)).all()
    returned = return_unanswered_to_it(db)
    evaluated = sum(1 for ticket in tickets if evaluate_ticket(db, ticket) is not None)
    return returned + evaluated


def smart_self_service_all_organizations():
    """Run tenant-scoped evaluations for every active organization."""
    discovery = SessionLocal()
    try:
        organization_ids = discovery.scalars(select(Organization.id).where(
            Organization.active.is_(True)).order_by(Organization.id)).all()
    finally:
        discovery.close()
    evaluated = 0
    for organization_id in organization_ids:
        tenant_db = SessionLocal()
        tenant_db.info["organization_id"] = organization_id
        try:
            evaluated += smart_self_service_job(tenant_db)
            tenant_db.commit()
        except Exception as exc:
            tenant_db.rollback()
            fail_automation(tenant_db, "smart_self_service", "Smart Self-Service evaluation failed",
                            {"error": str(exc)[:500]})
            tenant_db.commit()
        finally:
            tenant_db.close()
    return evaluated


def https_certificate_health_job(db):
    """Hourly repair for a custom certificate that Caddy is not serving."""
    monitor = db.get(SystemState, "https_certificate_monitor") or SystemState(
        key="https_certificate_monitor", value={}
    )
    db.add(monitor)
    previous = dict(monitor.value or {})
    checked_at = now()
    try:
        last_check = datetime.fromisoformat(str(previous.get("last_check") or "").replace("Z", "+00:00"))
        if last_check.tzinfo is None:
            last_check = last_check.replace(tzinfo=checked_at.tzinfo)
        if checked_at - last_check < _HTTPS_CERTIFICATE_CHECK_INTERVAL:
            return 0
    except (TypeError, ValueError):
        pass
    monitor.value = {**previous, "last_check": checked_at.isoformat(), "status": "Checked"}

    from . import certificate_api
    from .caddy_tls import (caddyfile_uses_custom_certificate, certificate_paths,
                            installed_certificate_fingerprint, read_certificate_state,
                            replace_tls_directive, selected_tls_directive)

    state = read_certificate_state(certificate_api._root())
    if state.get("mode") != "custom":
        return 0
    root = certificate_api._root()
    caddyfile = root / "Caddyfile"
    directive, warning = selected_tls_directive(root)

    # A missing, unreadable, or expired custom certificate is not a transient
    # listener failure. Fall back immediately, but only change/restart Caddy
    # when it is not already using the internal certificate. Remember the
    # warning so the same condition creates one operator alert, not one hourly.
    if directive == "tls internal":
        cycled = False
        try:
            source = caddyfile.read_text(encoding="utf-8")
            if not any(line.strip() == "tls internal" for line in source.splitlines()):
                pending = caddyfile.with_suffix(".pending")
                pending.write_text(replace_tls_directive(source, directive), encoding="utf-8")
                os.replace(pending, caddyfile)
                certificate_api._cycle_https_service()
                cycled = True
        except Exception as exc:
            warning = warning or f"HTTPS certificate fallback failed: {type(exc).__name__}: {str(exc)[:300]}"
        monitor.value = {
            **monitor.value,
            "status": "Needs attention",
            "consecutive_failures": 0,
            "last_error": warning,
            "last_warning": warning,
        }
        if warning and warning != previous.get("last_warning"):
            fail_automation(db, "https_certificate", "Custom HTTPS certificate is not being served",
                            {"error": warning, "served_fingerprint": "internal"},
                            related_type="https_certificate", related_id="custom")
        return 1 if cycled else 0

    expected = str(state.get("fingerprint_sha256") or "").upper()
    if not expected:
        try:
            expected = installed_certificate_fingerprint(certificate_paths(certificate_api._root())[0])
        except (OSError, ValueError):
            expected = ""
    try:
        served = certificate_api._served_certificate_fingerprint(timeout_seconds=3)
    except RuntimeError:
        served = ""
    if expected and served == expected and caddyfile_uses_custom_certificate(root):
        monitor.value = {**monitor.value, "status": "Healthy", "consecutive_failures": 0}
        return 0

    consecutive_failures = int(previous.get("consecutive_failures") or 0) + 1
    monitor.value = {
        **monitor.value,
        "status": "Check failed",
        "consecutive_failures": consecutive_failures,
        "served_fingerprint_sha256": served or None,
    }
    if consecutive_failures < 2:
        return 0

    try:
        pending = caddyfile.with_suffix(".pending")
        pending.write_text(replace_tls_directive(caddyfile.read_text(encoding="utf-8"), directive), encoding="utf-8")
        os.replace(pending, caddyfile)
        certificate_api._restart_https(state)
        try:
            served = certificate_api._served_certificate_fingerprint(timeout_seconds=3)
        except RuntimeError:
            served = ""
        healthy = bool(expected and served == expected and caddyfile_uses_custom_certificate(root))
        if healthy:
            monitor.value = {**monitor.value, "status": "Repaired", "consecutive_failures": 0,
                             "served_fingerprint_sha256": served}
            audit(db, "https_certificate.repaired", "https_certificate", None,
                  new={"served_fingerprint_sha256": served})
            return 1
        reason = warning or "The live HTTPS listener still presents a different certificate after repair."
    except Exception as exc:
        reason = f"HTTPS certificate repair failed: {type(exc).__name__}: {str(exc)[:300]}"

    monitor.value = {**monitor.value, "status": "Needs attention", "last_error": reason}
    fail_automation(db, "https_certificate", "Custom HTTPS certificate is not being served",
                    {"error": reason, "expected_fingerprint": expected,
                     "served_fingerprint": served or "unavailable"},
                    related_type="https_certificate", related_id="custom")
    return 0


def run_once():
    db=SessionLocal(); organization_id=db.scalar(select(Organization.id).where(Organization.active.is_(True)).order_by(Organization.id).limit(1))
    if organization_id: db.info["organization_id"]=organization_id
    state=db.get(SystemState,"worker") or SystemState(key="worker",value={});db.add(state)
    try:
        synchronized_assets = assetpilot_sync_job(db)
        sla_job(db)
        retained = custom_field_retention_job(db)
        self_service_evaluated = smart_self_service_all_organizations()
        certificate_repairs = https_certificate_health_job(db)
        processed = microsoft_mailbox_job(db)
        delivered = email_notification_job(db)
        host=os.getenv("ITSM_IMAP_HOST")
        if host:
            port=int(os.getenv("ITSM_IMAP_PORT","993"));username=os.environ["ITSM_IMAP_USERNAME"]
            target=os.getenv("ITSM_MAIL_SECRET_TARGET","NorthstarDesk/imap");password=keyring.get_password(target,username)
            if not password: raise RuntimeError("Mailbox credential is not available in Windows Credential Manager")
            with imaplib.IMAP4_SSL(host,port) as client:
                client.login(username,password);client.select("INBOX");_,ids=client.search(None,"UNSEEN")
                processed=0
                for message_no in ids[0].split():
                    _,data=client.fetch(message_no,"(RFC822)");process_message(db,data[0][1]);client.store(message_no,"+FLAGS","\\Seen");processed+=1
                mail=db.get(SystemState,"mailbox") or SystemState(key="mailbox",value={});mail.value={"status":"Connected","last_check":now().isoformat(),"messages_processed":processed};db.add(mail)
        state.value={"status":"Ready","last_heartbeat":now().isoformat(),"scheduled_jobs":"healthy","emails_received":processed,"emails_delivered":delivered,"retained_fields_removed":retained,"assetpilot_assets_seen":synchronized_assets,"self_service_evaluated":self_service_evaluated,"https_certificate_repairs":certificate_repairs};db.commit()
    except Exception as exc:
        db.rollback();fail_automation(db,"worker","Background worker run failed",{"error":str(exc)[:500]});state=db.get(SystemState,"worker") or SystemState(key="worker",value={});state.value={"status":"Error","last_heartbeat":now().isoformat()};db.add(state);db.commit()
    finally:db.close()


def main():
    interval=max(30,int(os.getenv("ITSM_WORKER_INTERVAL","60")))
    print(f"Northstar Desk worker running every {interval} seconds")
    from .ringcentral import supervisor as ringcentral_supervisor
    threading.Thread(target=ringcentral_supervisor,name="ringcentral-supervisor",daemon=True).start()
    while True: run_once();time.sleep(interval)

if __name__=="__main__":main()

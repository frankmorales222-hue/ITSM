"""Background worker for IMAP intake, notifications, SLA checks, and heartbeat.

Mailbox passwords are read from Windows Credential Manager through keyring. Run
scripts/configure-mail-secret.ps1 once, then set the non-secret IMAP variables.
"""
import email
import imaplib
import os
import re
import time
from datetime import timedelta
from email.header import decode_header, make_header
from email.policy import default
import keyring
from sqlalchemy import select
from .database import SessionLocal
from .models import EmailMessage, Notification, Organization, Role, SystemState, Ticket, TicketMessage, TicketStatus, User, now
from .services import audit, fail_automation, is_automated_email, next_ticket_number, notify, route_ticket, sla_dates


def text_body(message):
    candidates = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_disposition() == "attachment": continue
        if part.get_content_type() == "text/plain":
            try: candidates.append(part.get_content())
            except Exception: pass
    body = "\n".join(candidates).strip()
    body = re.split(r"\nOn .+ wrote:\s*\n|\nFrom:\s.+\nSent:\s", body, maxsplit=1)[0]
    return body[:20000]


def attachment_metadata(message):
    result = []
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            payload = part.get_payload(decode=True) or b""
            result.append({"name": str(make_header(decode_header(filename))), "content_type": part.get_content_type(), "size": len(payload)})
    return result


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
        requester = db.scalar(select(User).where(User.email == sender, User.active.is_(True)))
        if not requester:
            fail_automation(db,"email_requester","Requester could not be identified",{"sender":sender,"message_id":message_id}); status="failed"; ticket=None
        else:
            refs = [msg.get("In-Reply-To"), *(msg.get("References","").split())]
            prior = db.scalar(select(EmailMessage).where(EmailMessage.message_id.in_([r for r in refs if r])).order_by(EmailMessage.id.desc())) if any(refs) else None
            if prior and prior.ticket_id:
                ticket=db.get(Ticket,prior.ticket_id); db.add(TicketMessage(ticket_id=ticket.id,author_id=requester.id,body=text_body(msg),kind="public",source="email")); status="threaded"
                notify(db,ticket.assigned_user_id,"user.replied",f"Email reply on {ticket.number}",text_body(msg)[:200],ticket.id)
            else:
                team,tech,reason=route_ticket(db,"General",requester); first,due=sla_dates("Medium")
                ticket=Ticket(number=next_ticket_number(db,"Report an issue"),request_type="Report an issue",subject=subject[:240],description=text_body(msg),requester_id=requester.id,team_id=team.id,assigned_user_id=tech.id if tech else None,status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW,priority="Medium",impact="Medium",urgency="Medium",category="General",route_reason=reason,first_response_due=first,resolution_due=due)
                db.add(ticket);db.flush();db.add(TicketMessage(ticket_id=ticket.id,author_id=requester.id,body=text_body(msg),kind="public",source="email"));status="created"
                notify(db,requester.id,"ticket.created",f"{ticket.number} created from email","Your email was received. Attachment contents were not stored." if attachments else "Your email was received.",ticket.id)
    db.add(EmailMessage(message_id=message_id,in_reply_to=msg.get("In-Reply-To"),ticket_id=ticket.id if ticket else None,sender=sender,subject=subject,attachment_metadata=attachments,processing_status=status))
    audit(db,f"email.{status}","ticket",ticket.id if ticket else None,new={"message_id":message_id,"attachments":len(attachments)});return status


def sla_job(db):
    open_tickets=db.scalars(select(Ticket).where(Ticket.status.notin_([TicketStatus.RESOLVED,TicketStatus.CLOSED,TicketStatus.CANCELLED]))).all()
    for ticket in open_tickets:
        remaining=ticket.resolution_due.replace(tzinfo=ticket.resolution_due.tzinfo or now().tzinfo)-now()
        event="sla.breached" if remaining.total_seconds()<0 else "sla.warning" if remaining<timedelta(hours=4) else None
        if event and not db.scalar(select(Notification).where(Notification.ticket_id==ticket.id,Notification.event==event)):
            notify(db,ticket.assigned_user_id,event,f"{ticket.number} {'breached' if event.endswith('breached') else 'approaching'} SLA",ticket.subject,ticket.id)


def run_once():
    db=SessionLocal(); organization_id=db.scalar(select(Organization.id).where(Organization.active.is_(True)).order_by(Organization.id).limit(1))
    if organization_id: db.info["organization_id"]=organization_id
    state=db.get(SystemState,"worker") or SystemState(key="worker",value={});db.add(state)
    try:
        sla_job(db)
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
        state.value={"status":"Ready","last_heartbeat":now().isoformat(),"scheduled_jobs":"healthy"};db.commit()
    except Exception as exc:
        db.rollback();fail_automation(db,"worker","Background worker run failed",{"error":str(exc)[:500]});state=db.get(SystemState,"worker") or SystemState(key="worker",value={});state.value={"status":"Error","last_heartbeat":now().isoformat()};db.add(state);db.commit()
    finally:db.close()


def main():
    interval=max(30,int(os.getenv("ITSM_WORKER_INTERVAL","60")))
    print(f"Northstar Desk worker running every {interval} seconds")
    while True: run_once();time.sleep(interval)

if __name__=="__main__":main()

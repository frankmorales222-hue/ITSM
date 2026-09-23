from email.message import EmailMessage as MimeMessage

from sqlalchemy import select

from itsm.database import SessionLocal
from itsm.models import EmailMessage, Employee, IntegrationConnection, Notification, Organization, Role, RoutingRule, SupportQueue, Team, TeamMembership, TelephonyCall, Ticket, TicketMessage, TicketStatus, User
from itsm.ringcentral import process_telephony_event
from itsm.services import ticket_email_subject
from itsm.worker import email_notification_job, process_message


def _tenant(db):
    organization_id=db.scalar(select(Organization.id).order_by(Organization.id))
    db.info["organization_id"]=organization_id
    return organization_id


def test_email_subject_ticket_number_threads_reply():
    with SessionLocal() as db:
        _tenant(db)
        requester=db.scalar(select(User).where(User.username=="user1"))
        existing=db.scalar(select(Ticket).where(Ticket.requester_id==requester.id).order_by(Ticket.id))
        message=MimeMessage();message["Message-ID"]="<northstar-thread-test@example.test>"
        message["From"]=requester.email;message["To"]="helpdesk@example.test"
        message["Subject"]=f"Re: [{existing.number}] More information"
        message.set_content("The issue also happens after restarting.")
        assert process_message(db,message.as_bytes())=="threaded"
        db.commit()
        saved=db.scalar(select(TicketMessage).where(TicketMessage.ticket_id==existing.id,
                                                     TicketMessage.source=="email").order_by(TicketMessage.id.desc()))
        assert "after restarting" in saved.body


def test_ticket_notification_subject_always_contains_thread_reference():
    with SessionLocal() as db:
        _tenant(db)
        ticket=db.scalar(select(Ticket).order_by(Ticket.id))
        assert ticket_email_subject(ticket,"Requester added more information").startswith(f"[{ticket.number}] ")
        existing=f"Re: [{ticket.number}] Existing thread"
        assert ticket_email_subject(ticket,existing)==existing


def test_legacy_reply_without_headers_threads_by_unique_requester_subject():
    with SessionLocal() as db:
        _tenant(db)
        requester = db.scalar(select(User).where(User.username == "user1"))
        existing = db.scalar(select(Ticket).where(Ticket.requester_id == requester.id).order_by(Ticket.id))
        existing.subject = "Unique legacy email subject for threading"
        db.flush()
        message = MimeMessage()
        message["Message-ID"] = "<legacy-subject-only-reply@example.test>"
        message["From"] = requester.email
        message["To"] = "helpdesk@example.test"
        message["Subject"] = f"Re: {existing.subject}"
        message.set_content("This reply has no provider threading headers.")
        assert process_message(db, message.as_bytes()) == "threaded"
        assert db.scalar(select(Ticket).where(Ticket.subject == f"Re: {existing.subject}")) is None
        db.rollback()


def test_reply_to_outbound_graph_notification_threads_without_subject_reference(monkeypatch):
    """A reply remains on its ticket even when the mail client rewrites the subject."""
    from itsm import worker

    outbound_id = "<northstar-outbound-provider-id@example.test>"
    with SessionLocal() as db:
        organization_id = _tenant(db)
        ticket = db.scalar(select(Ticket).order_by(Ticket.id))
        requester = db.get(User, ticket.requester_id)
        for pending in db.scalars(select(Notification).where(Notification.delivery_status == "pending_email")):
            pending.delivery_status = "suppressed"
        connection = IntegrationConnection(
            organization_id=organization_id, name="Threading Graph test", kind="email",
            provider="Microsoft 365", enabled=True, status="Connected",
            configuration={"mailbox":"helpdesk@example.test"},
        )
        db.add(connection)
        db.add(Notification(organization_id=organization_id, user_id=requester.id, ticket_id=ticket.id,
                            event="technician.replied", title="A technician responded",
                            body="Please review the response.", delivery_status="pending_email"))
        db.flush()

        monkeypatch.setattr(worker, "notification_delivery_enabled", lambda _db: True)
        monkeypatch.setattr(worker, "outbound_email_delivery_enabled", lambda _db: True)
        monkeypatch.setattr(worker, "connected_mailbox", lambda _db: connection)
        monkeypatch.setattr(worker, "send_notification", lambda *_args, **_kwargs: outbound_id)
        assert email_notification_job(db) == 1
        saved = db.scalar(select(EmailMessage).where(EmailMessage.message_id == outbound_id))
        assert saved and saved.ticket_id == ticket.id and saved.processing_status == "outbound"

        reply = MimeMessage()
        reply["Message-ID"] = "<northstar-reply-with-rewritten-subject@example.test>"
        reply["In-Reply-To"] = outbound_id
        reply["References"] = f"<unrelated@example.test> {outbound_id}"
        reply["From"] = requester.email
        reply["To"] = "helpdesk@example.test"
        reply["Subject"] = "Re: Your support update"
        reply.set_content("This belongs on the existing request.")
        assert process_message(db, reply.as_bytes()) == "threaded"
        assert db.scalar(select(Ticket).where(Ticket.subject == "Re: Your support update")) is None
        db.rollback()


def test_inbound_email_domain_rule_round_robins_across_team_members():
    with SessionLocal() as db:
        organization_id=_tenant(db)
        techs=db.scalars(select(User).where(User.role==Role.TECHNICIAN,User.active.is_(True)).order_by(User.id).limit(2)).all()
        assert len(techs)==2
        for tech in techs: tech.availability="Available"
        team=Team(organization_id=organization_id,name="Email Domain Routing Test",queue_name="Email Domain Routing Test",active=True)
        db.add(team);db.flush()
        queue=SupportQueue(organization_id=organization_id,name="Email Domain Queue Test",team_id=team.id,
                           assignment_strategy="round_robin",active=True)
        db.add(queue);db.flush()
        for tech in techs:
            db.add(TeamMembership(organization_id=organization_id,team_id=team.id,user_id=tech.id,active=True))
        db.add(RoutingRule(organization_id=organization_id,name="Example email domain route test",priority_order=-1000,
                           trigger="ticket.created",status="active",active=True,stop_processing=True,
                           conditions={"logic":"AND","conditions":[
                               {"field":"channel","operator":"equals","value":"email"},
                               {"field":"requester_domain","operator":"equals","value":"example.test"},
                           ]},actions={"queue_id":queue.id,"assignment_strategy":"round_robin"}))
        db.flush()

        assigned=[]
        for index,username in enumerate(("user1","user2"),start=1):
            requester=db.scalar(select(User).where(User.username==username))
            message=MimeMessage();message["Message-ID"]=f"<domain-round-robin-{index}@example.test>"
            message["From"]=requester.email;message["To"]="helpdesk@example.test"
            message["Subject"]=f"Domain routed request {index}"
            message.set_content("Please route this email using the configured domain rule.")
            assert process_message(db,message.as_bytes())=="created"
            inbound=db.scalar(select(Ticket).join(TicketMessage).where(
                TicketMessage.source=="email",Ticket.subject==f"Domain routed request {index}").order_by(Ticket.id.desc()))
            assert inbound.team_id==team.id
            assigned.append(inbound.assigned_user_id)
        assert assigned==[techs[0].id,techs[1].id]
        db.rollback()


def test_requester_email_can_explicitly_close_waiting_ticket():
    with SessionLocal() as db:
        _tenant(db)
        requester=db.scalar(select(User).where(User.username=="user1"))
        existing=db.scalar(select(Ticket).where(Ticket.requester_id==requester.id).order_by(Ticket.id))
        existing.status=TicketStatus.WAITING_USER
        message=MimeMessage();message["Message-ID"]="<northstar-close-request@example.test>"
        message["From"]=requester.email;message["To"]="helpdesk@example.test"
        message["Subject"]=f"Re: [{existing.number}] Closure approval"
        message.set_content("It is okay to close the ticket")
        assert process_message(db,message.as_bytes())=="threaded"
        db.commit()
        assert existing.status==TicketStatus.CLOSED
        note=db.scalar(select(TicketMessage).where(TicketMessage.ticket_id==existing.id,
                                                    TicketMessage.source=="system").order_by(TicketMessage.id.desc()))
        assert note and requester.display_name in note.body


def test_new_email_requester_is_created_without_asset_inventory():
    sender = "new-requester-independent@example.test"
    with SessionLocal() as db:
        organization_id = _tenant(db)
        existing = db.scalar(select(User).where(User.email == sender))
        if existing:
            db.delete(existing)
            db.flush()
        message = MimeMessage()
        message["Message-ID"] = "<northstar-independent-requester@example.test>"
        message["From"] = f"Independent Requester <{sender}>"
        message["To"] = "helpdesk@example.test"
        message["Subject"] = "Request without asset inventory"
        message.set_content("Please create this ticket without AssetPilot.")

        assert process_message(db, message.as_bytes()) == "created"
        requester = db.scalar(select(User).where(User.email == sender))
        assert requester is not None
        assert requester.organization_id == organization_id
        assert requester.role == Role.END_USER
        assert requester.auth_source == "Email"
        assert db.scalar(select(Employee).where(Employee.user_id == requester.id)) is None
        ticket = db.scalar(select(Ticket).where(Ticket.requester_id == requester.id))
        assert ticket is not None
        db.rollback()


def test_ringcentral_inbound_call_creates_one_ticket_and_maps_answering_tech():
    with SessionLocal() as db:
        organization_id=_tenant(db)
        connection=IntegrationConnection(name="RingCentral call test",kind="telephony",provider="RingCentral",
                                         enabled=True,status="Connected",configuration={"ticket_creation_policy":"answered_or_destination"})
        db.add(connection);db.flush()
        tech=db.scalar(select(User).where(User.username=="tech1"));tech.ringcentral_extension_id="rc-tech-1"
        payload={"uuid":"event-one","body":{"telephonySessionId":"session-one","eventTime":"2026-08-13T12:00:00Z","parties":[
            {"direction":"Inbound","status":{"code":"Proceeding"},"from":{"phoneNumber":"+15551234567"},"to":{"phoneNumber":"+15557654321","extensionId":"support-queue"}},
            {"direction":"Outbound","extensionId":"rc-tech-1","status":{"code":"Answered"},"to":{"extensionNumber":"101"}},
        ]}}
        call=process_telephony_event(db,connection,payload);db.commit()
        assert call and call.ticket_id
        ticket=db.get(Ticket,call.ticket_id)
        assert ticket.assigned_user_id==tech.id
        assert ticket.category=="Phone Support"
        assert process_telephony_event(db,connection,{**payload,"uuid":"event-two"}).ticket_id==ticket.id
        assert db.scalar(select(TelephonyCall).where(TelephonyCall.organization_id==organization_id,
                                                     TelephonyCall.session_id=="session-one"))


def test_ringcentral_ignores_unanswered_calls_outside_configured_help_desk_destinations():
    with SessionLocal() as db:
        _tenant(db)
        connection=IntegrationConnection(name="Restricted RingCentral",kind="telephony",provider="RingCentral",
                                         enabled=True,status="Connected",configuration={
                                             "ticket_creation_policy":"answered_or_destination",
                                             "call_queue_ids":["support-queue"],
                                         })
        db.add(connection);db.flush()
        payload={"uuid":"ignored-event","body":{"telephonySessionId":"ignored-session","parties":[
            {"direction":"Inbound","status":{"code":"Proceeding"},"from":{"phoneNumber":"+15551234567"},
             "to":{"phoneNumber":"+15550009999","extensionId":"sales-queue"}},
        ]}}
        assert process_telephony_event(db,connection,payload) is None
        assert db.scalar(select(TelephonyCall).where(TelephonyCall.session_id=="ignored-session")) is None


def test_ringcentral_configured_destination_creates_ticket_before_answer():
    with SessionLocal() as db:
        _tenant(db)
        connection=IntegrationConnection(name="Help desk destination",kind="telephony",provider="RingCentral",
                                         enabled=True,status="Connected",configuration={
                                             "ticket_creation_policy":"answered_or_destination",
                                             "call_queue_ids":"support-queue, 800",
                                         })
        db.add(connection);db.flush()
        payload={"uuid":"queue-event","body":{"telephonySessionId":"queue-session","parties":[
            {"direction":"Inbound","status":{"code":"Proceeding"},"from":{"phoneNumber":"+15551234567"},
             "to":{"phoneNumber":"+15557654321","extensionId":"support-queue","extensionNumber":"800"}},
        ]}}
        call=process_telephony_event(db,connection,payload)
        assert call and call.ticket_id


def test_ringcentral_answered_policy_requires_a_mapped_technician():
    with SessionLocal() as db:
        _tenant(db)
        connection=IntegrationConnection(name="Answered tech only",kind="telephony",provider="RingCentral",
                                         enabled=True,status="Connected",configuration={
                                             "ticket_creation_policy":"answered_technician",
                                         })
        db.add(connection);db.flush()
        payload={"uuid":"unmapped-answer","body":{"telephonySessionId":"unmapped-session","parties":[
            {"direction":"Inbound","status":{"code":"Proceeding"},"from":{"phoneNumber":"+15551234567"},
             "to":{"extensionId":"any-queue"}},
            {"direction":"Outbound","extensionId":"not-a-tech","status":{"code":"Answered"},
             "to":{"extensionNumber":"999"}},
        ]}}
        assert process_telephony_event(db,connection,payload) is None

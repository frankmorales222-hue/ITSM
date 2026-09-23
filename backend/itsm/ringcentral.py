"""RingCentral telephony-session listener and call-to-ticket automation."""
from __future__ import annotations

import base64
import json
import re
import secrets
import threading
import time
import uuid
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .credential_store import get_integration_secret, set_integration_secret
from .database import SessionLocal
from .models import (IntegrationConnection, IntegrationLog, Organization, Role, TelephonyCall,
                     Ticket, TicketMessage, TicketStatus, User, now)
from .security import hash_password
from .services import audit, next_ticket_number, notify, route_ticket, sla_dates


def _host(environment: str) -> str:
    return "platform.devtest.ringcentral.com" if environment.lower() in {"sandbox", "devtest"} else "platform.ringcentral.com"


def _application(db: Session) -> tuple[str, str, str]:
    client_id=settings.ringcentral_client_id or get_integration_secret(db,"platform:ringcentral","client_id") or ""
    client_secret=settings.ringcentral_client_secret or get_integration_secret(db,"platform:ringcentral","client_secret") or ""
    environment=get_integration_secret(db,"platform:ringcentral","environment") or settings.ringcentral_environment
    if not client_id or not client_secret: raise RuntimeError("RingCentral application credentials are not configured")
    return client_id,client_secret,environment


def refresh_access_token(db: Session, connection: IntegrationConnection) -> str:
    refresh=get_integration_secret(db,f"connection:{connection.id}","refresh_token")
    if not refresh: raise RuntimeError("Reconnect RingCentral to obtain a refresh token")
    client_id,client_secret,environment=_application(db)
    basic=base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    response=httpx.post(f"https://{_host(environment)}/restapi/oauth/token",
                        headers={"Authorization":f"Basic {basic}"},
                        data={"grant_type":"refresh_token","refresh_token":refresh},timeout=30)
    response.raise_for_status(); token=response.json()
    access=token.get("access_token")
    if not access: raise RuntimeError("RingCentral did not return an access token")
    set_integration_secret(db,f"connection:{connection.id}","access_token",access)
    if token.get("refresh_token"): set_integration_secret(db,f"connection:{connection.id}","refresh_token",token["refresh_token"])
    db.commit(); return access


def test_connection(db: Session, connection: IntegrationConnection) -> dict:
    token=refresh_access_token(db,connection); _,_,environment=_application(db)
    response=httpx.get(f"https://{_host(environment)}/restapi/v1.0/account/~/extension/~",
                       headers={"Authorization":f"Bearer {token}"},timeout=30)
    response.raise_for_status(); profile=response.json()
    connection.status="Connected";connection.last_attempt_at=now();connection.last_success_at=now();connection.last_error=""
    db.add(IntegrationLog(connection_id=connection.id,level="success",event="telephony.test_succeeded",
                          details={"extension":profile.get("extensionNumber"),"message":"RingCentral API access verified."}))
    return profile


def _phone(value: str | None) -> str:
    digits=re.sub(r"\D","",value or "")
    return digits[-10:] if len(digits)>=10 else digits


def _party_value(party: dict, side: str, key: str) -> str:
    nested=party.get(side) or {}
    return str(nested.get(key) or party.get(f"{side}{key[0].upper()}{key[1:]}") or "")


def _call_body(payload) -> tuple[dict | None,str]:
    event_id=""
    stack=list(payload if isinstance(payload,list) else [payload])
    while stack:
        item=stack.pop(0)
        if not isinstance(item,dict): continue
        event_id=event_id or str(item.get("uuid") or item.get("messageId") or "")
        body=item.get("body")
        if isinstance(body,dict) and (body.get("telephonySessionId") or body.get("sessionId")): return body,event_id
        for value in item.values():
            if isinstance(value,dict): stack.append(value)
            elif isinstance(value,list): stack.extend(value)
    return None,event_id


def _requester_for_phone(db: Session, number: str, always_new: bool=False) -> User:
    normalized=_phone(number)
    if not always_new:
        for user in db.scalars(select(User).where(User.active.is_(True))).all():
            if normalized and normalized in {_phone(user.phone),_phone(user.ringcentral_extension_number)}: return user
    suffix=normalized[-4:] or "unknown"; marker=secrets.token_hex(3)
    user=User(username=f"rc-{db.info['organization_id']}-{suffix}-{marker}",
              email=f"caller-{db.info['organization_id']}-{suffix}-{marker}@caller.invalid",
              display_name=f"Caller ending {suffix}",password_hash=hash_password(secrets.token_urlsafe(32)),
              role=Role.END_USER,active=True,must_change_password=False,phone=number,auth_source="RingCentral")
    db.add(user);db.flush();return user


def _mapped_technician(db: Session, extension_id: str, extension_number: str="") -> User | None:
    technician_roles=(Role.TECHNICIAN,Role.TEAM_LEAD,Role.MANAGER,Role.ADMIN)
    if extension_id:
        user=db.scalar(select(User).where(User.ringcentral_extension_id==extension_id,
                                          User.role.in_(technician_roles),User.active.is_(True)))
        if user:return user
    if extension_number:
        return db.scalar(select(User).where(User.ringcentral_extension_number==extension_number,
                                            User.role.in_(technician_roles),User.active.is_(True)))
    return None


def _answered_technician(db: Session, parties: list[dict]) -> tuple[User | None,str,str]:
    """Return only an active ITSM technician that actually answered the call."""
    for party in parties:
        if str((party.get("status") or {}).get("code") or "").lower()!="answered":continue
        for side in (party,party.get("to") or {},party.get("from") or {}):
            extension_id=str(side.get("extensionId") or "")
            extension_number=str(side.get("extensionNumber") or "")
            technician=_mapped_technician(db,extension_id,extension_number)
            if technician:return technician,extension_id,extension_number
    return None,"",""


def _configured_destinations(config: dict) -> list[str]:
    values=config.get("call_queue_ids") or []
    if isinstance(values,str):values=values.split(",")
    return [str(value).strip() for value in values if str(value).strip()]


def _destination_matches(config: dict,party: dict) -> bool:
    configured=_configured_destinations(config)
    if not configured:return False
    target=party.get("to") or {}
    observed=[str(target.get(key) or "").strip() for key in ("extensionId","extensionNumber","phoneNumber")]
    for expected in configured:
        for actual in observed:
            if actual and expected.casefold()==actual.casefold():return True
            expected_phone,actual_phone=_phone(expected),_phone(actual)
            if len(expected_phone)>=7 and expected_phone==actual_phone:return True
    return False


def process_telephony_event(db: Session, connection: IntegrationConnection, payload) -> TelephonyCall | None:
    body,event_id=_call_body(payload)
    if not body:return None
    parties=list(body.get("parties") or [])
    if not parties:return None
    inbound=[p for p in parties if str(p.get("direction","")).lower()=="inbound"]
    if not inbound:return None
    party=inbound[0]
    session_id=str(body.get("telephonySessionId") or body.get("sessionId") or "")
    if not session_id:return None
    caller=_party_value(party,"from","phoneNumber")
    destination=_party_value(party,"to","phoneNumber")
    queue_id=str((party.get("to") or {}).get("extensionId") or body.get("queueId") or "")
    statuses=[str((p.get("status") or {}).get("code") or "") for p in parties]
    status="Answered" if "Answered" in statuses else "Disconnected" if "Disconnected" in statuses else "Ringing"
    answered_tech,extension_id,extension_number=_answered_technician(db,parties)
    call=db.scalar(select(TelephonyCall).where(TelephonyCall.provider=="RingCentral",TelephonyCall.session_id==session_id))
    config=connection.configuration or {}
    destination_match=_destination_matches(config,party)
    policy=config.get("ticket_creation_policy") or "answered_or_destination"
    # Preserve old saved values, but never treat an empty destination list as every call.
    policy={"incoming_calls":"configured_destination","answered_calls":"answered_technician"}.get(policy,policy)
    should_create=(
        (policy=="answered_technician" and answered_tech is not None) or
        (policy=="configured_destination" and destination_match) or
        (policy=="answered_or_destination" and (answered_tech is not None or destination_match))
    )
    if not call and not should_create:return None
    if not call:
        call=TelephonyCall(connection_id=connection.id,provider="RingCentral",session_id=session_id,event_id=event_id,
                           caller_number=caller,destination_number=destination,queue_id=queue_id,status=status,
                           answered_extension_id=extension_id,safe_payload={"event_time":body.get("eventTime"),"statuses":statuses})
        db.add(call);db.flush()
        requester=_requester_for_phone(db,caller,config.get("caller_match")=="always_new")
        team,routed,reason=route_ticket(db,"Phone Support",requester)
        tech=answered_tech or routed
        first,due=sla_dates("Medium")
        ticket=Ticket(number=next_ticket_number(db,"Report an issue"),request_type="Report an issue",
                      subject=f"Incoming support call from {requester.display_name}",
                      description=f"RingCentral call received from {caller or 'unknown caller'} to {destination or 'the support queue'}.",
                      requester_id=requester.id,opened_by_id=requester.id,team_id=team.id,
                      assigned_user_id=tech.id if tech else None,status=TicketStatus.ASSIGNED if tech else TicketStatus.NEW,
                      priority="Medium",impact="Medium",urgency="Medium",category="Phone Support",mode="Phone",
                      route_reason="RingCentral answering technician" if tech and tech!=routed else reason,
                      first_response_due=first,resolution_due=due)
        db.add(ticket);db.flush();call.ticket_id=ticket.id
        db.add(TicketMessage(ticket_id=ticket.id,author_id=requester.id,body=ticket.description,kind="public",source="phone"))
        if not requester.email.endswith("@caller.invalid"):
            notify(db,requester.id,"ticket.created",f"[{ticket.number}] Support call received",ticket.description,ticket.id,email=True)
        notify(db,tech.id if tech else None,"ticket.assigned",f"[{ticket.number}] Phone ticket assigned",ticket.subject,ticket.id,email=True)
        audit(db,"call.ticket_created","ticket",ticket.id,new={"session_id":session_id,"connection_id":connection.id})
    else:
        call.status=status;call.event_id=event_id or call.event_id;call.answered_extension_id=extension_id or call.answered_extension_id
        if call.ticket_id and status=="Answered":
            ticket=db.get(Ticket,call.ticket_id);tech=answered_tech
            if ticket and tech and ticket.assigned_user_id!=tech.id:
                ticket.assigned_user_id=tech.id;ticket.status=TicketStatus.ASSIGNED
                notify(db,tech.id,"ticket.assigned",f"[{ticket.number}] Phone ticket assigned",ticket.subject,ticket.id,email=True)
    connection.last_success_at=now();connection.last_error="";connection.records_processed=(connection.records_processed or 0)+1
    return call


def _listen(connection_id: int,organization_id: int):
    from websockets.sync.client import connect
    while True:
        db=SessionLocal();db.info["organization_id"]=organization_id
        try:
            connection=db.get(IntegrationConnection,connection_id)
            if not connection or not connection.enabled or connection.status!="Connected": return
            token=refresh_access_token(db,connection);_,_,environment=_application(db)
            response=httpx.post(f"https://{_host(environment)}/restapi/oauth/wstoken",
                                headers={"Authorization":f"Bearer {token}"},timeout=30)
            response.raise_for_status();ws_info=response.json()
            uri=f"{ws_info['uri']}?access_token={quote(ws_info['ws_access_token'],safe='')}"
            with connect(uri,open_timeout=30,ping_interval=30,ping_timeout=30) as socket:
                socket.recv()
                socket.send(json.dumps([{"type":"ClientRequest","messageId":str(uuid.uuid4()),"method":"POST","path":"/restapi/v1.0/subscription/"},
                                        {"eventFilters":["/restapi/v1.0/account/~/telephony/sessions"],"deliveryMode":{"transportType":"WebSocket"}}]))
                connection.last_error="";connection.last_success_at=now();db.commit()
                for raw in socket:
                    try:
                        process_telephony_event(db,connection,json.loads(raw));db.commit()
                    except Exception as exc:
                        db.rollback();connection=db.get(IntegrationConnection,connection_id)
                        if connection: connection.last_error=f"Call event failed: {str(exc)[:300]}";db.commit()
        except Exception as exc:
            db.rollback();connection=db.get(IntegrationConnection,connection_id)
            if connection:
                connection.last_attempt_at=now();connection.last_error=f"RingCentral listener reconnecting: {str(exc)[:300]}"
                db.add(IntegrationLog(connection_id=connection_id,level="error",event="telephony.listener_error",details={"message":str(exc)[:300]}));db.commit()
        finally:db.close()
        time.sleep(15)


def supervisor():
    workers:dict[int,threading.Thread]={}
    while True:
        db=SessionLocal()
        try:
            rows=db.execute(select(IntegrationConnection.id,IntegrationConnection.organization_id).where(
                IntegrationConnection.kind=="telephony",IntegrationConnection.provider=="RingCentral",
                IntegrationConnection.enabled.is_(True),IntegrationConnection.status=="Connected",
                IntegrationConnection.archived_at.is_(None))).all()
            for connection_id,organization_id in rows:
                if connection_id not in workers or not workers[connection_id].is_alive():
                    thread=threading.Thread(target=_listen,args=(connection_id,organization_id),name=f"ringcentral-{connection_id}",daemon=True)
                    workers[connection_id]=thread;thread.start()
        finally:db.close()
        time.sleep(30)

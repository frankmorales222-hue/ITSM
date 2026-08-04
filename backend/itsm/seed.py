import argparse
import random
from datetime import date, timedelta
from sqlalchemy import select
from .database import Base, SessionLocal, engine
from .models import *
from .security import hash_password
from .services import audit, sla_dates

TEMP_PASSWORD = "ChangeMe!2026"


def seed(reset=False):
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.scalar(select(User.id).limit(1)):
        print("Database already contains data; seed skipped.")
        return
    departments = [Department(name=n) for n in ["Information Technology", "Finance", "Human Resources", "Clinical Operations", "Administration"]]
    locations = [Location(name=n) for n in ["Main Campus", "North Clinic", "Operations Center"]]
    db.add_all(departments + locations); db.flush()
    teams = [Team(name="Service Desk", queue_name="General Support", is_default=True, skills=["General", "Access", "Software"]),
             Team(name="Endpoint Services", queue_name="Devices", skills=["Hardware"]),
             Team(name="Identity & Access", queue_name="Access Requests", skills=["Access", "Onboarding"])]
    db.add_all(teams); db.flush()
    accounts = [
        ("admin", "admin@example.test", "System Administrator", Role.ADMIN, teams[0]),
        ("manager", "manager@example.test", "IT Manager", Role.MANAGER, teams[0]),
        ("tech1", "tech1@example.test", "Technician One", Role.TECHNICIAN, teams[0]),
        ("tech2", "tech2@example.test", "Technician Two", Role.TECHNICIAN, teams[1]),
        ("tech3", "tech3@example.test", "Technician Three", Role.TECHNICIAN, teams[2]),
        ("lead", "lead@example.test", "Service Desk Lead", Role.TEAM_LEAD, teams[0]),
        ("user1", "user1@example.test", "End User One", Role.END_USER, None),
        ("user2", "user2@example.test", "End User Two", Role.END_USER, None),
        ("user3", "user3@example.test", "End User Three", Role.END_USER, None),
        ("user4", "user4@example.test", "End User Four", Role.END_USER, None),
        ("user5", "user5@example.test", "End User Five", Role.END_USER, None),
        ("auditor", "auditor@example.test", "Reporting Viewer", Role.AUDITOR, None),
    ]
    users = []
    for username, email, name, role, team in accounts:
        user = User(username=username, email=email, display_name=name, role=role, team_id=team.id if team else None,
                    password_hash=hash_password(TEMP_PASSWORD), must_change_password=True)
        db.add(user); users.append(user)
    db.flush()
    employee_names = [("Avery","Brooks"),("Cameron","Diaz"),("Jordan","Ellis"),("Morgan","Flynn"),("Riley","Gray"),
                      ("Casey","Hayes"),("Taylor","Iverson"),("Quinn","Jones"),("Parker","Kim"),("Reese","Lane")]
    employees = []
    for i, (first,last) in enumerate(employee_names):
        linked_user = users[6+i] if i < 5 else None
        emp = Employee(employee_number=f"E{1001+i}", first_name=first, last_name=last, preferred_name=first,
                       work_email=linked_user.email if linked_user else f"{first.lower()}.{last.lower()}@example.test",
                       department_id=departments[i % len(departments)].id, location_id=locations[i % len(locations)].id,
                       job_title=["Analyst","Coordinator","Specialist","Manager"][i%4], start_date=date.today()-timedelta(days=400+i*30),
                       support_region="East", vip=i in (3,8), user_id=linked_user.id if linked_user else None, source="Manual")
        db.add(emp); employees.append(emp)
    db.flush()
    asset_types = ["Laptop","Desktop","Monitor","Phone","Accessory"]
    manufacturers = [("Lenovo","ThinkPad T14"),("Dell","OptiPlex 7010"),("HP","EliteBook 840"),("Apple","iPhone 15"),("Dell","U2424H")]
    assets = []
    for i in range(25):
        make, model = manufacturers[i%5]; assigned = employees[i%10] if i < 20 else None
        asset = Asset(asset_tag=f"AST-{10001+i}", hostname=f"WS-{2001+i}" if i%5 != 4 else None,
                      serial_number=f"SN26{i:05d}" if i%7 != 0 else None, manufacturer=make, model=model,
                      asset_type=asset_types[i%5], status="Active" if assigned else "Stock", condition="Good",
                      location_id=locations[i%3].id, department_id=departments[i%5].id,
                      assigned_employee_id=assigned.id if assigned else None, purchase_date=date.today()-timedelta(days=200+i*20),
                      warranty_expiration=date.today()+timedelta(days=400-i*5), notes="Seeded test asset")
        db.add(asset); assets.append(asset)
    db.flush()
    for asset in assets:
        db.add(AssetHistory(asset_id=asset.id, event_type="initial_assignment", new_value={"employee_id":asset.assigned_employee_id,"status":asset.status}, actor_id=users[0].id))
    statuses = list(TicketStatus)
    subjects = ["Laptop cannot connect to Wi-Fi","Request access to finance folder","Install approved analytics software",
                "Monitor flickers intermittently","New employee equipment setup","Password reset assistance",
                "VPN connection fails","Phone enrollment question","Shared printer unavailable","Account permission review"]
    techs = users[2:5]
    for i in range(30):
        requester = users[6+(i%5)]; status = statuses[i%len(statuses)]; priority = ["Critical","High","Medium","Low"][i%4]
        created = now()-timedelta(hours=i*9+2); first,due = sla_dates(priority, created)
        assigned = None if i%7==0 else techs[i%3]; team = teams[i%3]
        ticket = Ticket(number=f"{'INC' if i%3==0 else 'REQ'}-{i+1:06d}", request_type="Report an issue" if i%3==0 else "Request software",
                        subject=subjects[i%len(subjects)], description="Realistic sample request for local acceptance testing. No sensitive data.",
                        requester_id=requester.id, employee_id=employees[i%10].id, assigned_user_id=assigned.id if assigned else None,
                        team_id=team.id, status=status, priority=priority, impact=["High","Medium","Low"][i%3], urgency=["High","Low","Medium"][i%3],
                        category=["General","Access","Software","Hardware","Onboarding"][i%5], next_action_owner="IT" if "Waiting" not in status.value else "Requester",
                        next_action="Review and progress request", waiting_reason="Additional information required" if "Waiting" in status.value else None,
                        first_response_due=first, resolution_due=due, first_responded_at=created+timedelta(hours=2) if i%4 else None,
                        resolved_at=created+timedelta(hours=12) if status in (TicketStatus.RESOLVED,TicketStatus.CLOSED) else None,
                        closed_at=created+timedelta(hours=20) if status==TicketStatus.CLOSED else None,
                        resolution_summary="Validated service restoration with requester." if status in (TicketStatus.RESOLVED,TicketStatus.CLOSED) else None,
                        restricted=i in (8,23), route_reason=f"Category rule selected {team.name}", created_at=created, updated_at=created+timedelta(hours=3))
        if i%4==0: ticket.assets.append(assets[i%25])
        db.add(ticket); db.flush()
        db.add(TicketMessage(ticket_id=ticket.id, author_id=requester.id, body=ticket.description, kind="public", created_at=created))
        if assigned: db.add(TicketMessage(ticket_id=ticket.id, author_id=assigned.id, body="We are reviewing this request and will provide an update.", kind="public", created_at=created+timedelta(hours=2)))
        db.add(TicketHistory(ticket_id=ticket.id,event_type="created",actor_id=requester.id,new_value={"status":status.value},created_at=created))
        audit(db,"ticket.created","ticket",ticket.id,requester.id,new={"number":ticket.number})
    db.add_all([Sequence(prefix="INC",value=30),Sequence(prefix="REQ",value=30),Sequence(prefix="HR",value=0)])
    db.add(Announcement(title="Planned network maintenance", body="Operations Center connectivity may be intermittent Tuesday 7–8 PM.", severity="warning"))
    db.add(Announcement(title="Attachment policy", body="File attachments are not stored in this test version. Include essential details in the request text.", severity="info"))
    db.add(AutomationFailure(failure_type="notification",summary="Sample notification delivery failure",safe_details={"channel":"email","ticket_number":"INC-000003"}))
    db.add(SystemState(key="mailbox",value={"status":"Not configured","last_check":None,"last_processed":None}))
    db.add(SystemState(key="worker",value={"status":"Ready","last_heartbeat":now().isoformat(),"scheduled_jobs":"healthy"}))
    config_defaults = [
        ("teams","Teams and queues",{"default_queue":"Service Desk","routing_mode":"least_active"},"Default ownership and routing behavior"),
        ("categories","Categories",{"values":["General","Access","Software","Hardware","Onboarding","Network","Security"]},"Available ticket categories"),
        ("assignment","Assignment rules",{"method":"least_active","fallback_team":"Service Desk","exclude_unavailable":True,"category_first":True},"Routing rule controls"),
        ("sla","SLA policies",{"Critical":{"first_response_hours":1,"resolution_hours":4},"High":{"first_response_hours":4,"resolution_hours":16},"Medium":{"first_response_hours":8,"resolution_hours":40},"Low":{"first_response_hours":16,"resolution_hours":80}},"Priority-based service targets"),
        ("calendar","Business hours",{"timezone":"America/New_York","days":["Monday","Tuesday","Wednesday","Thursday","Friday"],"start":"08:00","end":"17:00","holidays":[]},"Default support calendar"),
        ("notifications","Notification templates",{"ticket_created":"Your request {ticket_number} was received.","ticket_resolved":"Your request {ticket_number} was resolved."},"User-facing templates"),
        ("email","Email settings",{"host":"","port":993,"encryption":"TLS","support_address":"","poll_seconds":60,"unknown_sender":"exception","attachment_policy":"accept_metadata_only"},"Non-secret mailbox settings"),
        ("authentication","Local authentication",{"session_minutes":480,"lockout_attempts":5,"lockout_minutes":15,"minimum_password_length":12},"Local security policy"),
        ("retention","Data retention",{"tickets_days":2555,"audit_days":2555,"automation_failures_days":365},"Retention policy; deletion requires an approved external process"),
    ]
    db.add_all([ConfigItem(section=s,name=n,value=v,description=d) for s,n,v,d in config_defaults])
    db.commit(); db.close()
    print(f"Seeded {len(users)} users, {len(employees)} employees, {len(assets)} assets, and 30 tickets.")
    print(f"Temporary password for all test accounts: {TEMP_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--reset", action="store_true")
    seed(parser.parse_args().reset)

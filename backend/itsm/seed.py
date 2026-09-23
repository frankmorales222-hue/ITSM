import argparse
import random
import re
from datetime import date, timedelta
from sqlalchemy import select
from .database import Base, SessionLocal, engine
from .models import *
from .security import hash_password, validate_password
from .services import audit, sla_dates

TEMP_PASSWORD = "ChangeMe!2026"

SYSTEM_ROLE_PERMISSIONS = {
    "end_user": {"tickets": ["view_own", "create"]},
    "technician": {"tickets": ["view_team", "edit", "assign"], "assets": ["view"]},
    "team_lead": {"tickets": ["view_team", "edit", "assign"], "reports": ["view_team"]},
    "manager": {"tickets": ["view_all", "edit", "approve"], "reports": ["view_all", "export"]},
    "admin": {"administration": ["administer"], "integrations": ["configure"], "audit": ["view"], "tickets": ["view_all", "edit", "assign", "approve"]},
    "auditor": {"tickets": ["view_all"], "reports": ["view_all", "export"], "audit": ["view"]},
}
SYSTEM_ROLE_NAMES = {"end_user": "End User", "technician": "Technician", "team_lead": "Team Lead", "manager": "Manager", "admin": "Administrator", "auditor": "Auditor"}
GROUP_TYPE_DEFAULTS = [
    ("Support", "Teams that deliver service", 10), ("Department", "Business departments", 20),
    ("Security", "Security and access groups", 30), ("Approval", "Approval authorities", 40),
    ("Distribution", "Notification distribution", 50), ("Asset ownership", "Asset custodians", 60),
    ("Reporting", "Reporting audiences", 70), ("Custom", "Organization-defined use", 80),
]
EVENT_KEYS = [
    "ticket.created", "ticket.assigned", "ticket.reassigned", "ticket.updated", "ticket.public_reply", "ticket.internal_note",
    "ticket.waiting_on_requester", "ticket.resolved", "ticket.closed", "ticket.reopened", "approval.requested", "approval.reminder",
    "approval.approved", "approval.rejected", "sla.warning", "sla.breached", "incident.major_declared", "incident.status_changed",
    "change.submitted", "change.approved", "change.rejected", "change.scheduled", "call.received", "call.answered", "call.missed",
    "call.abandoned", "voicemail.received", "routing.failed", "integration.failed", "user.created", "user.deactivated",
    "asset.assigned", "asset.returned",
]

PRODUCTION_CONFIG_DEFAULTS = [
    ("teams", "Teams and queues", {"default_queue": "Service Desk", "routing_mode": "round_robin"}, "Default ownership and routing behavior"),
    ("categories", "Categories", {"values": ["General", "Access", "Software", "Hardware", "Onboarding", "Network", "Security"]}, "Available ticket categories"),
    ("assignment", "Assignment rules", {"method": "round_robin", "fallback_team": "Service Desk", "exclude_unavailable": True, "category_first": True}, "Routing rule controls"),
    ("sla", "SLA policies", {"Critical": {"first_response_hours": 1, "resolution_hours": 4}, "High": {"first_response_hours": 4, "resolution_hours": 16}, "Medium": {"first_response_hours": 8, "resolution_hours": 40}, "Low": {"first_response_hours": 16, "resolution_hours": 80}}, "Priority-based service targets"),
    ("calendar", "Business hours", {"timezone": "America/New_York", "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], "start": "08:00", "end": "17:00", "holidays": []}, "Default support calendar"),
    ("notifications", "Notification templates", {"ticket_created": "Your request {ticket_number} was received.", "ticket_resolved": "Your request {ticket_number} was resolved."}, "User-facing templates"),
    ("email", "Email settings", {"host": "", "port": 993, "encryption": "TLS", "support_address": "", "poll_seconds": 60, "unknown_sender": "exception", "attachment_policy": "accept_metadata_only"}, "Non-secret mailbox settings"),
    ("authentication", "Local authentication", {"session_minutes": 480, "lockout_attempts": 5, "lockout_minutes": 15, "minimum_password_length": 12}, "Local security policy"),
    ("retention", "Data retention", {"tickets_days": 2555, "audit_days": 2555, "automation_failures_days": 365}, "Retention policy; deletion requires an approved external process"),
    ("help_desk", "Help Desk Settings", {"help_desk_title": "Help Desk", "tickets_per_page": 50, "auto_reload_seconds": 30, "autoclose_days": 5, "reply_form_position": "bottom", "conversation_order": "oldest_first", "customer_portal": "required_login", "session_minutes": 480, "auto_assign": True, "allow_reopen": True, "require_email": True, "require_subject": True, "require_message": True, "time_tracking": True, "ticket_ratings": True, "attachments_enabled": True, "max_files_per_reply": 10, "max_file_size_mb": 25, "allowed_file_types": ["png", "jpg", "jpeg", "gif", "pdf", "docx", "xlsx", "csv", "txt", "zip"], "login_attempts": 5, "lockout_minutes": 15}, "Ticket behavior, staff workflow, customer access, security, and attachment limits"),
    ("ringcentral", "RingCentral phone integration", {"enabled": False, "environment": "production", "connection_mode": "websocket", "client_id": "", "support_number": "", "queue_extension": "", "routing_mode": "rotating", "ticket_trigger": "answered", "default_team": "Service Desk", "default_category": "Phone Support", "default_priority": "Medium", "caller_matching": "phone_number", "unknown_caller": "create_ticket", "open_ticket_on_answer": True, "create_missed_call_ticket": True}, "Per-organization call routing and automatic ticket behavior"),
]


def seed_production(organization_name: str = "", admin_email: str = "", admin_password: str = "") -> None:
    """Initialize a new production database without evaluation/sample data.

    This routine is intentionally separate from :func:`seed`.  It creates the
    minimum operational catalog and exactly one local administrator.  It is
    idempotent for that completed state and refuses to adopt a database that
    already contains other users, which prevents demo credentials from being
    carried into a production installation accidentally.
    """
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        existing_users = db.scalars(select(User).order_by(User.id)).all()
        if existing_users:
            bootstrap_state = db.get(SystemState, "production_bootstrap")
            if (len(existing_users) == 1 and existing_users[0].role == Role.ADMIN
                    and existing_users[0].username == "admin"
                    and bootstrap_state
                    and (bootstrap_state.value or {}).get("completed") is True):
                return
            # Normal service startup and the installer's migration command do
            # not carry bootstrap credentials. A populated database in that
            # path is an upgrade, not a request to seed or adopt its users.
            # Explicit production configuration still supplies credentials
            # and retains the refusal below, preventing accidental promotion
            # of evaluation/demo data into a new production deployment.
            if not organization_name and not admin_email and not admin_password:
                return
            raise RuntimeError(
                "Production initialization refused: the database already contains "
                "users. Use a new database or complete an explicit migration; demo "
                "accounts will not be promoted into production."
            )

        organization_name = organization_name.strip()
        admin_email = admin_email.strip().lower()
        if not organization_name:
            raise ValueError("Organization name is required for production initialization.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", admin_email):
            raise ValueError("A valid administrator email address is required.")
        password_errors = validate_password(admin_password)
        if password_errors:
            raise ValueError("Initial administrator password: " + "; ".join(password_errors) + ".")

        organization = db.scalar(select(Organization).where(Organization.slug == "primary"))
        if organization is None:
            organization = Organization(
                name=organization_name, slug="primary", timezone="America/New_York"
            )
            db.add(organization)
            db.flush()
        else:
            organization.name = organization_name
        db.info["organization_id"] = organization.id

        team = db.scalar(select(Team).where(Team.name == "Service Desk"))
        if team is None:
            team = Team(
                name="Service Desk", key="service-desk", queue_name="General Support",
                is_default=True, skills=["General"], description="Default service desk team",
            )
            db.add(team)
            db.flush()

        role_definitions = {}
        for key, name in SYSTEM_ROLE_NAMES.items():
            definition = db.scalar(select(RoleDefinition).where(RoleDefinition.key == key))
            if definition is None:
                definition = RoleDefinition(
                    key=key, name=name, description=f"System {name} role",
                    permissions=SYSTEM_ROLE_PERMISSIONS[key], system=True,
                )
                db.add(definition)
                db.flush()
            role_definitions[key] = definition

        admin = User(
            username="admin", email=admin_email, display_name="System Administrator",
            role=Role.ADMIN, team_id=team.id, password_hash=hash_password(admin_password),
            must_change_password=False, auth_source="Local",
        )
        db.add(admin)
        db.flush()
        db.add(UserRoleAssignment(
            user_id=admin.id, role_definition_id=role_definitions["admin"].id,
            source="Production bootstrap",
        ))
        db.add(TeamMembership(
            team_id=team.id, user_id=admin.id, membership_role="owner", is_primary=True,
        ))

        for name, purpose, order in GROUP_TYPE_DEFAULTS:
            if db.scalar(select(GroupType).where(GroupType.name == name)) is None:
                db.add(GroupType(name=name, purpose=purpose, sort_order=order))
        for key in EVENT_KEYS:
            if db.scalar(select(EventCatalogItem).where(EventCatalogItem.key == key)) is None:
                db.add(EventCatalogItem(
                    key=key, name=key.replace(".", " ").replace("_", " ").title(),
                    category=key.split(".")[0],
                ))

        categories = ["General", "Access and Identity", "Applications", "Email and Collaboration", "Hardware", "Network and Connectivity", "Security", "Telephony", "Onboarding"]
        for index, name in enumerate(categories, 1):
            if db.scalar(select(ServiceCategory).where(
                    ServiceCategory.name == name, ServiceCategory.parent_id.is_(None))) is None:
                db.add(ServiceCategory(name=name, level="category", sort_order=index * 10))

        queue = db.scalar(select(SupportQueue).where(SupportQueue.name == "General Support"))
        if queue is None:
            queue = SupportQueue(
                name="General Support", key="general-support", team_id=team.id,
                description="Default intake and service desk work",
                assignment_strategy="round_robin",
            )
            db.add(queue)
            db.flush()
            db.add(QueueTeamEligibility(
                queue_id=queue.id, team_id=team.id,
                eligibility_priority=100, weight=100,
            ))

        existing_sections = set(db.scalars(select(ConfigItem.section)).all())
        db.add_all([
            ConfigItem(section=section, name=name, value=value, description=description)
            for section, name, value, description in PRODUCTION_CONFIG_DEFAULTS
            if section not in existing_sections
        ])
        if db.get(SystemState, "mailbox") is None:
            db.add(SystemState(key="mailbox", value={"status": "Not configured", "last_check": None, "last_processed": None}))
        if db.get(SystemState, "worker") is None:
            db.add(SystemState(key="worker", value={"status": "Ready", "last_heartbeat": None, "scheduled_jobs": "healthy"}))
        db.add(SystemState(
            key="production_bootstrap",
            value={"completed": True, "mode": "production-safe"},
        ))
        db.commit()

    print("Production database initialized with one administrator and no sample data.")


def seed(reset=False):
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    if db.scalar(select(User.id).limit(1)):
        print("Database already contains data; seed skipped.")
        return
    organization = db.scalar(select(Organization).where(Organization.slug == "primary"))
    if organization is None:
        organization = Organization(name="Primary Organization", slug="primary", timezone="America/New_York")
        db.add(organization)
        db.flush()
    db.info["organization_id"] = organization.id
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
    role_definitions = {}
    for key, name in SYSTEM_ROLE_NAMES.items():
        definition = RoleDefinition(key=key, name=name, description=f"System {name} role", permissions=SYSTEM_ROLE_PERMISSIONS[key], system=True)
        db.add(definition); role_definitions[key] = definition
    for name, purpose, order in GROUP_TYPE_DEFAULTS:
        db.add(GroupType(name=name, purpose=purpose, sort_order=order))
    db.add_all([EventCatalogItem(key=key, name=key.replace(".", " ").replace("_", " ").title(), category=key.split(".")[0]) for key in EVENT_KEYS])
    db.flush()
    for user in users:
        role_key = user.role.value if hasattr(user.role, "value") else str(user.role)
        db.add(UserRoleAssignment(user_id=user.id, role_definition_id=role_definitions[role_key].id, source="System role"))
        if user.team_id:
            db.add(TeamMembership(team_id=user.team_id, user_id=user.id, membership_role="member", is_primary=True))

    category_names = ["General", "Access and Identity", "Applications", "Email and Collaboration", "Hardware", "Medical Devices",
                      "Network and Connectivity", "Operating Systems", "Printers", "Security", "Telephony", "Onboarding"]
    categories = [ServiceCategory(name=name, level="category", sort_order=index * 10) for index, name in enumerate(category_names, 1)]
    db.add_all(categories)
    db.flush()
    hardware = next(item for item in categories if item.name == "Hardware")
    endpoint = ServiceCategory(name="Endpoint Devices", parent_id=hardware.id, level="subcategory", sort_order=10)
    db.add(endpoint); db.flush()
    db.add_all([ServiceCategory(name=name, parent_id=endpoint.id, level="item", sort_order=index * 10)
                for index, name in enumerate(["Laptop", "Desktop", "Monitor", "Docking Station"], 1)])
    queues = [
        SupportQueue(name="General Support", key="general-support", team_id=teams[0].id, description="Default intake and service desk work", assignment_strategy="round_robin"),
        SupportQueue(name="Devices", key="devices", team_id=teams[1].id, description="Endpoint hardware and device work", assignment_strategy="least_active"),
        SupportQueue(name="Access Requests", key="access-requests", team_id=teams[2].id, description="Identity and access work", assignment_strategy="round_robin"),
    ]
    db.add_all(queues); db.flush()
    db.add_all([QueueTeamEligibility(queue_id=queue.id, team_id=queue.team_id, eligibility_priority=100, weight=100) for queue in queues])
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
    db.add(Announcement(title="Attachment policy", body="Supporting files are stored securely and are available from Ticket Detail to authorized users.", severity="info"))
    db.add(AutomationFailure(failure_type="notification",summary="Sample notification delivery failure",safe_details={"channel":"email","ticket_number":"INC-000003"}))
    db.add(SystemState(key="mailbox",value={"status":"Not configured","last_check":None,"last_processed":None}))
    db.add(SystemState(key="worker",value={"status":"Ready","last_heartbeat":now().isoformat(),"scheduled_jobs":"healthy"}))
    incident_taxonomy = {
        "request_types":[{"key":"incident","name":"Incident"},{"key":"information","name":"Request for Information"},{"key":"service_request","name":"Service Request"}],
        "modes":[{"key":name.lower().replace(" ","_"),"name":name} for name in ["Email","Live Chat","Mobile Application","Phone Call","Web Form"]],
        "levels":[{"key":f"tier_{number}","name":f"Tier {number}"} for number in range(1,5)],
        "impacts":[{"key":name.lower(),"name":name} for name in ["Low","Medium","High"]],
        "urgencies":[{"key":name.lower(),"name":name} for name in ["Low","Medium","High"]],
        "priorities":[{"key":name.lower(),"name":name} for name in ["Critical","High","Medium","Normal","Low"]],
        "statuses":[
            {"key":"open","name":"Open","description":"Newly submitted work","color":"#397da1","lifecycle":"active","sla_runs":True,"order":10,"active":True},
            {"key":"in_progress","name":"In Progress","description":"Work is underway","color":"#176453","lifecycle":"active","sla_runs":True,"order":20,"active":True},
            {"key":"on_hold","name":"On Hold","description":"Temporarily paused","color":"#e4a934","lifecycle":"paused","sla_runs":False,"order":30,"active":True},
            {"key":"pending_verification","name":"Pending Verification","description":"Awaiting confirmation","color":"#7867a5","lifecycle":"paused","sla_runs":False,"order":40,"active":True},
            {"key":"staging","name":"Staging","description":"Fix is being prepared","color":"#6b7d8b","lifecycle":"active","sla_runs":True,"order":50,"active":True},
            {"key":"resolved","name":"Resolved","description":"Service restored","color":"#41906e","lifecycle":"resolved","sla_runs":False,"order":60,"active":True},
            {"key":"closed","name":"Closed","description":"Work completed","color":"#56615d","lifecycle":"closed","sla_runs":False,"order":70,"active":True},
            {"key":"canceled","name":"Canceled","description":"Request withdrawn","color":"#9a7569","lifecycle":"closed","sla_runs":False,"order":80,"active":True},
            {"key":"rejected","name":"Rejected","description":"Request was not accepted","color":"#bc382d","lifecycle":"closed","sla_runs":False,"order":90,"active":True},
        ]}
    incident_matrix = {"priorities":["Critical","High","Medium","Normal","Low"],"cells":{
        "High|High":"Critical","High|Medium":"High","High|Low":"Medium","Medium|High":"High","Medium|Medium":"Normal",
        "Medium|Low":"Low","Low|High":"Medium","Low|Medium":"Low","Low|Low":"Low"}}
    incident_slas = {"policies":[
        {"key":"critical","name":"Critical","priority":"Critical","response_minutes":15,"resolution_minutes":60,"calendar":"default_business_hours","pause_statuses":["On Hold","Pending Verification"],"active":True},
        {"key":"high","name":"High","priority":"High","response_minutes":30,"resolution_minutes":120,"calendar":"default_business_hours","pause_statuses":["On Hold","Pending Verification"],"active":True},
        {"key":"medium","name":"Medium","priority":"Medium","response_minutes":60,"resolution_minutes":240,"calendar":"default_business_hours","pause_statuses":["On Hold","Pending Verification"],"active":True},
        {"key":"normal","name":"Normal","priority":"Normal","response_minutes":120,"resolution_minutes":480,"calendar":"default_business_hours","pause_statuses":["On Hold","Pending Verification"],"active":True},
        {"key":"low","name":"Low","priority":"Low","response_minutes":240,"resolution_minutes":960,"calendar":"default_business_hours","pause_statuses":["On Hold","Pending Verification"],"active":True}]}
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
        ("help_desk","Help Desk Settings",{"help_desk_title":"Help Desk","tickets_per_page":50,"auto_reload_seconds":30,"autoclose_days":5,"reply_form_position":"bottom","conversation_order":"oldest_first","customer_portal":"required_login","session_minutes":480,"auto_assign":True,"allow_reopen":True,"require_email":True,"require_subject":True,"require_message":True,"time_tracking":True,"ticket_ratings":True,"attachments_enabled":True,"max_files_per_reply":10,"max_file_size_mb":25,"allowed_file_types":["png","jpg","jpeg","gif","pdf","docx","xlsx","csv","txt","zip"],"login_attempts":5,"lockout_minutes":15},"Ticket behavior, staff workflow, customer access, security, and attachment limits"),
        ("ringcentral","RingCentral phone integration",{"enabled":False,"environment":"production","connection_mode":"websocket","client_id":"","support_number":"","queue_extension":"","routing_mode":"rotating","ticket_trigger":"answered","default_team":"Service Desk","default_category":"Phone Support","default_priority":"Medium","caller_matching":"phone_number","unknown_caller":"create_ticket","open_ticket_on_answer":True,"create_missed_call_ticket":True},"Per-organization call routing and automatic ticket behavior"),
        ("incident_taxonomy","Incident classification values",incident_taxonomy,"Request types, modes, levels, impacts, urgencies, priorities, and lifecycle-aware statuses"),
        ("incident_priority_matrix","Incident impact and urgency matrix",incident_matrix,"Every impact and urgency combination maps to a configurable priority"),
        ("incident_sla","Incident SLA policies",incident_slas,"Priority-based response and resolution targets stored in minutes"),
    ]
    existing_sections = set(db.scalars(select(ConfigItem.section)).all())
    db.add_all([ConfigItem(section=s,name=n,value=v,description=d) for s,n,v,d in config_defaults if s not in existing_sections])
    incident_form = db.scalar(select(FormDefinition).where(FormDefinition.slug == "new-incident"))
    if incident_form is None:
        incident_form = FormDefinition(slug="new-incident", name="New Incident", description="Report an interruption or degraded service.",
                                   category="General", icon="incident", active=True, published=True, form_type="incident",
                                   portal_visible=True, default_for_type=True, lifecycle_state="published",
                                   requester_layout=["Classification","Requester and asset context","Categorization","Request details"],
                                   technician_layout=["Classification","Requester and asset context","Assignment","Categorization","Request details","Resolution"],
                                   fields=[
                                       {"id":"incident-classification","key":"","label":"Classification","type":"section","required":False,"help":"Describe how the incident entered the service desk.","options":[],"placeholder":"","width":"full","icon":"tag","max_length":None,"visibility":"visible","read_only":False,"show_when":None},
                                       {"id":"incident-request-details","key":"","label":"Request details","type":"section","required":False,"help":"Explain the interruption and its business effect.","options":[],"placeholder":"","width":"full","icon":"document","max_length":None,"visibility":"visible","read_only":False,"show_when":None},
                                       {"id":"incident-assignment","key":"","label":"Assignment and categorization","type":"section","required":False,"help":"Routing is calculated from these values.","options":[],"placeholder":"","width":"full","icon":"route","max_length":None,"visibility":"visible","read_only":False,"show_when":None},
                                   ])
        db.add(incident_form)
        db.flush()
    devices_queue = next(queue for queue in queues if queue.name == "Devices")
    db.add(RoutingRule(name="Route hardware incidents", description="Send hardware incidents to Endpoint Services", trigger="ticket.created",
                       priority_order=10, conditions={"logic":"AND","conditions":[{"field":"category","operator":"equals","value":"Hardware"}]},
                       actions={"queue_id":devices_queue.id,"team_id":teams[1].id,"assignment_strategy":"least_active"},
                       status="active", active=True, stop_processing=True))
    db.commit(); db.close()
    print(f"Seeded {len(users)} users, {len(employees)} employees, {len(assets)} assets, and 30 tickets.")
    print(f"Temporary password for all test accounts: {TEMP_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--reset", action="store_true")
    seed(parser.parse_args().reset)

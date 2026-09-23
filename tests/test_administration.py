def test_administration_resources_are_configurable(admin):
    users = admin.get("/api/admin/users").json()
    teams = admin.get("/api/bootstrap").json()["teams"]

    group = admin.post("/api/admin/groups", json={
        "name": "Escalation Managers", "group_type": "Security", "description": "Approvers",
        "source": "Local", "active": True, "member_ids": [users[0]["id"]], "owner_ids": [users[1]["id"]],
    })
    assert group.status_code == 201, group.text
    assert group.json()["member_count"] == 2

    parent = admin.post("/api/admin/categories", json={
        "name": "Hardware", "level": "category", "sort_order": 10, "active": True,
        "description": "Physical equipment", "configuration": {}, "parent_id": None,
    })
    assert parent.status_code == 201, parent.text
    child = admin.post("/api/admin/categories", json={
        "name": "Laptop", "level": "subcategory", "sort_order": 20, "active": True,
        "description": "Portable computer", "configuration": {}, "parent_id": parent.json()["id"],
    })
    assert child.status_code == 201, child.text
    assert child.json()["parent_id"] == parent.json()["id"]

    queue = admin.post("/api/admin/queues", json={
        "name": "Hardware Queue", "team_id": teams[0]["id"], "description": "Hardware requests",
        "assignment_strategy": "round_robin", "configuration": {}, "active": True,
    })
    assert queue.status_code == 201, queue.text
    assert queue.json()["assignment_strategy"] == "round_robin"

    rule = admin.post("/api/admin/routing-rules", json={
        "name": "Route hardware", "priority_order": 10, "active": True,
        "conditions": [{"field": "category", "value": "Hardware"}],
        "actions": {"queue_id": queue.json()["id"], "assignment_strategy": "round_robin"},
    })
    assert rule.status_code == 201, rule.text
    tested = admin.post("/api/admin/routing-rules/test", json={"category": "Hardware"})
    assert tested.status_code == 200, tested.text
    assert tested.json()["matched"] is True

    notice = admin.post("/api/admin/notification-rules", json={
        "name": "Ticket created email", "trigger": "ticket.created", "active": True,
        "conditions": [], "recipients": [{"type": "requester"}],
        "template": {"subject": "{{ticket.number}} created", "body": "We received your request."},
    })
    assert notice.status_code == 201, notice.text


def test_category_hierarchy_ordering_dependencies_and_archive_safety(admin):
    parent = admin.post("/api/admin/categories", json={
        "name": "Configuration Parent", "level": "category", "sort_order": 40,
        "description": "Parent", "configuration": {}, "active": True,
    })
    assert parent.status_code == 201, parent.text
    invalid = admin.post("/api/admin/categories", json={
        "name": "Invalid Item", "level": "item", "parent_id": parent.json()["id"],
        "description": "Wrong parent level", "configuration": {}, "active": True,
    })
    assert invalid.status_code == 422
    child = admin.post("/api/admin/categories", json={
        "name": "Configuration Child", "level": "subcategory", "parent_id": parent.json()["id"],
        "sort_order": 50, "description": "Child", "configuration": {}, "active": True,
    })
    assert child.status_code == 201, child.text

    dependencies = admin.get(f"/api/admin/categories/{parent.json()['id']}/dependencies")
    assert dependencies.status_code == 200
    assert dependencies.json()["active_children"] == 1
    blocked = admin.delete(f"/api/admin/categories/{parent.json()['id']}")
    assert blocked.status_code == 409

    reordered = admin.post("/api/admin/categories/reorder", json=[
        {"id": parent.json()["id"], "sort_order": 200},
        {"id": child.json()["id"], "sort_order": 210},
    ])
    assert reordered.status_code == 200, reordered.text
    rows = admin.get("/api/admin/categories").json()
    assert next(row for row in rows if row["id"] == parent.json()["id"])["sort_order"] == 200

    assert admin.delete(f"/api/admin/categories/{child.json()['id']}").status_code == 200
    archived_parent = admin.delete(f"/api/admin/categories/{parent.json()['id']}")
    assert archived_parent.status_code == 200, archived_parent.text
    restored = admin.post(f"/api/admin/categories/{parent.json()['id']}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["active"] is True


def test_provider_neutral_integration_configuration(admin):
    created = admin.post("/api/admin/integrations", json={
        "name": "Primary phone system", "kind": "telephony", "provider": "RingCentral",
        "enabled": True, "configuration": {"identifier": "sandbox"},
    })
    assert created.status_code == 201, created.text
    connection = created.json()
    assert connection["status"] == "Disconnected"

    tested = admin.post(f"/api/admin/integrations/{connection['id']}/test")
    assert tested.status_code == 200, tested.text
    assert tested.json()["status"] == "Authorization required"
    assert tested.json()["last_error"]

    logs = admin.get(f"/api/admin/integrations/{connection['id']}/logs")
    assert logs.status_code == 200, logs.text
    assert logs.json()[0]["event"] == "connection.configuration_test"


def test_guided_provider_connection_reports_one_time_registration(admin, monkeypatch):
    from itsm.config import settings
    monkeypatch.setattr(settings, "microsoft_client_id", "")
    response = admin.post("/api/admin/integrations/connect/start", json={
        "name": "Company Microsoft", "kind": "directory", "provider": "Microsoft Entra ID",
        "configuration": {"sync_scope": "all_users"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["ready"] is False
    assert "registered once" in response.json()["message"]


def test_guided_microsoft_connection_builds_admin_consent_url(admin, monkeypatch):
    from itsm.config import settings
    monkeypatch.setattr(settings, "microsoft_client_id", "northstar-client-id")
    monkeypatch.setattr(settings, "microsoft_client_secret", "northstar-client-secret")
    response = admin.post("/api/admin/integrations/connect/start", json={
        "name": "Company Microsoft Mail", "kind": "email", "provider": "Microsoft 365",
        "configuration": {"mailbox": "support@example.test"},
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ready"] is True
    assert "login.microsoftonline.com/organizations/v2.0/adminconsent" in payload["authorization_url"]
    assert "northstar-client-id" in payload["authorization_url"]
    assert "scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" in payload["authorization_url"]


def test_guided_connection_uses_localhost_for_loopback_redirect(admin, monkeypatch):
    from itsm.config import settings
    monkeypatch.setattr(settings, "public_url", "http://127.0.0.1:8011")
    readiness = admin.get("/api/admin/integrations/connect/readiness")
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["microsoft"]["callback_url"] == (
        "http://localhost:8011/api/admin/integrations/oauth/callback/microsoft"
    )


def test_server_owner_can_save_provider_application_registration(admin, monkeypatch):
    from itsm.config import settings
    monkeypatch.setattr(settings, "ringcentral_client_id", "")
    monkeypatch.setattr(settings, "ringcentral_client_secret", "")
    saved=admin.put("/api/admin/integrations/connect/registration/ringcentral",json={
        "client_id":"ringcentral-application-id","client_secret":"ringcentral-secret-value","environment":"sandbox"
    })
    assert saved.status_code==200,saved.text
    assert saved.json()["ready"] is True
    readiness=admin.get("/api/admin/integrations/connect/readiness").json()
    assert readiness["ringcentral"]["ready"] is True
    assert readiness["ringcentral"]["environment"]=="sandbox"


def test_administration_catalogs_and_effective_permissions(admin):
    roles = admin.get("/api/admin/roles")
    assert roles.status_code == 200, roles.text
    assert {item["key"] for item in roles.json()} >= {"end_user", "technician", "team_lead", "manager", "admin", "auditor"}

    group_types = admin.get("/api/admin/group-types")
    assert group_types.status_code == 200, group_types.text
    assert {item["name"] for item in group_types.json()} >= {"Support", "Department", "Security", "Approval", "Custom"}

    events = admin.get("/api/admin/event-catalog")
    assert events.status_code == 200, events.text
    assert len(events.json()) >= 30
    assert "approval.requested" in {item["key"] for item in events.json()}

    current = admin.get("/api/auth/me").json()["user"]
    effective = admin.get(f"/api/admin/users/{current['id']}/effective-permissions")
    assert effective.status_code == 200, effective.text
    assert "administer" in effective.json()["permissions"]["administration"]


def test_user_lifecycle_multi_team_queue_and_final_admin_guards(admin):
    teams = admin.get("/api/admin/teams").json()
    roles = admin.get("/api/admin/roles").json()
    created = admin.post("/api/admin/users", json={
        "username": "admin_workflow_user", "email": "admin.workflow@example.test",
        "display_name": "Administration Workflow User", "temporary_password": "StrongPass!2026",
        "role": "technician", "team_id": teams[0]["id"], "team_ids": [teams[0]["id"], teams[1]["id"]],
        "role_definition_ids": [next(item["id"] for item in roles if item["key"] == "technician")],
        "employee_number": "ADM-TEST-01", "location_name": "United States", "auth_source": "Local",
    })
    assert created.status_code == 201, created.text
    account = created.json()
    assert set(account["team_ids"]) == {teams[0]["id"], teams[1]["id"]}

    queue = admin.post("/api/admin/queues", json={
        "name": "Multi Team Acceptance Queue", "key": "multi-team-acceptance", "team_id": teams[0]["id"],
        "description": "Verifies flexible queue eligibility", "assignment_strategy": "least_active", "configuration": {"region": "US"},
        "eligible_teams": [
            {"team_id": teams[0]["id"], "eligibility_priority": 10, "weight": 70, "active": True},
            {"team_id": teams[1]["id"], "eligibility_priority": 20, "weight": 30, "active": True},
        ], "active": True,
    })
    assert queue.status_code == 201, queue.text
    assert len(queue.json()["eligible_teams"]) == 2
    simulation = admin.post(f"/api/admin/queues/{queue.json()['id']}/simulate")
    assert simulation.status_code == 200, simulation.text
    assert len(simulation.json()["eligible_teams"]) == 2

    updated = admin.patch(f"/api/admin/users/{account['id']}", json={"job_title": "Support Engineer", "version": account["version"]})
    assert updated.status_code == 200, updated.text
    stale = admin.patch(f"/api/admin/users/{account['id']}", json={"job_title": "Stale Update", "version": account["version"]})
    assert stale.status_code == 409
    deactivated = admin.delete(f"/api/admin/users/{account['id']}")
    assert deactivated.status_code == 200, deactivated.text

    current = admin.get("/api/auth/me").json()["user"]
    assert admin.delete(f"/api/admin/users/{current['id']}").status_code == 409


def test_notification_html_safety_and_admin_authorization(admin, client):
    unsafe = admin.post("/api/admin/notification-rules", json={
        "name": "Unsafe template", "trigger": "ticket.created", "classification": "customer",
        "conditions": [], "recipients": [{"type": "requester", "channel": "to"}],
        "template": {"subject": "Test", "html_body": "<script>alert(1)</script>"}, "status": "draft", "active": False,
    })
    assert unsafe.status_code == 422

    seeded = admin.post("/api/admin/notification-rules/seed-defaults")
    assert seeded.status_code == 200, seeded.text
    rules = admin.get("/api/admin/notification-rules").json()
    assert any(item["template"].get("subject") for item in rules)

    login = client.post("/api/auth/login", json={"username": "user1", "password": "ChangeMe!2026"})
    assert login.status_code == 200, login.text
    client.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    forbidden = client.get("/api/admin/users")
    assert forbidden.status_code == 403


def test_notification_preview_test_delivery_and_active_template_engine(admin):
    rule=admin.post("/api/admin/notification-rules",json={
        "name":"Configured ticket receipt","trigger":"ticket.created","classification":"customer","conditions":[],
        "recipients":[{"type":"requester","channel":"to"}],"template":{"subject":"[{{ticket.number}}] We received {{ticket.subject}}","text_body":"Hello {{requester.first_name}}, your request is recorded."},
        "locale":"en","status":"active","rate_limit":{"dedupe_minutes":5},"suppress_actor":True,"active":True})
    assert rule.status_code==201,rule.text
    preview=admin.post("/api/admin/notification-rules/preview",json={"trigger":"ticket.created","template":rule.json()["template"],"context":{"ticket":{"number":"INC-009999","subject":"VPN help"},"requester":{"first_name":"Frank"}}})
    assert preview.status_code==200,preview.text
    assert preview.json()["subject"]=="[INC-009999] We received VPN help"
    assert "Hello Frank" in preview.json()["text_body"]
    tested=admin.post(f"/api/admin/notification-rules/{rule.json()['id']}/test",json={"delivery":"in_app"})
    assert tested.status_code==200 and tested.json()["delivery"]=="in_app"

    created=admin.post("/api/tickets",json={"request_type":"Other request","subject":"Configured notification engine","description":"Confirm the active administration template controls delivery."})
    assert created.status_code==201,created.text
    notices=admin.get("/api/notifications").json()
    receipt=next(item for item in notices if item["event"]=="ticket.created" and item["ticket_id"]==created.json()["ticket"]["id"])
    assert "We received Configured notification engine" in receipt["title"]


def test_global_notification_switch_and_audit_recipient_details(admin):
    settings=admin.get("/api/admin/notification-settings").json()
    assert settings["enabled"] is True
    assert settings["email_enabled"] is True
    created=admin.post("/api/tickets",json={
        "request_type":"Other request","subject":"Audit recipient detail","description":"Verify automatic recipients and the master notification switch."
    })
    assert created.status_code==201,created.text
    ticket_id=created.json()["ticket"]["id"]
    audit_rows=admin.get("/api/audit?limit=100").json()
    receipt=next(row for row in audit_rows if row["action"]=="notification.created" and row.get("details",{}).get("ticket",{}).get("id")==ticket_id)
    assert receipt["details"]["recipient"]["email"]
    assert receipt["new"]["subject"]

    before=len(admin.get("/api/notifications").json())
    disabled=admin.patch("/api/admin/notification-settings",json={"enabled":False})
    assert disabled.status_code==200 and disabled.json()["enabled"] is False
    suppressed_ticket=admin.post("/api/tickets",json={
        "request_type":"Other request","subject":"Suppressed test notification","description":"No notification should be delivered."
    })
    assert suppressed_ticket.status_code==201,suppressed_ticket.text
    assert len(admin.get("/api/notifications").json())==before
    audit_rows=admin.get("/api/audit?limit=100").json()
    suppressed=next(row for row in audit_rows if row["action"]=="notification.suppressed")
    assert suppressed["new"]["recipient_email"]
    assert suppressed["new"]["reason"]=="Global notification delivery is disabled"

    enabled=admin.patch("/api/admin/notification-settings",json={"enabled":True})
    assert enabled.status_code==200 and enabled.json()["enabled"] is True

    email_disabled=admin.patch("/api/admin/notification-settings",json={"email_enabled":False})
    assert email_disabled.status_code==200
    assert email_disabled.json()["enabled"] is True
    assert email_disabled.json()["email_enabled"] is False
    in_app_only=admin.post("/api/tickets",json={
        "request_type":"Other request","subject":"In-app only test","description":"Email must remain disabled."
    })
    assert in_app_only.status_code==201,in_app_only.text
    in_app_ticket_id=in_app_only.json()["ticket"]["id"]
    notices=admin.get("/api/notifications").json()
    assert any(row["ticket_id"]==in_app_ticket_id and row["delivery_status"]=="in_app" for row in notices)
    email_enabled=admin.patch("/api/admin/notification-settings",json={"email_enabled":True})
    assert email_enabled.status_code==200 and email_enabled.json()["email_enabled"] is True


def test_user_password_controls_and_routing_version_rollback(admin):
    created = admin.post("/api/admin/users", json={
        "username": "password_control_user", "email": "password.control@example.test",
        "display_name": "Password Control User", "temporary_password": "InitialPass!2026",
        "role": "end_user", "auth_source": "Local",
    })
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    reset = admin.post(f"/api/admin/users/{user_id}/reset-password", json={"temporary_password": "ResetPass!2026"})
    assert reset.status_code == 200, reset.text
    assert reset.json()["must_change_password"] is True
    forced = admin.post(f"/api/admin/users/{user_id}/force-password-change")
    assert forced.status_code == 200, forced.text

    rule = admin.post("/api/admin/routing-rules", json={
        "name": "Rollback acceptance rule", "description": "Version one", "trigger": "ticket.created",
        "priority_order": 500, "conditions": {"logic": "AND", "conditions": [{"field": "location_name", "operator": "equals", "value": "US"}]},
        "actions": {}, "status": "draft", "active": False,
    })
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["id"]
    updated_payload = {**rule.json(), "description": "Version two"}
    updated = admin.patch(f"/api/admin/routing-rules/{rule_id}", json=updated_payload)
    assert updated.status_code == 200, updated.text
    versions = admin.get(f"/api/admin/routing-rules/{rule_id}/versions")
    assert versions.status_code == 200, versions.text
    version_one = next(item for item in versions.json() if item["version"] == 1)
    rolled_back = admin.post(f"/api/admin/routing-rules/{rule_id}/rollback/{version_one['id']}")
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["description"] == "Version one"

    draft_test = admin.post("/api/admin/routing-rules/evaluate", json={
        "rule": rule.json(), "sample": {"location_name": "US"},
    })
    assert draft_test.status_code == 200, draft_test.text
    assert draft_test.json()["matched"] is True


def test_routing_validation_conflicts_effective_windows_and_loop_protection(admin):
    teams=admin.get("/api/admin/teams").json();queues=admin.get("/api/admin/queues").json()
    base={
        "description":"Conflict acceptance", "trigger":"ticket.created", "priority_order":700,
        "conditions":{"logic":"AND","conditions":[{"field":"category","operator":"equals","value":"Security"}]},
        "actions":{"queue_id":queues[0]["id"],"team_id":teams[0]["id"]},"status":"active","active":True,
        "stop_processing":True,"overwrite_existing":False,"reevaluate_fields":[],
    }
    first=admin.post("/api/admin/routing-rules",json={**base,"name":"Security conflict one"})
    assert first.status_code==201,first.text
    second=admin.post("/api/admin/routing-rules",json={**base,"name":"Security conflict two","priority_order":710})
    assert second.status_code==201,second.text
    conflicts=admin.get("/api/admin/routing-rules/conflicts")
    assert conflicts.status_code==200
    assert any(item["first_rule_id"]==first.json()["id"] for item in conflicts.json()["conflicts"])

    invalid_field=admin.post("/api/admin/routing-rules",json={**base,"name":"Invalid field rule",
        "conditions":{"logic":"AND","conditions":[{"field":"password","operator":"equals","value":"x"}]}})
    assert invalid_field.status_code==422
    loop=admin.post("/api/admin/routing-rules",json={**base,"name":"Looping rule","stop_processing":False,
        "actions":{"team_id":teams[0]["id"]},"reevaluate_fields":["team"]})
    assert loop.status_code==422
    expired=admin.post("/api/admin/routing-rules",json={**base,"name":"Future rule","conditions":{"logic":"AND","conditions":[{"field":"category","operator":"equals","value":"Future"}]},
        "effective_from":"2099-01-01T00:00:00Z"})
    assert expired.status_code==201,expired.text
    simulation=admin.post("/api/admin/routing-rules/test",json={"category":"Future"})
    future_trace=next(item for item in simulation.json()["trace"] if item["rule_id"]==expired.json()["id"])
    assert future_trace["matched"] is False
    assert "effective date" in future_trace["conditions"][0]


def test_custom_administrator_role_is_enforced_by_api_and_exposed_to_ui(admin):
    role = admin.post("/api/admin/roles", json={
        "key": "delegated_configuration_admin", "name": "Delegated Configuration Administrator",
        "description": "May administer configuration without changing the operational base role.",
        "permissions": {"administration": ["administer"]}, "active": True,
    })
    assert role.status_code == 201, role.text
    account = admin.post("/api/admin/users", json={
        "username": "delegated_admin", "email": "delegated.admin@example.test",
        "display_name": "Delegated Administrator", "temporary_password": "DelegatePass!2026",
        "role": "technician", "role_definition_ids": [role.json()["id"]],
    })
    assert account.status_code == 201, account.text

    login = admin.post("/api/auth/login", json={"username": "delegated_admin", "password": "DelegatePass!2026"})
    assert login.status_code == 200, login.text
    admin.headers.update({"X-CSRF-Token": login.json()["csrf_token"]})
    assert login.json()["user"]["role"] == "technician"
    assert login.json()["user"]["can_administrate"] is True
    assert admin.get("/api/admin/users").status_code == 200

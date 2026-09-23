def test_automation_center_is_safe_by_default_and_persists_independent_policies(admin):
    initial = admin.get("/api/admin/automation-center")
    assert initial.status_code == 200, initial.text
    assert initial.json()["all_disabled"] is True
    assert initial.json()["policies"]["password_expiry"]["enabled"] is False

    updated = admin.patch("/api/admin/automation-center", json={"policies": {
        "duplicate_detection": {"enabled": True, "lookback_hours": 48},
        "password_expiry": {"enabled": False, "warning_days": 15},
    }})
    assert updated.status_code == 200, updated.text
    assert updated.json()["policies"]["duplicate_detection"]["enabled"] is True
    assert updated.json()["policies"]["duplicate_detection"]["lookback_hours"] == 48
    assert updated.json()["policies"]["password_expiry"]["enabled"] is False

    staged = admin.post("/api/admin/automation-center/password_expiry/test")
    assert staged.status_code == 200, staged.text
    assert staged.json()["ready"] is False
    assert "No production ticket" not in staged.json()["message"]

    duplicate = admin.post("/api/admin/automation-center/duplicate_detection/test")
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["ready"] is True
    assert "No production ticket" in duplicate.json()["message"]


def test_administrator_can_publish_and_unpublish_announcements(admin):
    created = admin.post("/api/admin/announcements", json={
        "title": "Planned maintenance", "body": "The service desk will be unavailable at 8 PM.",
        "severity": "warning", "active": True,
    })
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["active"] is True

    listed = admin.get("/api/admin/announcements")
    assert listed.status_code == 200, listed.text
    assert any(x["id"] == item["id"] for x in listed.json())

    hidden = admin.patch(f"/api/admin/announcements/{item['id']}", json={"active": False})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["active"] is False

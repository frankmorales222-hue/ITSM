from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import delete, select

from itsm import microsoft_mail, worker
from itsm.database import SessionLocal
from itsm.models import AutomationFailure, EmailMessage as StoredEmailMessage, IntegrationConnection, IntegrationLog, Organization, SystemState


class _Response:
    def __init__(self, payload=None):
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_graph_notification_creates_traceable_draft_then_sends(monkeypatch):
    connection = IntegrationConnection(
        name="Mail threading", kind="email", provider="Microsoft 365",
        enabled=True, status="Connected", configuration={"mailbox":"helpdesk@example.test"},
    )
    calls = []

    monkeypatch.setattr(microsoft_mail, "access_token", lambda _db, _connection: "token")

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/messages"):
            return _Response({"id":"graph-draft-1", "internetMessageId":"<provider-id@example.test>"})
        assert url.endswith("/messages/graph-draft-1/send")
        return _Response()

    monkeypatch.setattr(microsoft_mail.httpx, "post", post)
    result = microsoft_mail.send_notification(
        None, connection, "requester@example.test", "[INC-000001] Update", "A response was added."
    )

    assert result == "<provider-id@example.test>"
    assert len(calls) == 2
    assert calls[0][1]["json"]["subject"] == "[INC-000001] Update"
    assert calls[0][1]["json"]["toRecipients"][0]["emailAddress"]["address"] == "requester@example.test"


def test_mail_poll_includes_messages_already_read_in_outlook(monkeypatch):
    connection = IntegrationConnection(
        name="Mail threading", kind="email", provider="Microsoft 365",
        enabled=True, status="Connected", configuration={"mailbox":"helpdesk@example.test"},
    )
    captured = {}
    monkeypatch.setattr(microsoft_mail, "access_token", lambda _db, _connection: "token")
    def get(_url, **kwargs):
        captured.update(kwargs["params"])
        return _Response({"value":[{"id":"new"},{"id":"old"}]})
    monkeypatch.setattr(microsoft_mail.httpx, "get", get)
    rows = microsoft_mail.unread_messages(None, connection)
    assert "$filter" not in captured
    assert captured["$orderby"] == "receivedDateTime desc"
    assert [row["id"] for row in rows] == ["old", "new"]


def test_inbound_outlook_cid_is_removed_and_image_is_saved(monkeypatch):
    """Inline Outlook images stay available as ticket attachments, not CID text."""
    message = EmailMessage()
    message.set_content("Please review the screenshot.\n[cid:image001.png@01D3FA]")
    message.add_attachment(b"png-data", maintype="image", subtype="png", filename="image001.png")

    assert "[cid:" not in worker.text_body(message)

    saved = []
    db = SimpleNamespace(add=saved.append)
    test_root = Path("data") / "test_inbound_attachment"
    monkeypatch.setattr(worker.settings, "data_directory", str(test_root))
    try:
        count = worker._save_inbound_attachments(
            db, message, SimpleNamespace(id=42), SimpleNamespace(id=7)
        )
        assert count == 1
        assert saved[0].ticket_id == 42
        assert saved[0].original_name == "image001.png"
        assert (test_root / "attachments" / saved[0].storage_name).read_bytes() == b"png-data"
    finally:
        for path in (test_root / "attachments").glob("*") if (test_root / "attachments").exists() else []:
            path.unlink()
        if (test_root / "attachments").exists():
            (test_root / "attachments").rmdir()
        if test_root.exists():
            test_root.rmdir()


def test_mailbox_message_is_atomic_retried_and_then_skipped(monkeypatch):
    graph_id = "graph-atomic-retry-test"
    internet_id = "<atomic-retry@example.test>"
    calls = {"mime": 0, "process": 0}
    with SessionLocal() as db:
        organization_id = db.scalar(select(Organization.id).order_by(Organization.id))
        db.info["organization_id"] = organization_id
        connection = IntegrationConnection(
            organization_id=organization_id, name="Atomic mailbox test", kind="email",
            provider="Microsoft 365", enabled=True, status="Connected",
            configuration={"mailbox":"helpdesk@example.test"},
        )
        db.add(connection); db.commit()
        monkeypatch.setattr(worker, "connected_mailbox", lambda _db: connection)
        monkeypatch.setattr(worker, "unread_messages", lambda *_args: [
            {"id": graph_id, "internetMessageId": internet_id}
        ])
        def mime(*_args):
            calls["mime"] += 1
            return b"raw"
        monkeypatch.setattr(worker, "message_mime", mime)
        monkeypatch.setattr(worker, "mark_read", lambda *_args: None)
        def process(target_db, _raw):
            calls["process"] += 1
            target_db.add(StoredEmailMessage(
                organization_id=organization_id, message_id=internet_id,
                sender="requester@example.test", subject="Atomic test",
                attachment_metadata=[], processing_status="created",
            ))
            target_db.flush()
            if calls["process"] == 1:
                raise RuntimeError("fail after partial persistence")
            return "created"
        monkeypatch.setattr(worker, "process_message", process)

        assert worker.microsoft_mailbox_job(db) == 0
        assert db.scalar(select(StoredEmailMessage).where(
            StoredEmailMessage.message_id == internet_id)) is None
        assert worker.microsoft_mailbox_job(db) == 1
        assert db.scalar(select(StoredEmailMessage).where(
            StoredEmailMessage.message_id == internet_id)) is not None
        assert worker.microsoft_mailbox_job(db) == 0
        assert calls == {"mime": 2, "process": 2}

        db.execute(delete(StoredEmailMessage).where(StoredEmailMessage.message_id == internet_id))
        db.execute(delete(SystemState).where(SystemState.key == worker._mail_retry_key(graph_id)))
        db.execute(delete(AutomationFailure).where(
            AutomationFailure.failure_type == "microsoft_mailbox",
            AutomationFailure.related_id == str(connection.id),
        ))
        db.execute(delete(IntegrationLog).where(IntegrationLog.connection_id == connection.id))
        db.delete(connection); db.commit()


def test_mailbox_stops_after_three_failures_for_manual_review(monkeypatch):
    graph_id = "graph-manual-review-test"
    mime_calls = []
    with SessionLocal() as db:
        organization_id = db.scalar(select(Organization.id).order_by(Organization.id))
        db.info["organization_id"] = organization_id
        connection = IntegrationConnection(
            organization_id=organization_id, name="Manual review mailbox test", kind="email",
            provider="Microsoft 365", enabled=True, status="Connected",
            configuration={"mailbox":"helpdesk@example.test"},
        )
        db.add(connection); db.commit()
        monkeypatch.setattr(worker, "connected_mailbox", lambda _db: connection)
        monkeypatch.setattr(worker, "unread_messages", lambda *_args: [
            {"id": graph_id, "internetMessageId": "<manual-review@example.test>"}
        ])
        monkeypatch.setattr(worker, "message_mime", lambda *_args: mime_calls.append(graph_id) or b"raw")
        monkeypatch.setattr(worker, "process_message", lambda *_args: (_ for _ in ()).throw(RuntimeError("broken")))

        for _ in range(4):
            assert worker.microsoft_mailbox_job(db) == 0
        state = db.get(SystemState, worker._mail_retry_key(graph_id))
        assert state.value["attempts"] == 3
        assert state.value["status"] == "manual_review"
        assert len(mime_calls) == 3

        db.execute(delete(SystemState).where(SystemState.key == worker._mail_retry_key(graph_id)))
        db.execute(delete(AutomationFailure).where(
            AutomationFailure.failure_type == "microsoft_mailbox",
            AutomationFailure.related_id == str(connection.id),
        ))
        db.execute(delete(IntegrationLog).where(IntegrationLog.connection_id == connection.id))
        db.delete(connection); db.commit()

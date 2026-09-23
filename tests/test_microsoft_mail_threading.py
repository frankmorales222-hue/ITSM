from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

from itsm import microsoft_mail, worker
from itsm.models import IntegrationConnection


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

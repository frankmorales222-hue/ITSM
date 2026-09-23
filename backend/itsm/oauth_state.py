"""Signed, short-lived OAuth state shared by provider setup and user sign-in."""
import base64
import hashlib
import hmac
import json
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from .config import settings


def create_oauth_state(payload: dict) -> tuple[str, dict]:
    signed_payload = {**payload, "expires": int(time.time()) + 600, "nonce": uuid.uuid4().hex}
    raw = base64.urlsafe_b64encode(
        json.dumps(signed_payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}", signed_payload


def read_oauth_state(value: str) -> dict:
    try:
        raw, signature = value.rsplit(".", 1)
        expected = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        payload = json.loads(decoded)
        if int(payload["expires"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "This authorization request is invalid or has expired. Please start again.") from exc


def provider_callback_url(provider: str = "microsoft") -> str:
    slug = "microsoft" if provider.lower().startswith("microsoft") else "ringcentral"
    public_url = settings.public_url.rstrip("/")
    parsed = urlsplit(public_url)
    if parsed.hostname in {"127.0.0.1", "::1"}:
        host = f"localhost:{parsed.port}" if parsed.port else "localhost"
        public_url = urlunsplit((parsed.scheme, host, parsed.path.rstrip("/"), "", ""))
    return f"{public_url}/api/admin/integrations/oauth/callback/{slug}"

import json
import time
import uuid
from email.utils import formatdate
from urllib.parse import parse_qs, urlparse

import jwt
import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from itsm.config import settings
from itsm.database import SessionLocal
from itsm.microsoft_sso import MicrosoftSignInError, _link_user, test_microsoft_application as verify_microsoft_application
from itsm.models import Employee, IntegrationConnection, IntegrationLog, Role, Session as LoginSession, User


class ProviderResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_live_identity_check_rejects_secret_id_with_clear_message(monkeypatch):
    tenant_id = str(uuid.uuid4())
    monkeypatch.setattr(settings, "microsoft_client_id", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "microsoft_client_secret", "secret-id-instead-of-value")
    request = httpx.Request("POST", f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token")

    def rejected_token(*_args, **_kwargs):
        return httpx.Response(
            401,
            request=request,
            json={
                "error": "invalid_client",
                "error_description": "AADSTS7000215: Invalid client secret provided.",
            },
        )

    monkeypatch.setattr("itsm.microsoft_sso.httpx.post", rejected_token)
    connection = IntegrationConnection(
        provider="Microsoft Entra ID",
        configuration={"tenant_id": tenant_id},
    )
    with SessionLocal() as db:
        try:
            verify_microsoft_application(db, connection)
            raise AssertionError("invalid Microsoft credential was accepted")
        except MicrosoftSignInError as exc:
            assert exc.code == "credentials_invalid"
            assert "secret Value" in str(exc)
            assert "Secret ID" in str(exc)


def test_live_identity_check_accepts_valid_application_token(monkeypatch):
    tenant_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    monkeypatch.setattr(settings, "microsoft_client_id", client_id)
    monkeypatch.setattr(settings, "microsoft_client_secret", "valid-secret-value")

    def accepted_token(url, **kwargs):
        assert tenant_id in url
        assert kwargs["data"]["scope"] == "https://graph.microsoft.com/.default"
        return ProviderResponse({"access_token": "validated-application-token"})

    monkeypatch.setattr("itsm.microsoft_sso.httpx.post", accepted_token)
    connection = IntegrationConnection(
        provider="Microsoft Entra ID",
        configuration={"tenant_id": tenant_id},
    )
    with SessionLocal() as db:
        result = verify_microsoft_application(db, connection)
    assert result == {"tenant_id": tenant_id, "client_id": client_id}


def test_sign_in_callback_reports_invalid_secret_value(client, monkeypatch):
    tenant_id = str(uuid.uuid4())
    connection_name = f"Rejected credential {tenant_id[:8]}"
    monkeypatch.setattr(settings, "microsoft_client_id", str(uuid.uuid4()))
    monkeypatch.setattr(settings, "microsoft_client_secret", "secret-id-instead-of-value")
    with SessionLocal() as db:
        administrator = db.scalar(select(User).where(User.username == "admin"))
        db.info["organization_id"] = administrator.organization_id
        db.add(IntegrationConnection(
            organization_id=administrator.organization_id,
            kind="directory",
            name=connection_name,
            provider="Microsoft Entra ID",
            enabled=True,
            status="Connected",
            configuration={"tenant_id": tenant_id},
        ))
        db.commit()

    start = client.get("/api/auth/microsoft/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    request = httpx.Request("POST", "https://login.microsoftonline.com/organizations/oauth2/v2.0/token")

    def rejected_token(*_args, **_kwargs):
        return httpx.Response(
            401,
            request=request,
            json={"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret provided."},
        )

    monkeypatch.setattr("itsm.microsoft_sso.httpx.post", rejected_token)
    callback = client.get(
        "/api/admin/integrations/oauth/callback/microsoft",
        params={"state": state, "code": "authorization-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert "sso=failed" in callback.headers["location"]
    assert "sso_error=credentials_invalid" in callback.headers["location"]

    with SessionLocal() as db:
        saved = db.scalar(select(IntegrationConnection).where(IntegrationConnection.name == connection_name))
        failure = db.scalar(select(IntegrationLog).where(
            IntegrationLog.connection_id == saved.id,
            IntegrationLog.event == "login.microsoft_failed",
        ))
        assert failure.details["code"] == "credentials_invalid"
        db.query(IntegrationLog).filter(IntegrationLog.connection_id == saved.id).delete()
        db.delete(saved)
        db.commit()


def test_first_microsoft_login_creates_end_user_without_asset_inventory():
    tenant_id = str(uuid.uuid4())
    object_id = str(uuid.uuid4())
    email = f"new-sso-{uuid.uuid4().hex[:10]}@medreceivables.com"
    with SessionLocal() as db:
        administrator = db.scalar(select(User).where(User.username == "admin"))
        db.info["organization_id"] = administrator.organization_id
        connection = IntegrationConnection(
            organization_id=administrator.organization_id,
            kind="directory",
            name=f"JIT {tenant_id[:8]}",
            provider="Microsoft Entra ID",
            enabled=True,
            status="Connected",
            configuration={"tenant_id": tenant_id},
        )
        db.add(connection)
        db.flush()

        user = _link_user(db, connection, {
            "tid": tenant_id,
            "oid": object_id,
            "sub": "new-user-subject",
            "email": email,
            "name": "New Microsoft User",
        })

        assert user.email == email
        assert user.display_name == "New Microsoft User"
        assert user.role == Role.END_USER
        assert user.active is True
        assert user.auth_source == "Microsoft Entra ID"
        assert user.entra_tenant_id == tenant_id
        assert user.entra_object_id == object_id
        assert db.scalar(select(Employee).where(Employee.user_id == user.id)) is None
        db.rollback()


def test_microsoft_sign_in_links_approved_asset_user(client, monkeypatch):
    tenant_id = str(uuid.uuid4())
    object_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    key_id = "northstar-test-key"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    # Microsoft signing-key metadata is not authoritative for the token issuer.
    # The OpenID metadata issuer and the signed token claims are authoritative.
    public_jwk.update({"kid": key_id, "use": "sig", "alg": "RS256",
                       "issuer": "https://login.microsoftonline.com/common/v2.0"})
    monkeypatch.setattr(settings, "microsoft_client_id", client_id)
    monkeypatch.setattr(settings, "microsoft_client_secret", "test-secret")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "user1"))
        original = (user.auth_source, user.entra_tenant_id, user.entra_object_id, user.entra_subject)
        db.info["organization_id"] = user.organization_id
        connection = IntegrationConnection(
            kind="directory", name=f"SSO test {tenant_id[:8]}", provider="Microsoft Entra ID",
            enabled=True, status="Connected", configuration={"tenant_id": tenant_id},
        )
        db.add(connection); db.commit()
        user_id, organization_id, email = user.id, user.organization_id, user.email

    status = client.get("/api/auth/microsoft/status")
    assert status.status_code == 200
    assert status.json() == {"enabled": True}
    start = client.get("/api/auth/microsoft/start", follow_redirects=False)
    assert start.status_code == 303
    authorization = urlparse(start.headers["location"])
    parameters = parse_qs(authorization.query)
    assert authorization.netloc == "login.microsoftonline.com"
    assert parameters["scope"] == ["openid profile email"]
    assert parameters["prompt"] == ["select_account"]
    state, nonce = parameters["state"][0], parameters["nonce"][0]

    # Simulate a server whose local clock is one hour behind Microsoft.
    issued = int(time.time()) + 3600
    id_token = jwt.encode({
        "aud": client_id, "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        # Allow the small clock differences commonly seen on Windows servers.
        "iat": issued + 120, "nbf": issued + 120, "exp": issued + 300, "tid": tenant_id,
        "oid": object_id, "sub": "stable-subject", "nonce": nonce, "email": email,
        "name": "End User One",
    }, private_key, algorithm="RS256", headers={"kid": key_id})

    def provider_post(url, **kwargs):
        assert url.endswith("/oauth2/v2.0/token")
        assert kwargs["data"]["scope"] == "openid profile email"
        return ProviderResponse({"id_token": id_token}, {"date": formatdate(issued, usegmt=True)})

    def provider_get(url, **_kwargs):
        if url.endswith("openid-configuration"):
            return ProviderResponse({
                "jwks_uri": "https://login.microsoftonline.com/test/discovery/keys",
                "issuer": "https://login.microsoftonline.com/{tenantId}/v2.0",
            })
        return ProviderResponse({"keys": [public_jwk]})

    monkeypatch.setattr("itsm.microsoft_sso.httpx.post", provider_post)
    monkeypatch.setattr("itsm.microsoft_sso.httpx.get", provider_get)
    callback = client.get(
        "/api/admin/integrations/oauth/callback/microsoft",
        params={"state": state, "code": "authorization-code"}, follow_redirects=False,
    )
    assert callback.status_code == 303
    assert "sso=success" in callback.headers["location"]
    assert callback.headers["location"].startswith("http://localhost:8000/")
    assert "itsm_session=" in callback.headers["set-cookie"]
    assert client.get("/api/auth/me").json()["user"]["email"] == email

    with SessionLocal() as db:
        linked = db.get(User, user_id)
        assert linked.auth_source == "Microsoft Entra ID"
        assert linked.entra_tenant_id == tenant_id
        assert linked.entra_object_id == object_id
        db.query(LoginSession).filter(LoginSession.user_id == user_id).delete()
        linked.auth_source, linked.entra_tenant_id, linked.entra_object_id, linked.entra_subject = original
        db.info["organization_id"] = organization_id
        saved = db.scalar(select(IntegrationConnection).where(IntegrationConnection.name == f"SSO test {tenant_id[:8]}"))
        db.delete(saved); db.commit()

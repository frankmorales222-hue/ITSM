"""Microsoft Entra OpenID Connect sign-in for approved organizations."""
from __future__ import annotations

import hmac
import time
import uuid
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .credential_store import get_integration_secret
from .identity import provision_end_user
from .models import IntegrationConnection, Role, User, now
from .oauth_state import create_oauth_state, provider_callback_url
from .security import create_session
from .services import audit


class MicrosoftSignInError(Exception):
    """A safe, expected Microsoft sign-in rejection."""

    def __init__(self, message: str, code: str = "unknown"):
        super().__init__(message)
        self.code = code


def _application(db: Session) -> dict[str, str]:
    return {
        "client_id": settings.microsoft_client_id or get_integration_secret(db, "platform:microsoft", "client_id") or "",
        "client_secret": settings.microsoft_client_secret or get_integration_secret(db, "platform:microsoft", "client_secret") or "",
    }


def _approved_connections(db: Session) -> list[IntegrationConnection]:
    return list(db.scalars(select(IntegrationConnection).where(
        IntegrationConnection.provider == "Microsoft Entra ID",
        IntegrationConnection.enabled.is_(True),
        IntegrationConnection.archived_at.is_(None),
    )).all())


def microsoft_sign_in_status(db: Session) -> dict:
    application = _application(db)
    tenants = [str((item.configuration or {}).get("tenant_id", "")).strip() for item in _approved_connections(db)]
    return {"enabled": bool(application["client_id"] and application["client_secret"] and any(tenants))}


def _microsoft_token_error(exc: Exception, default: str) -> MicrosoftSignInError:
    """Convert Microsoft token errors into useful messages without exposing credentials."""
    response = getattr(exc, "response", None)
    payload: dict = {}
    if response is not None:
        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = {}
    provider_code = str(payload.get("error", "")).lower()
    description = str(payload.get("error_description", "")).lower()
    if provider_code == "invalid_client" or "aadsts7000215" in description or "aadsts7000222" in description:
        return MicrosoftSignInError(
            "Microsoft rejected the application credential. Enter the client secret Value (not the Secret ID), and confirm it is current and belongs to this Client ID.",
            "credentials_invalid",
        )
    if provider_code == "invalid_grant":
        return MicrosoftSignInError(
            "Microsoft rejected the authorization response. Verify the callback URL and try signing in again.",
            "authorization_invalid",
        )
    if response is not None and getattr(response, "status_code", 0) in {401, 403}:
        return MicrosoftSignInError(
            "Microsoft denied the application request. Verify the tenant approval and application permissions.",
            "microsoft_denied",
        )
    return MicrosoftSignInError(default, "provider_unavailable")


def test_microsoft_application(db: Session, connection: IntegrationConnection) -> dict[str, str]:
    """Verify the configured tenant, client ID, and secret with Microsoft."""
    tenant_id = str((connection.configuration or {}).get("tenant_id", "")).strip()
    try:
        uuid.UUID(tenant_id)
    except (ValueError, TypeError, AttributeError) as exc:
        raise MicrosoftSignInError("The approved Microsoft tenant ID is missing or invalid.", "tenant_invalid") from exc
    application = _application(db)
    if not application["client_id"] or not application["client_secret"]:
        raise MicrosoftSignInError("The Microsoft Client ID and client secret Value are required.", "not_configured")
    try:
        response = httpx.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": application["client_id"],
                "client_secret": application["client_secret"],
                "grant_type": "client_credentials",
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=20,
        )
        response.raise_for_status()
        token = response.json()
        if not token.get("access_token"):
            raise ValueError("missing access token")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise _microsoft_token_error(exc, "Microsoft could not validate the identity application configuration.") from exc
    return {"tenant_id": tenant_id, "client_id": application["client_id"]}


def microsoft_authorization_url(db: Session) -> str:
    if not microsoft_sign_in_status(db)["enabled"]:
        raise HTTPException(503, "Microsoft sign-in is not configured yet. An administrator must connect an approved tenant first.")
    application = _application(db)
    state, state_payload = create_oauth_state({"purpose": "microsoft_login", "provider": "Microsoft Entra ID"})
    return "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?" + urlencode({
        "client_id": application["client_id"],
        "response_type": "code",
        "response_mode": "query",
        "redirect_uri": provider_callback_url("microsoft"),
        "scope": "openid profile email",
        "state": state,
        "nonce": state_payload["nonce"],
        "prompt": "select_account",
    })


def _microsoft_response_time(response) -> float | None:
    """Use Microsoft's HTTPS Date header so Windows clock drift cannot reject a valid token."""
    try:
        value = response.headers.get("date")
        return parsedate_to_datetime(value).timestamp() if value else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _validated_claims(
    id_token: str,
    client_id: str,
    expected_nonce: str,
    provider_time: float | None = None,
) -> dict:
    try:
        unverified = jwt.decode(id_token, options={"verify_signature": False})
        tenant_id = str(unverified.get("tid", ""))
        uuid.UUID(tenant_id)
    except (ValueError, TypeError, jwt.PyJWTError) as exc:
        raise MicrosoftSignInError("Microsoft returned a malformed identity token.", "token_malformed") from exc
    metadata_url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
    try:
        metadata_response = httpx.get(metadata_url, timeout=20)
        metadata_response.raise_for_status()
        metadata = metadata_response.json()
        jwks_uri = str(metadata["jwks_uri"])
        provider_time = provider_time or _microsoft_response_time(metadata_response)
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise MicrosoftSignInError(
            "The server could not retrieve Microsoft OpenID signing metadata.",
            "metadata_unavailable",
        ) from exc

    try:
        header = jwt.get_unverified_header(id_token)
        key_id = str(header["kid"])
    except (KeyError, ValueError, jwt.PyJWTError) as exc:
        raise MicrosoftSignInError("Microsoft returned a token without a usable signing key ID.", "signing_key_missing") from exc

    jwk = None
    for _attempt in range(2):
        try:
            jwks_response = httpx.get(jwks_uri, timeout=20)
            jwks_response.raise_for_status()
            jwk = next((item for item in jwks_response.json()["keys"] if item.get("kid") == key_id), None)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise MicrosoftSignInError(
                "The server could not retrieve Microsoft token-signing keys.",
                "signing_keys_unavailable",
            ) from exc
        if jwk is not None:
            break
    if jwk is None:
        raise MicrosoftSignInError(
            "Microsoft rotated its signing key, but the matching key could not be retrieved. Try signing in again.",
            "signing_key_not_found",
        )

    metadata_issuer = str(metadata.get("issuer") or f"https://login.microsoftonline.com/{tenant_id}/v2.0")
    expected_issuer = metadata_issuer.replace("{tenantid}", tenant_id).replace("{tenantId}", tenant_id)
    try:
        claims = jwt.decode(
            id_token,
            key=jwt.PyJWK.from_dict(jwk).key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=expected_issuer,
            options={
                "require": ["exp", "iss", "aud", "sub", "tid", "nonce"],
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )
    except jwt.InvalidAudienceError as exc:
        raise MicrosoftSignInError(
            "Microsoft issued the token for a different Application Client ID.",
            "audience_mismatch",
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise MicrosoftSignInError(
            "Microsoft returned a token from an unexpected tenant issuer.",
            "issuer_mismatch",
        ) from exc
    except jwt.MissingRequiredClaimError as exc:
        raise MicrosoftSignInError(
            f"Microsoft's identity token is missing the required {exc.claim} claim.",
            "claim_missing",
        ) from exc
    except jwt.InvalidSignatureError as exc:
        raise MicrosoftSignInError(
            "Microsoft's identity token signature could not be verified.",
            "signature_invalid",
        ) from exc
    except (ValueError, TypeError, jwt.PyJWTError) as exc:
        raise MicrosoftSignInError("Microsoft identity token validation failed.", "token_validation") from exc

    trusted_now = provider_time if provider_time is not None else time.time()
    try:
        expires_at = float(claims["exp"])
        not_before = float(claims.get("nbf", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise MicrosoftSignInError("Microsoft returned invalid token timing information.", "token_time_invalid") from exc
    if trusted_now > expires_at + 300 or (not_before and trusted_now + 300 < not_before):
        raise MicrosoftSignInError(
            "Microsoft returned an identity token outside its valid time window. Start sign-in again.",
            "token_time_invalid",
        )

    if not hmac.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise MicrosoftSignInError("Microsoft sign-in nonce did not match", "nonce_mismatch")
    return claims


def _approved_connection(db: Session, tenant_id: str) -> IntegrationConnection:
    matches = [item for item in _approved_connections(db)
               if str((item.configuration or {}).get("tenant_id", "")).lower() == tenant_id.lower()]
    if len(matches) != 1:
        raise MicrosoftSignInError("This Microsoft organization is not approved for Northstar Desk", "tenant_not_approved")
    return matches[0]


def _link_user(db: Session, connection: IntegrationConnection, claims: dict) -> User:
    tenant_id = str(claims["tid"])
    object_id = str(claims.get("oid") or claims["sub"])
    subject = str(claims["sub"])
    email = str(claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip().lower()
    if not email or "@" not in email:
        raise MicrosoftSignInError("Microsoft did not return a usable work email address", "email_missing")
    db.info["organization_id"] = connection.organization_id
    user = db.scalar(select(User).where(
        User.entra_tenant_id == tenant_id,
        or_(User.entra_object_id == object_id, User.entra_subject == subject),
    ))
    if not user:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user:
        user, created = provision_end_user(
            db,
            organization_id=connection.organization_id,
            email=email,
            display_name=str(claims.get("name") or ""),
            auth_source="Microsoft Entra ID",
            role_source="Microsoft Entra first login",
        )
        if created:
            audit(
                db,
                "user.microsoft_provisioned",
                "user",
                user.id,
                actor_id=user.id,
                new={"tenant_id": tenant_id, "email": email, "role": Role.END_USER.value},
            )
    if user.organization_id != connection.organization_id:
        raise MicrosoftSignInError("This Microsoft account belongs to another Northstar organization", "organization_conflict")
    if not user.active:
        raise MicrosoftSignInError("This Northstar Desk account is inactive", "account_inactive")
    if user.entra_tenant_id and (user.entra_tenant_id != tenant_id or user.entra_object_id not in {None, object_id}):
        raise MicrosoftSignInError("This account is already linked to another Microsoft identity", "identity_conflict")
    user.entra_tenant_id = tenant_id
    user.entra_object_id = object_id
    user.entra_subject = subject
    user.auth_source = "Microsoft Entra ID"
    user.must_change_password = False
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now()
    return user


def complete_microsoft_sign_in(db: Session, payload: dict, code: str | None, error: str | None,
                               error_description: str | None, request: Request) -> RedirectResponse:
    if error or not code:
        raise MicrosoftSignInError(error_description or "Microsoft sign-in was cancelled", "cancelled")
    application = _application(db)
    if not application["client_id"] or not application["client_secret"]:
        raise MicrosoftSignInError("Microsoft sign-in is not configured", "not_configured")
    try:
        token_response = httpx.post(
            "https://login.microsoftonline.com/organizations/oauth2/v2.0/token",
            data={
                "client_id": application["client_id"],
                "client_secret": application["client_secret"],
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": provider_callback_url("microsoft"),
                "scope": "openid profile email",
            }, timeout=20,
        )
        token_response.raise_for_status()
        id_token = token_response.json()["id_token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise _microsoft_token_error(exc, "Microsoft sign-in could not be completed.") from exc
    claims = _validated_claims(
        id_token,
        application["client_id"],
        str(payload["nonce"]),
        _microsoft_response_time(token_response),
    )
    connection = _approved_connection(db, str(claims["tid"]))
    user = _link_user(db, connection, claims)
    raw, _csrf, _session = create_session(db, user)
    audit(db, "login.microsoft_succeeded", "user", user.id, actor_id=user.id,
          source_ip=request.client.host if request.client else None,
          new={"tenant_id": user.entra_tenant_id, "provider": "Microsoft Entra ID"})
    db.commit()
    # The callback may intentionally use localhost even when PUBLIC_URL uses
    # 127.0.0.1. Host-only cookies do not cross that boundary, so finish on
    # the callback origin that actually received and set the session cookie.
    callback = urlsplit(provider_callback_url("microsoft"))
    callback_origin = f"{callback.scheme}://{callback.netloc}"
    response = RedirectResponse(f"{callback_origin}/?sso=success#home", status_code=303)
    response.set_cookie("itsm_session", raw, httponly=True, secure=settings.cookie_secure, samesite="lax",
                        max_age=settings.session_minutes * 60, path="/")
    return response

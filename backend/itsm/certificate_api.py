"""Administrator-only HTTPS certificate installation.

The certificate material is handled on the server only. It is never returned
by the API or stored in the application database.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Role, User
from .security import require_roles
from .services import audit

router = APIRouter(prefix="/api/admin/https-certificate", tags=["HTTPS certificate"])
MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _root() -> Path:
    return Path(settings.data_directory).resolve().parent


def _certificate_directory() -> Path:
    path = _root() / "certificates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_path() -> Path:
    return _certificate_directory() / "status.json"


def _read_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"mode": "internal", "status": "Using Northstar internal certificate."}


def _write_state(value: dict) -> None:
    target = _state_path()
    pending = target.with_suffix(".pending")
    pending.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(pending, target)


def _public_hostname() -> str:
    return (urlsplit(settings.public_url).hostname or "").lower()


def _read_upload(item: UploadFile | None, label: str) -> bytes:
    if item is None:
        raise HTTPException(400, f"Select a {label} file.")
    data = item.file.read(MAX_UPLOAD_BYTES + 1)
    item.file.close()
    if not data:
        raise HTTPException(400, f"The {label} file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"The {label} file exceeds the 2 MB safety limit.")
    return data


def _match_certificate_key(cert: x509.Certificate, key: object) -> None:
    certificate_key = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    supplied_key = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if certificate_key != supplied_key:
        raise HTTPException(400, "The certificate and private key do not belong together.")


def _certificate_names(cert: x509.Certificate) -> list[str]:
    try:
        return list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        attributes = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        return [attributes[0].value] if attributes else []


def _load_certificate(data: bytes) -> tuple[x509.Certificate, bytes]:
    """Accept standard PEM chains and a single DER certificate safely."""
    try:
        return x509.load_pem_x509_certificate(data), data
    except ValueError:
        try:
            certificate = x509.load_der_x509_certificate(data)
            return certificate, certificate.public_bytes(serialization.Encoding.PEM)
        except ValueError as exc:
            raise HTTPException(400, "Northstar could not read the certificate file. Upload a PEM full-chain certificate or a PFX package.") from exc


def _load_intermediate_certificates(data: bytes) -> list[x509.Certificate]:
    """Read the CA bundle supplied with a website certificate."""
    for loader in (pkcs7.load_der_pkcs7_certificates, pkcs7.load_pem_pkcs7_certificates):
        try:
            certificates = list(loader(data))
            if certificates:
                return certificates
        except ValueError:
            pass
    try:
        certificates = list(x509.load_pem_x509_certificates(data))
        if certificates:
            return certificates
    except ValueError:
        pass
    try:
        return [x509.load_der_x509_certificate(data)]
    except ValueError as exc:
        raise HTTPException(400, "Northstar could not read the intermediate certificate chain. Upload the .p7b or PEM chain supplied by your certificate authority.") from exc


def _pem_chain(certificates: list[x509.Certificate]) -> bytes:
    return b"".join(certificate.public_bytes(serialization.Encoding.PEM) for certificate in certificates)


def _validate_certificate_chain(material: bytes, leaf: x509.Certificate) -> None:
    """Reject broken PEM bundles before the HTTPS proxy is restarted.

    A browser validates the issuer chain, while a private key check only proves
    ownership of the first certificate.  This prevents the UI from calling a
    leaf-only GoDaddy upload a successful HTTPS installation.
    """
    try:
        certificates = x509.load_pem_x509_certificates(material)
    except ValueError as exc:
        raise HTTPException(400, "Northstar could not read the certificate chain. Upload a PEM full-chain certificate or a PFX package.") from exc
    if not certificates or certificates[0].fingerprint(hashes.SHA256()) != leaf.fingerprint(hashes.SHA256()):
        raise HTTPException(400, "The first certificate in the chain must be the website certificate.")
    fingerprints = [cert.fingerprint(hashes.SHA256()) for cert in certificates]
    if len(set(fingerprints)) != len(fingerprints):
        raise HTTPException(400, "The certificate chain contains the same certificate more than once.")
    for certificate, issuer in zip(certificates, certificates[1:]):
        if certificate.issuer != issuer.subject:
            raise HTTPException(400, "The certificate chain is incomplete or out of order. Upload the website certificate followed by its issuing intermediate certificate(s).")
        try:
            certificate.verify_directly_issued_by(issuer)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "The certificate chain could not be verified. Upload the full chain supplied by your certificate authority.") from exc


def _validate_certificate(cert: x509.Certificate, key: object) -> dict:
    _match_certificate_key(cert, key)
    now = datetime.now(timezone.utc)
    not_after = cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc") else cert.not_valid_after.replace(tzinfo=timezone.utc)
    not_before = cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc") else cert.not_valid_before.replace(tzinfo=timezone.utc)
    if not_before > now or not_after <= now:
        raise HTTPException(400, "This certificate is not currently valid. Check its start and expiration dates.")
    hostname = _public_hostname()
    names = _certificate_names(cert)
    if hostname:
        def matches(name: str) -> bool:
            name = name.lower().rstrip(".")
            if name.startswith("*."):
                suffix = name[1:]
                return hostname.endswith(suffix) and hostname.count(".") == suffix.count(".")
            return hostname == name
        if not any(matches(name) for name in names):
            raise HTTPException(400, f"This certificate does not cover {hostname}. Select a certificate issued for the Northstar website name.")
    return {"hostname": hostname, "subject": cert.subject.rfc4514_string(), "issuer": cert.issuer.rfc4514_string(), "expires_at": not_after.isoformat(), "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex().upper(), "names": names}


def _load_material(
    certificate: UploadFile | None,
    private_key: UploadFile | None,
    intermediate_chain: UploadFile | None,
    pfx: UploadFile | None,
    password: str | None,
) -> tuple[bytes, bytes, dict]:
    if pfx and (certificate or private_key or intermediate_chain):
        raise HTTPException(400, "Use either a PFX package or a certificate and private-key pair, not both.")
    try:
        if pfx:
            key, cert, extras = pkcs12.load_key_and_certificates(_read_upload(pfx, "PFX"), (password or "").encode() or None)
            if not key or not cert:
                raise HTTPException(400, "The PFX package does not contain both a certificate and private key.")
            fullchain = _pem_chain([cert, *(extras or [])])
        else:
            cert, uploaded_certificate_material = _load_certificate(_read_upload(certificate, "certificate"))
            key = serialization.load_pem_private_key(_read_upload(private_key, "private key"), password=(password or "").encode() or None)
            if intermediate_chain:
                intermediates = _load_intermediate_certificates(_read_upload(intermediate_chain, "intermediate certificate chain"))
                fullchain = _pem_chain([cert, *intermediates])
            else:
                fullchain = uploaded_certificate_material
        _validate_certificate_chain(fullchain, cert)
        details = _validate_certificate(cert, key)
        details["chain_certificates"] = len(x509.load_pem_x509_certificates(fullchain))
        key_bytes = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        return fullchain, key_bytes, details
    except HTTPException:
        raise
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, "Northstar could not read the certificate package, private key, or password.") from exc


def _caddy_binary() -> Path:
    configured = os.environ.get("ITSM_CADDY_BINARY", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates += [Path(sys.executable).resolve().parent / "Caddy" / "caddy.exe", Path(__file__).resolve().parents[2] / "installer" / "vendor" / "Caddy" / "caddy.exe"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise HTTPException(500, "The Northstar HTTPS service executable was not found. Use the server installation, not a development copy, to install a certificate.")


def _caddy_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _custom_caddyfile(source: str, certificate: Path, key: Path) -> str:
    lines = source.splitlines()
    matches = [index for index, line in enumerate(lines) if line.strip().startswith("tls ")]
    if len(matches) != 1:
        raise HTTPException(400, "Northstar could not safely identify the HTTPS certificate setting. Keep the existing Caddyfile unchanged and contact support.")
    lines[matches[0]] = f'    tls "{_caddy_path(certificate)}" "{_caddy_path(key)}"'
    return "\n".join(lines) + "\n"


def _validate_caddy(candidate: Path) -> None:
    result = subprocess.run([str(_caddy_binary()), "validate", "--config", str(candidate), "--adapter", "caddyfile"], capture_output=True, text=True, timeout=30)
    if result.returncode:
        message = (result.stderr or result.stdout or "Caddy rejected the configuration.").strip()
        raise HTTPException(400, f"The HTTPS service rejected this certificate configuration: {message[:500]}")


def _protect_private_key(path: Path) -> None:
    """The HTTPS proxy runs as SYSTEM; no ordinary desktop account needs this key."""
    if os.name != "nt":
        return
    result = subprocess.run([
        "icacls.exe", str(path), "/inheritance:r", "/grant:r",
        "SYSTEM:(F)", "BUILTIN\\Administrators:(F)",
    ], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise HTTPException(500, "Northstar could not secure the private-key file. The existing HTTPS certificate was left unchanged.")


def _https_port() -> int:
    return urlsplit(settings.public_url).port or 443


def _served_certificate_fingerprint(timeout_seconds: int = 25) -> str:
    """Read the certificate the local HTTPS listener actually presents."""
    hostname = _public_hostname()
    if not hostname:
        raise RuntimeError("Northstar's public HTTPS hostname is not configured.")
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", _https_port()), timeout=3) as connection:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                with context.wrap_socket(connection, server_hostname=hostname) as stream:
                    certificate = x509.load_der_x509_certificate(stream.getpeercert(binary_form=True))
                    return certificate.fingerprint(hashes.SHA256()).hex().upper()
        except (OSError, ssl.SSLError, ValueError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Northstar HTTPS did not present a certificate on local port {_https_port()}: {last_error}")


def _restart_https(state: dict) -> None:
    try:
        # Caddy is dedicated to Northstar Desk.  Ending only the scheduled task
        # can leave its child listener alive, which caused an old certificate to
        # continue being served after the UI reported a successful restart.
        subprocess.run(["schtasks.exe", "/End", "/TN", "Northstar HTTPS"], capture_output=True, text=True, timeout=20)
        subprocess.run(["taskkill.exe", "/F", "/IM", "caddy.exe"], capture_output=True, text=True, timeout=20)
        time.sleep(1)
        result = subprocess.run(["schtasks.exe", "/Run", "/TN", "Northstar HTTPS"], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "Unable to start Northstar HTTPS").strip())
        served = _served_certificate_fingerprint()
        if served != state["fingerprint_sha256"]:
            raise RuntimeError("Northstar HTTPS started but is still presenting a different certificate. The previous browser-trusted certificate setting was not reported as successful.")
        state.update({"status": "Certificate installed and verified on the live HTTPS listener.", "restart_pending": False, "restart_failed": False, "served_fingerprint_sha256": served})
    except Exception as exc:
        state.update({"status": f"Certificate files were installed, but the HTTPS restart needs attention: {exc}", "restart_pending": False, "restart_failed": True})
    _write_state(state)


@router.get("")
def certificate_status(user: User = Depends(require_roles(Role.ADMIN))):
    state = _read_state()
    state["hostname"] = state.get("hostname") or _public_hostname()
    state["certificate_installed"] = bool((_certificate_directory() / "fullchain.pem").is_file() and (_certificate_directory() / "privatekey.pem").is_file())
    return state


@router.post("/install")
def install_certificate(certificate: UploadFile | None = File(None), private_key: UploadFile | None = File(None), intermediate_chain: UploadFile | None = File(None), pfx: UploadFile | None = File(None), password: str | None = Form(None), user: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    fullchain, key_bytes, details = _load_material(certificate, private_key, intermediate_chain, pfx, password)
    root = _root(); caddyfile = root / "Caddyfile"
    if not caddyfile.is_file():
        raise HTTPException(400, "Northstar's HTTPS configuration was not found. Install this certificate from the production server application.")
    stage = _certificate_directory() / "staging" / uuid.uuid4().hex
    stage.mkdir(parents=True, exist_ok=False)
    staged_certificate, staged_key = stage / "fullchain.pem", stage / "privatekey.pem"
    staged_certificate.write_bytes(fullchain); staged_key.write_bytes(key_bytes)
    candidate = stage / "Caddyfile"
    candidate.write_text(_custom_caddyfile(caddyfile.read_text(encoding="utf-8"), staged_certificate, staged_key), encoding="utf-8")
    try:
        _validate_caddy(candidate)
        cert_dir = _certificate_directory(); backup = cert_dir / "backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup.mkdir(parents=True, exist_ok=True)
        for existing in (caddyfile, cert_dir / "fullchain.pem", cert_dir / "privatekey.pem"):
            if existing.is_file(): shutil.copy2(existing, backup / existing.name)
        live_certificate, live_key = cert_dir / "fullchain.pem", cert_dir / "privatekey.pem"
        os.replace(staged_certificate, live_certificate); os.replace(staged_key, live_key)
        _protect_private_key(live_key)
        pending = caddyfile.with_suffix(".pending")
        pending.write_text(_custom_caddyfile(caddyfile.read_text(encoding="utf-8"), live_certificate, live_key), encoding="utf-8")
        os.replace(pending, caddyfile)
        state = {"mode": "custom", **details, "status": "Certificate validated. Restarting the HTTPS service…", "restart_pending": True, "restart_failed": False, "installed_at": datetime.now(timezone.utc).isoformat()}
        _write_state(state)
        audit(db, "https_certificate.installed", "https_certificate", None, user.id, new={"hostname": details["hostname"], "expires_at": details["expires_at"], "fingerprint": details["fingerprint_sha256"]})
        db.commit()
        threading.Thread(target=_restart_https, args=(state,), daemon=True).start()
        return {"ok": True, **state}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

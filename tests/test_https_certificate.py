from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from itsm import certificate_api
from itsm import worker
from itsm.certificate_api import _custom_caddyfile, _load_intermediate_certificates, _validate_certificate, _validate_certificate_chain
from itsm.config import settings
from itsm.models import AutomationFailure, SystemState


def certificate_for(name: str, key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        .sign(key, hashes.SHA256()))
    return cert, key


def test_certificate_requires_hostname_and_matching_key(monkeypatch):
    monkeypatch.setattr(settings, "public_url", "https://helpdesk.example.com")
    cert, key = certificate_for("helpdesk.example.com")
    details = _validate_certificate(cert, key)
    assert details["hostname"] == "helpdesk.example.com"
    assert details["expires_at"]
    with pytest.raises(HTTPException, match="do not belong together"):
        _validate_certificate(cert, rsa.generate_private_key(public_exponent=65537, key_size=2048))
    other, other_key = certificate_for("other.example.com")
    with pytest.raises(HTTPException, match="does not cover"):
        _validate_certificate(other, other_key)


def test_caddyfile_replaces_only_certificate_directive():
    original = "helpdesk.example.com {\n    tls internal\n    reverse_proxy 127.0.0.1:8000\n}\n"
    configured = _custom_caddyfile(original, Path("C:/northstar-test/fullchain.pem"), Path("C:/northstar-test/privatekey.pem"))
    assert "tls internal" not in configured
    assert "reverse_proxy 127.0.0.1:8000" in configured
    assert "fullchain.pem" in configured


def test_certificate_chain_rejects_duplicate_or_out_of_order_material():
    cert, _ = certificate_for("helpdesk.example.com")
    material = cert.public_bytes(serialization.Encoding.PEM)
    _validate_certificate_chain(material, cert)
    with pytest.raises(HTTPException, match="more than once"):
        _validate_certificate_chain(material + material, cert)

    other, _ = certificate_for("issuer.example.com")
    with pytest.raises(HTTPException, match="incomplete or out of order"):
        _validate_certificate_chain(material + other.public_bytes(serialization.Encoding.PEM), cert)


def test_intermediate_loader_accepts_pem_certificate_chain():
    certificate, _ = certificate_for("issuer.example.com")
    loaded = _load_intermediate_certificates(certificate.public_bytes(serialization.Encoding.PEM))
    assert loaded[0].fingerprint(hashes.SHA256()) == certificate.fingerprint(hashes.SHA256())


def test_certificate_status_warns_when_custom_certificate_is_not_in_live_caddyfile(tmp_path, monkeypatch):
    certificate, key = certificate_for("helpdesk.example.com")
    certificate_dir = tmp_path / "certificates"
    certificate_dir.mkdir()
    certificate_bytes = certificate.public_bytes(serialization.Encoding.PEM)
    (certificate_dir / "fullchain.pem").write_bytes(certificate_bytes)
    (certificate_dir / "privatekey.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
    (certificate_dir / "status.json").write_text(
        '{"mode":"custom","fingerprint_sha256":"' + fingerprint + '"}', encoding="utf-8")
    (tmp_path / "Caddyfile").write_text(
        "helpdesk.example.com {\n    tls internal\n    reverse_proxy 127.0.0.1:8000\n}\n",
        encoding="utf-8")
    monkeypatch.setattr(certificate_api, "_root", lambda: tmp_path)
    monkeypatch.setattr(certificate_api, "_served_certificate_fingerprint", lambda timeout_seconds=2: fingerprint)

    status = certificate_api.certificate_status(user=None)

    assert status["certificate_installed"] is True
    assert status["caddyfile_serves_custom"] is False
    assert status["live_served_fingerprint_sha256"] == fingerprint
    assert status["needs_attention"] is True
    assert status["status"] == "Custom certificate is installed but NOT being served"


class _WorkerDb:
    def __init__(self):
        self.rows = []

    def get(self, _model, _key):
        return None

    def add(self, item):
        self.rows.append(item)


def _custom_certificate_files(root: Path) -> str:
    certificate, key = certificate_for("helpdesk.example.com")
    certificate_dir = root / "certificates"
    certificate_dir.mkdir()
    (certificate_dir / "fullchain.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    (certificate_dir / "privatekey.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
    (certificate_dir / "status.json").write_text(
        '{"mode":"custom","fingerprint_sha256":"' + fingerprint + '"}', encoding="utf-8")
    (root / "Caddyfile").write_text(
        "helpdesk.example.com {\n    tls internal\n    reverse_proxy 127.0.0.1:8000\n}\n",
        encoding="utf-8")
    return fingerprint


def test_hourly_certificate_check_reapplies_custom_tls_and_restarts_https(tmp_path, monkeypatch):
    fingerprint = _custom_certificate_files(tmp_path)
    served = iter(["OLD", fingerprint])
    restarted = []
    monkeypatch.setattr(certificate_api, "_root", lambda: tmp_path)
    monkeypatch.setattr(certificate_api, "_served_certificate_fingerprint",
                        lambda timeout_seconds=3: next(served))
    monkeypatch.setattr(certificate_api, "_restart_https", lambda state: restarted.append(state))
    db = _WorkerDb()

    assert worker.https_certificate_health_job(db) == 1

    assert restarted and restarted[0]["fingerprint_sha256"] == fingerprint
    assert "tls internal" not in (tmp_path / "Caddyfile").read_text(encoding="utf-8")
    monitor = next(item for item in db.rows if isinstance(item, SystemState))
    assert monitor.value["status"] == "Repaired"


def test_hourly_certificate_check_records_failure_when_listener_still_mismatches(tmp_path, monkeypatch):
    _custom_certificate_files(tmp_path)
    monkeypatch.setattr(certificate_api, "_root", lambda: tmp_path)
    monkeypatch.setattr(certificate_api, "_served_certificate_fingerprint",
                        lambda timeout_seconds=3: "WRONG")
    monkeypatch.setattr(certificate_api, "_restart_https", lambda state: None)
    db = _WorkerDb()

    assert worker.https_certificate_health_job(db) == 0

    failure = next(item for item in db.rows if isinstance(item, AutomationFailure))
    assert failure.failure_type == "https_certificate"
    assert "not being served" in failure.summary

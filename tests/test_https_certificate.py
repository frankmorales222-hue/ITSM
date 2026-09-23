from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from itsm.certificate_api import _custom_caddyfile, _load_intermediate_certificates, _validate_certificate, _validate_certificate_chain
from itsm.config import settings


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

"""Shared Caddy TLS selection for setup, certificate management, and repair."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes


def caddy_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def certificate_paths(data_root: Path) -> tuple[Path, Path]:
    directory = data_root / "certificates"
    return directory / "fullchain.pem", directory / "privatekey.pem"


def read_certificate_state(data_root: Path) -> dict:
    try:
        value = json.loads((data_root / "certificates" / "status.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"mode": "internal"}
    except (OSError, ValueError, TypeError):
        return {"mode": "internal"}


def custom_tls_directive(certificate: Path, private_key: Path) -> str:
    return f'tls "{caddy_path(certificate)}" "{caddy_path(private_key)}"'


def installed_certificate_fingerprint(certificate: Path) -> str:
    material = certificate.read_bytes()
    loaded = x509.load_pem_x509_certificate(material)
    return loaded.fingerprint(hashes.SHA256()).hex().upper()


def selected_tls_directive(data_root: Path) -> tuple[str, str | None]:
    """Select custom TLS only when its recorded, present certificate is valid."""
    state = read_certificate_state(data_root)
    if state.get("mode") != "custom":
        return "tls internal", None
    certificate, private_key = certificate_paths(data_root)
    if not certificate.is_file() or not private_key.is_file():
        return "tls internal", (
            "Custom HTTPS mode is recorded, but fullchain.pem or privatekey.pem is missing; "
            "Northstar kept the internal certificate."
        )
    try:
        loaded = x509.load_pem_x509_certificate(certificate.read_bytes())
        expires_at = (loaded.not_valid_after_utc if hasattr(loaded, "not_valid_after_utc")
                      else loaded.not_valid_after.replace(tzinfo=timezone.utc))
        if expires_at <= datetime.now(timezone.utc):
            return "tls internal", (
                f"The installed custom HTTPS certificate expired at {expires_at.isoformat()}; "
                "Northstar kept the internal certificate."
            )
    except (OSError, ValueError) as exc:
        return "tls internal", (
            f"The installed custom HTTPS certificate could not be read ({type(exc).__name__}); "
            "Northstar kept the internal certificate."
        )
    return custom_tls_directive(certificate, private_key), None


def replace_tls_directive(source: str, directive: str) -> str:
    lines = source.splitlines()
    matches = [index for index, line in enumerate(lines) if line.strip().startswith("tls ")]
    if len(matches) != 1:
        raise ValueError("Northstar could not safely identify the HTTPS certificate setting.")
    lines[matches[0]] = f"    {directive}"
    return "\n".join(lines) + "\n"


def caddyfile_uses_custom_certificate(data_root: Path) -> bool:
    caddyfile = data_root / "Caddyfile"
    certificate, private_key = certificate_paths(data_root)
    try:
        source = caddyfile.read_text(encoding="utf-8")
    except OSError:
        return False
    expected = custom_tls_directive(certificate, private_key)
    return any(line.strip() == expected for line in source.splitlines())

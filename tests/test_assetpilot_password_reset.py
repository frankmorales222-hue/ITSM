import base64
import struct

from installer.assetpilot_password_reset import (
    aspnet_identity_v3_hash,
    password_errors,
)


def test_password_policy_accepts_strong_password():
    assert password_errors("AssetPilot-Recovery-2026!") == []


def test_password_policy_reports_each_missing_requirement():
    errors = password_errors("short")
    assert "Use at least 12 characters" in errors
    assert "Add an uppercase letter" in errors
    assert "Add a number" in errors
    assert "Add a symbol" in errors


def test_hash_uses_aspnet_identity_v3_wire_format():
    encoded = aspnet_identity_v3_hash(
        "AssetPilot-Recovery-2026!",
        salt=bytes(range(16)),
        iterations=100_000,
    )
    payload = base64.b64decode(encoded)

    assert payload[0] == 1
    assert struct.unpack(">I", payload[1:5])[0] == 2
    assert struct.unpack(">I", payload[5:9])[0] == 100_000
    assert struct.unpack(">I", payload[9:13])[0] == 16
    assert payload[13:29] == bytes(range(16))
    assert len(payload[29:]) == 32

"""Create signing keys and signed offline Northstar Desk update packages."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PRODUCT = "Northstar Desk Server"


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def protect_private_key(path: Path) -> None:
    if os.name == "nt":
        subprocess.run(["icacls.exe", str(path), "/inheritance:r", "/grant:r",
                        f"{getpass.getuser()}:(F)", "SYSTEM:(F)"], check=True,
                       stdout=subprocess.DEVNULL)
    else:
        path.chmod(0o600)


def keygen(private_path: Path, public_path: Path) -> None:
    if private_path.exists() or public_path.exists():
        raise SystemExit("Refusing to replace an existing signing key.")
    password = getpass.getpass("New private-key password: ")
    confirm = getpass.getpass("Confirm private-key password: ")
    if len(password) < 16 or password != confirm:
        raise SystemExit("Passwords must match and contain at least 16 characters.")
    key = Ed25519PrivateKey.generate()
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                               serialization.PrivateFormat.PKCS8,
                                               serialization.BestAvailableEncryption(password.encode())))
    protect_private_key(private_path)
    raw_public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(base64.b64encode(raw_public).decode("ascii") + "\n", encoding="ascii")
    print(f"Private key: {private_path.resolve()}")
    print(f"Public verification key: {public_path.resolve()}")
    print("Keep the private key offline. Put only the public key in ITSM_UPDATE_PUBLIC_KEY.")


def authenticode_valid(path: Path) -> bool:
    if os.name != "nt":
        return False
    escaped_path = str(path).replace("'", "''")
    command = f"(Get-AuthenticodeSignature -LiteralPath '{escaped_path}').Status"
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            check=False, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "Valid"


def signing_password(password_file: Path | None) -> str:
    """Read the build-only key password without placing it on a command line."""
    if password_file:
        try:
            value = password_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SystemExit(f"Unable to read signing password file: {exc}") from exc
        if not value:
            raise SystemExit("The signing password file is empty.")
        return value
    return getpass.getpass("Private-key password: ")


def build(args: argparse.Namespace) -> None:
    payload = args.payload.resolve()
    if not payload.is_file() or payload.suffix.lower() != ".exe":
        raise SystemExit("The update payload must be an existing Windows .exe installer.")
    if not args.allow_unsigned and not authenticode_valid(payload):
        raise SystemExit("The installer does not have a valid Authenticode signature. Sign it before building a production update.")
    password = signing_password(args.password_file)
    key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=password.encode())
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("The selected private key is not an Ed25519 update-signing key.")
    notes = args.release_notes_file.read_text(encoding="utf-8") if args.release_notes_file else args.release_notes
    manifest = {
        "product": PRODUCT,
        "version": args.version,
        "package_id": str(uuid.uuid4()),
        "released_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "publisher": args.publisher,
        "payload": payload.name,
        "payload_sha256": sha256(payload),
        "release_notes": notes.strip(),
        "database_backup_required": True,
    }
    if args.component_update:
        manifest["component_update"] = True
    if args.minimum_current_version:
        manifest["minimum_current_version"] = args.minimum_current_version
    manifest_bytes = canonical(manifest)
    signature = base64.b64encode(key.sign(manifest_bytes))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", manifest_bytes)
        archive.writestr("signature.ed25519", signature)
        archive.write(payload, payload.name)
    digest = sha256(args.output)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(f"{digest}  {args.output.name}\n", encoding="ascii")
    print(f"Signed update: {args.output.resolve()}")
    print(f"SHA-256: {digest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Northstar Desk offline update packaging")
    commands = parser.add_subparsers(dest="command", required=True)
    keys = commands.add_parser("keygen", help="Create a password-protected offline signing key")
    keys.add_argument("--private-key", type=Path, required=True)
    keys.add_argument("--public-key", type=Path, required=True)
    package = commands.add_parser("build", help="Sign an installer as a .nsupdate package")
    package.add_argument("--private-key", type=Path, required=True)
    package.add_argument("--payload", type=Path, required=True)
    package.add_argument("--version", required=True)
    package.add_argument("--publisher", default="Northstar")
    package.add_argument("--release-notes", default="")
    package.add_argument("--release-notes-file", type=Path)
    package.add_argument("--minimum-current-version", default="")
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--password-file", type=Path, help="Build-only file containing the private-key password")
    package.add_argument("--allow-unsigned", action="store_true", help="Development only; never use for production")
    package.add_argument("--component-update", action="store_true", help="Mark a signed package that updates a bounded component without changing the server build")
    args = parser.parse_args()
    if args.command == "keygen":
        keygen(args.private_key, args.public_key)
    else:
        build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

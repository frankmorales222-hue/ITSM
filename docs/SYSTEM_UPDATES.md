# Signed offline updates and distribution protection

Northstar Desk supports administrator-controlled offline updates. A release is delivered as one `.nsupdate` file. The server never accepts source archives, ordinary ZIP files, unsigned manifests, a version that is not newer than the installed version, a reused version, or a reused package ID.

## Security model

Each update uses two complementary signatures:

1. The Windows installer must have a valid Authenticode signature from the software publisher. Sign production installers with SHA-256 and an RFC 3161 SHA-256 timestamp.
2. The `.nsupdate` manifest is signed with the Northstar release Ed25519 private key. The installed server contains only the public verification key. The manifest signature covers the release version, package identity, installer filename, installer SHA-256 hash, publisher, date, minimum supported starting version, and release notes.

The private update key and Authenticode signing credentials must never be copied to the application server, repository, installer, update package, or normal administrator workstation. Keep the private update key in protected offline release storage with a tested backup and access limited to the release owner.

## Establish the release key once

On the protected build computer:

```powershell
.venv\Scripts\python.exe installer\update-package.py keygen `
  --private-key D:\NorthstarReleaseKeys\northstar.update-private.pem `
  --public-key installer\signing\update-public-key.txt
```

Use a unique password of at least 16 characters. Back up the encrypted private key and its password separately. `installer\signing\update-public-key.txt` is public and is embedded into the initial server installer. The installer writes this public key into the protected server configuration. Replacing it requires rebuilding and installing a trusted full server installer; normal application administrators cannot change the trust key in the web interface.

## Build a future update

1. Increase the authoritative version in `backend\itsm\__init__.py` and the Windows installer version.
2. Build and test the full server installer.
3. Authenticode-sign and timestamp the `.exe` using the organization code-signing certificate. Verify it with `signtool verify /pa`.
4. Create the offline package:

```powershell
.venv\Scripts\python.exe installer\update-package.py build `
  --private-key D:\NorthstarReleaseKeys\northstar.update-private.pem `
  --payload installer\artifacts\NorthstarDesk-Server-Setup-0.4.4.exe `
  --version 0.4.4 `
  --minimum-current-version 0.3.0 `
  --publisher "Northstar" `
  --release-notes-file release-notes-0.4.4.txt `
  --output installer\artifacts\NorthstarDesk-0.4.4.nsupdate
```

The builder refuses an installer without a valid Authenticode signature unless the explicit development-only `--allow-unsigned` switch is used. Never use that switch for a network deployment.

## Install an update from the application

1. Sign in as an administrator.
2. Open **Help Desk Settings → System updates**.
3. Browse to the `.nsupdate` file and select **Upload and validate**.
4. Review its version, publisher, release notes, package hash, and validation status.
5. Select **Install update** and type the displayed target version.

Before installation, Northstar re-verifies the package and extracted installer, creates and verifies a database backup, records the administrator and release in the audit log, and places the update into `Installing` status. The Windows installer stops both application tasks, updates compiled application files, applies database migrations, recreates the startup tasks, and restarts the applications. On restart, Northstar records the release as `Installed`. A failed or incomplete restart remains visible in version history.

Downgrades and repeated releases are blocked. Recovering an earlier release is a deliberate disaster-recovery operation: restore the matching database backup and reinstall the matching previously signed full installer while the service is stopped.

## Protecting the product code

The production server package contains compiled/bundled backend files, minified browser assets, and published .NET binaries; it does not contain the source repository, tests, build scripts, Git history, private signing key, or source maps. Authorization and sensitive business rules remain enforced by the server API rather than trusted to browser JavaScript. Configuration secrets remain under protected ProgramData ACLs or the Windows credential store.

No software installed on a customer's computer can be made impossible to inspect, copy, or reverse engineer. Administrators necessarily have access to the files that Windows executes, and browser code must be delivered to the browser. Packaging, compilation, minification, and obfuscation raise the effort required but are not a security boundary. Authentic signatures, hashes, server-side authorization, least-privilege ACLs, Windows Defender Application Control or AppLocker, licensing terms, and keeping signing keys and source off the deployed server are the practical controls. Never place secrets or authorization decisions in browser code.

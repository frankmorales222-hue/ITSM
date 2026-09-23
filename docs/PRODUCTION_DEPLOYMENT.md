# Production deployment

This guide promotes the existing local Northstar Desk data to a shared Windows-hosted installation. Do not expose Uvicorn directly to technicians or the internet. Use an HTTPS reverse proxy and a DNS name.

## Required decisions and infrastructure

- A supported Windows computer or server that remains powered on
- A dedicated Windows service account with logon-as-batch permission
- PostgreSQL and the PostgreSQL command-line tools (`pg_dump` and `pg_restore`)
- Two DNS names, such as `helpdesk.company.example` and `assets.company.example`
- An HTTPS certificate, normally managed by the reverse proxy
- A protected backup destination on a different disk or secured network location

## Prepare the application

1. Run `scripts\configure-shared-deployment.ps1 -DnsName helpdesk.company.example -AssetDnsName assets.company.example -PostgresServer POSTGRES-SERVER` or copy `deployment/production.env.example` to `.env` and replace every example value. The helper backs up an existing `.env`, prompts securely for the database password, generates the application secret, disables outbound email for the pilot, locks the file ACL, and creates `deployment\Caddyfile` with separate loopback proxies for Northstar Desk and AssetPilot.
2. Grant the service account read/execute access to the project and write access only to `logs` and the configured backup directory.
3. Run `scripts/install.cmd` while the production `.env` is active.
4. Run `scripts/build.cmd` and keep the resulting tested `frontend/dist` directory with the deployment.
5. Run `scripts/production-check.cmd`. Do not proceed while it reports an error.

Generate the application secret locally rather than using a human password:

```powershell
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Move the existing data to PostgreSQL

Create an empty PostgreSQL database owned by a dedicated, non-administrator database account. Stop the local application, then run:

```powershell
scripts\migrate-to-postgres.ps1 -Server "POSTGRES-SERVER" -Database "northstar_desk"
```

The script securely prompts for the PostgreSQL account so its password is not stored in PowerShell history. It first creates and verifies a SQLite backup, initializes the target with Alembic, refuses a target containing application data, copies all records in one transaction, and advances PostgreSQL identity sequences. The SQLite source is never modified. Put the target URL in `.env` only after this command succeeds, restrict `.env` so only administrators and the service account can read it, and never commit it to source control.

## HTTPS and network boundary

Bind Northstar Desk to port 8000 only behind a reverse proxy. `deployment/Caddyfile.example` shows the minimum Caddy configuration; IIS with Application Request Routing is also acceptable. Permit inbound TCP 443 to the reverse proxy. Do not permit inbound TCP 8000 outside the server. Set `ITSM_FORWARDED_ALLOW_IPS` to only the reverse proxy address.

`ITSM_BIND_HOST` defaults to `127.0.0.1`; the production checker rejects wildcard binding. Endpoint computers connect only to `ITSM_PUBLIC_URL` over HTTPS. Create internal DNS records for both names. The pilot Caddyfile uses Caddy's internal certificate authority, so distribute its root certificate to managed Windows computers through Group Policy before testing. Replace `tls internal` with your organization-issued certificate configuration before go-live if required by policy.

## Packaged Windows Server installation

Use `installer\artifacts\NorthstarDesk-Server-Setup-0.4.4.exe` for the shared server. The unified installer includes Northstar Desk, AssetPilot 3.7, the endpoint-agent download, migrations, signed offline update history, the verified Caddy HTTPS proxy, configurable service ports, and supervised automatic-start tasks. Install PostgreSQL first, including its command-line tools. During setup enter a PostgreSQL administrator account once; setup creates or repairs the dedicated `itsm_service` role, generates its random password, creates the `northstar_desk` database, initializes Northstar and AssetPilot, and discards the administrator password. The generated application credentials are protected so only Administrators and SYSTEM can read them.

Northstar and AssetPilot now use the same PostgreSQL database with separate schemas. Northstar owns its normal application schema and AssetPilot owns the `assetpilot` schema. AssetPilot no longer uses a server-side SQLite file in production. This removes the SQLite concurrency limitation and gives both applications the same PostgreSQL backup and recovery boundary. The local evaluation build continues to support SQLite.

Setup prompts for both DNS names, writes the protected configuration, and generates `C:\ProgramData\NorthstarDesk\Caddyfile`. Caddy (or IIS with ARR) remains the HTTPS infrastructure prerequisite. AssetPilot binds to `127.0.0.1:5080`, Northstar Desk binds to `127.0.0.1:8000`, and only the HTTPS reverse proxy should accept network traffic.

Outbound email is disabled by default in the generated production configuration so pilot tickets do not contact real users. Enable it from administration only after mail routing and notification templates have passed acceptance testing.

The installer preserves `C:\ProgramData\NorthstarDesk` during application upgrades and uninstall. PostgreSQL data is managed by PostgreSQL rather than the application uninstall process. Back up both schemas before every upgrade.

Do not embed the live AssetPilot database in the installer because it contains employee and asset information. For the first server test, either import the approved AssetPilot employee and asset workbooks into the new AssetPilot installation or perform a separately controlled migration of the existing SQLite database. Keep the original database read-only until record counts and sample assignments have been verified in PostgreSQL.

## Deploy endpoint inventory

After HTTPS and PostgreSQL are working, build the standalone enterprise package with `endpoint_agent\scripts\build-enterprise-package.ps1`. Generate an enterprise deployment token in the Assets page and distribute the package with Intune, Group Policy, or an RMM in System context. The installer registers an at-startup SYSTEM task and supports silent install, repair, upgrade, and uninstall. See `endpoint_agent\README.md` for commands and detection rules.

Unknown, ambiguous, or conflicting user observations are visible through `/api/agent-admin/assignment-review` and the Endpoint Agents panel. They are never silently assigned. Populate employee email, directory object ID, employee ID, or Windows account name to enable deterministic matching.

## Automatic startup

From an elevated PowerShell session, install the startup task under the dedicated service account:

```powershell
scripts\install-startup-task.ps1 -AtStartup
```

The task starts the API and background worker together, creates a verified pre-migration backup, applies safe Alembic migrations, and refuses to launch if production checks fail. For a local workstation test, omit `-AtStartup` to install an at-logon task for the current user.

## Backup and recovery

Run `scripts/backup.cmd` from Task Scheduler on a daily schedule under the same service account. The command uses `pg_dump` custom format, writes a SHA-256 checksum, and verifies the dump with `pg_restore --list`. Copy backups off the application server and apply an organizational retention policy.

Test recovery in a separate PostgreSQL database at least quarterly. The restore command is intentionally explicit and must be run only while the application is stopped:

```powershell
scripts\restore.ps1 -BackupPath "D:\NorthstarDesk\backups\itsm-TIMESTAMP.dump" -Confirm
```

## Move a broken server to new hardware

If the old Northstar Desk service will not start but `C:\ProgramData\NorthstarDesk` is still readable, create a migration package from the old server instead of re-entering configuration by hand. The package includes the protected `.env`, optional Caddyfile, and a verified Northstar database backup.

On the old server, first copy the existing ProgramData folder to safe storage. Then run one of these from the installed application folder:

```powershell
export-migration.cmd "D:\Transfer\NorthstarDesk-Migration.zip"
```

If the old database cannot be contacted but you already have a valid backup, point the export at that backup:

```powershell
export-migration.cmd "D:\Transfer\NorthstarDesk-Migration.zip" "D:\NorthstarDesk\backups\itsm-20260827-120000Z.dump"
```

On the new server, install PostgreSQL, run the Northstar Desk Server installer, and configure the new server's DNS, ports, database host, and backup directory. Stop the `Northstar Desk` and `Northstar HTTPS` scheduled tasks, copy the migration package locally, and run:

```powershell
import-migration.cmd "D:\Transfer\NorthstarDesk-Migration.zip"
```

The import restores tickets and database-backed configuration, then merges the old `.env` without replacing the new server's database URL, local paths, ports, public URL, trusted hosts, or update staging directory. This prevents the new installation from accidentally reconnecting to the old database. The package contains secrets and ticket data; transfer it securely and delete temporary copies after the new server is verified.

Windows Credential Manager secrets are machine/account-specific and are not included in the package. Re-enter mailbox, SMTP, or other Credential Manager-backed passwords on the new server if those integrations fail readiness checks.

## Go-live gate

- Production readiness check passes
- Backup and separate-database restore have both been tested
- HTTPS is valid with no browser warning
- Default test accounts are disabled or removed
- Admin, technician, manager, auditor, and end-user access is acceptance-tested
- Firewall exposes only HTTPS
- Mail and RingCentral credentials are stored under the service account
- SMTP delivery is configured and approval email success/failure is acceptance-tested
- Logs, health page, and automation failures have an assigned operational owner

Microsoft Entra SSO, RingCentral production credentials/webhooks, and production email still require organization-owned tenant registrations and cannot be completed from source code alone.

## Application updates

Production releases are distributed as signed `.nsupdate` files and installed from **Help Desk Settings → System updates**. Northstar rejects altered, unofficial, repeated, and older packages, creates a verified database backup before maintenance begins, and records version history and the initiating administrator. Establish the offline release-signing key before building the initial production installer. See [SYSTEM_UPDATES.md](SYSTEM_UPDATES.md) for the release and recovery procedure.

# Production deployment

This guide promotes the existing local Northstar Desk data to a shared Windows-hosted installation. Do not expose Uvicorn directly to technicians or the internet. Use an HTTPS reverse proxy and a DNS name.

## Required decisions and infrastructure

- A supported Windows computer or server that remains powered on
- A dedicated Windows service account with logon-as-batch permission
- PostgreSQL and the PostgreSQL command-line tools (`pg_dump` and `pg_restore`)
- A DNS name such as `helpdesk.company.example`
- An HTTPS certificate, normally managed by the reverse proxy
- A protected backup destination on a different disk or secured network location

## Prepare the application

1. Copy `deployment/production.env.example` to `.env` and replace every example value.
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

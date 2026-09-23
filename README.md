# Northstar Desk

Northstar Desk is a locally hosted, browser-based IT service management application for internal technology teams. It includes self-service, technician and approval queues, a drag-and-drop form Studio, saved custom reports, manager reporting, administration, local authentication, email intake and notifications, employees, assets, audit records, health monitoring, and an automation exception queue.

The repository also contains the standalone [Northstar Windows Endpoint Agent](endpoint_agent/README.md), which securely supplies live Windows hardware, software, security, health, and signed-in user observations to the shared Asset Inventory and ITSM asset records.

## Quick start on Windows

Prerequisites: Python 3.12+ and PowerShell 5.1+. Node.js 20+ is needed only to rebuild the React interface; the prepared local workspace includes a production build.

1. Run `scripts\install.ps1` once during initial setup.
2. After installation, double-click `Start ITSM.cmd` whenever you want to start the app.
3. The launcher automatically applies safe database updates before starting.
4. Open <http://127.0.0.1:8000>.

The development installer creates a virtual environment, installs pinned Python dependencies, builds the React interface, applies Alembic migrations, and loads demo data.

For a shared Windows server, use `installer\artifacts\NorthstarDesk-Server-Setup-0.4.5.exe`. Install PostgreSQL first; the server wizard provisions the application role and database, configures the services, applies migrations, disables outbound email for pilot testing, and installs the automatic-start tasks. AssetPilot is optional and does not control ITSM login, ticketing, email intake, or startup readiness. See the production deployment guide before placing the server on the network.

## Test accounts

All seeded accounts use the temporary password `ChangeMe!2026` and are required to change it after first login.

| Role | Username |
|---|---|
| System Administrator | `admin` |
| IT Manager | `manager` |
| Technicians | `tech1`, `tech2`, `tech3` |
| Team Lead | `lead` |
| End Users | `user1` through `user5` |
| Auditor / Reporting Viewer | `auditor` |

These are test-only identities using the reserved `.test` domain. Replace or disable them before any production use.

## Useful scripts

- Use the `.cmd` launchers when PowerShell execution policy blocks direct `.ps1` commands.
- `scripts\install.cmd`: install dependencies, build the interface, migrate, and seed.
- `scripts\init-db.ps1`: apply migrations and seed an empty database.
- `scripts\build.cmd`: reproducibly build the interface and run automated tests.
- `scripts\backup.cmd`: create and verify a safe SQLite or PostgreSQL backup.
- `scripts\production-check.cmd`: reject unsafe or incomplete production configuration.
- `scripts\migrate-to-postgres.ps1`: securely prompt for PostgreSQL credentials, then back up and transfer the local SQLite database to an empty PostgreSQL database.
- `scripts\reset-demo.ps1 -Confirm`: destructively recreate demo data.
- `scripts\configure-mail-secret.ps1 -Username support@example.org`: store the IMAP secret in Windows Credential Manager.
- `scripts\configure-smtp-secret.ps1 -Username support@example.org`: store the outbound email secret used by approvals and notifications.
- `scripts\start-dev.ps1`: run backend and frontend development servers.

See [docs/STUDIO_GUIDE.md](docs/STUDIO_GUIDE.md), [docs/PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md), [docs/SYSTEM_UPDATES.md](docs/SYSTEM_UPDATES.md), [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md), [docs/ACCEPTANCE_CHECKLIST.md](docs/ACCEPTANCE_CHECKLIST.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for operating guidance.

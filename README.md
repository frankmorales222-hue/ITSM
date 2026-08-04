# Northstar Desk

Northstar Desk is a locally hosted, browser-based IT service management application for internal technology teams. This first operational version includes self-service, technician queues, manager reporting, administration, local authentication, IMAP email intake, notifications, employees, assets, audit records, health monitoring, and an automation exception queue.

## Quick start on Windows

Prerequisites: Python 3.12+, Node.js 20+, and PowerShell 5.1+.

1. Open PowerShell in this folder.
2. Run `Set-ExecutionPolicy -Scope Process Bypass` if local script execution is restricted.
3. Run `scripts\install.ps1`.
4. Run `scripts\start.ps1`.
5. Open <http://127.0.0.1:8000>.

The installer creates a virtual environment, installs pinned Python dependencies, builds the React interface, applies Alembic migrations, and loads demo data. PostgreSQL is recommended for team deployment; set `ITSM_DATABASE_URL` in `.env` before initialization.

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

- `scripts\init-db.ps1`: apply migrations and seed an empty database.
- `scripts\build.ps1`: build the interface and run automated tests.
- `scripts\reset-demo.ps1 -Confirm`: destructively recreate demo data.
- `scripts\configure-mail-secret.ps1 -Username support@example.org`: store the IMAP secret in Windows Credential Manager.
- `scripts\start-dev.ps1`: run backend and frontend development servers.

See [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md), [docs/ACCEPTANCE_CHECKLIST.md](docs/ACCEPTANCE_CHECKLIST.md), and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for operating guidance.


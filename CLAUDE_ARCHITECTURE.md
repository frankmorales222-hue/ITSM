# Northstar Desk / ITSM — Claude Engineering Handoff

Generated from the repository on 2026-09-16. This is a documentation-only handoff; it does not change application code. Do not copy credentials from local environment files into tickets, prompts, commits, or support bundles.

## 1. Repository map

### Source and runtime areas

| Path | Purpose | Source or generated |
|---|---|---|
| `backend/itsm/` | FastAPI application, domain services, security, integrations, models, migrations glue | Source |
| `backend/itsm/main.py` | Application creation and route registration; primary API entry point | Source |
| `backend/itsm/models.py` | SQLAlchemy ORM model/table definitions | Source of truth for mapped schema |
| `backend/itsm/schemas.py` | Pydantic request/response contracts | Source |
| `backend/itsm/services.py`, `admin_services.py`, `database_ops.py` | Business logic and persistence operations | Source |
| `backend/itsm/security.py`, `identity.py`, `microsoft_sso.py`, `oauth_state.py` | Local auth, Microsoft identity, OAuth state and authorization checks | Source |
| `backend/itsm/microsoft_mail.py`, `ringcentral.py`, `teams_support.py` | Email/Graph, RingCentral, and Teams support integrations | Source |
| `backend/itsm/agent_api.py`, `assetpilot.py`, `assetpilot_runtime.py` | Endpoint/AssetPilot enrollment and inventory integration | Source |
| `backend/itsm/system_updates.py`, `update_api.py`, `certificate_api.py` | Signed offline updates and HTTPS certificate administration | Source |
| `migrations/versions/` | Alembic schema history (`0001` through `0023`) | Source/migration history |
| `frontend/src/` | React/Vite interface and CSS | Source |
| `frontend/dist/` | Built browser assets copied into production package | Generated |
| `endpoint_agent/` | Standalone Windows endpoint agent, tray companion, installer metadata | Source/package input |
| `installer/` | Inno Setup definitions, release/build scripts, migration import/export helpers | Source/build tooling |
| `deployment/` | Caddy and production environment examples | Deployment templates |
| `scripts/` | Install, run, backup, restore, migration, diagnostics, and build entry points | Operational tooling |
| `docs/` | Operational, security, admin, technician, end-user, update, and acceptance guides | Documentation |
| `artifacts/` | Built installers/packages and release artifacts | Generated/distributable |
| `certificates/` | Local/test certificate material; treat as sensitive | Environment-specific |
| `recovery/`, `logs/`, `data/` | Backups, diagnostics, and local runtime data | Runtime/generated |
| `.venv/`, `frontend/node_modules/`, `.pytest-*`, `.pytest_cache/`, `pytest-cache-files-*`, `_agent_e2e_tmp/`, `.scratch/`, `.test-temp-*` | Virtual environment, dependency cache, and test scratch data | Generated; never ship |

Other root files include `.env` (local secrets; never disclose), `.env.example`, `alembic.ini`, `requirements.txt`, `pyproject.toml`, `README.md`, `Start ITSM.cmd`, `Start Local Test.cmd`, `Enable Network Test.cmd`, and `Restore Local Only.cmd`.

## 2. Technology stack

### Backend/runtime

- Python 3.12+ and PowerShell 5.1+ on Windows. Node.js 20+ is required only when rebuilding the React interface; a prepared build is included.
- FastAPI `0.116.1`, Uvicorn `0.35.0`, SQLAlchemy `2.0.43`, Alembic `1.16.4`, Pydantic Settings `2.10.1`.
- PostgreSQL driver `psycopg[binary] 3.3.4`; SQLite is used for local/test mode.
- Argon2-CFFI `25.1.0`, `cryptography 45.0.6`, `PyJWT[crypto] 2.10.1`, `keyring 25.6.0`, `python-multipart 0.0.20`, `email-validator 2.2.0`.
- Tests: pytest `8.4.1`, pytest-cov `6.2.1`, httpx `0.28.1`, websockets `17.0.1`.

### Frontend

React `19.2.8`, React DOM `19.2.8`, TypeScript `7.0.2`, Vite `8.2.0`, `@vitejs/plugin-react 6.0.5`; package metadata is in `frontend/package.json` and the lockfile is `frontend/pnpm-lock.yaml`.

### Runtime topology

Browser → FastAPI/Uvicorn (`backend/itsm/main.py`) → SQLAlchemy/Alembic → PostgreSQL (production) or SQLite (local/test). A background worker handles scheduled jobs, email intake/outbound delivery, automation, and health checks. Optional external integrations are Microsoft Entra ID/Graph, RingCentral, Microsoft Teams, and AssetPilot/endpoint agents. Caddy or another TLS terminator can front the app.

## 3. Database schema

The authoritative field definitions, SQL types, constraints, indexes, and ORM relationships are in `backend/itsm/models.py`; migration DDL and upgrade behavior are in `migrations/versions/`. To extract every field without guessing:

```powershell
rg -n "^class |mapped_column|ForeignKey|relationship|Index\(" backend/itsm/models.py
```

Current table/model inventory:

`organizations`, `departments`, `locations`, `teams`, `team_memberships`, `support_queues`, `queue_team_eligibility`, `users`, `role_definitions`, `user_role_assignments`, `group_types`, `user_groups`, `user_group_memberships`, `service_categories`, `employees`, `assets`, `asset_history`, `agent_enrollment_tokens`, `endpoint_agents`, `endpoint_actions`, `asset_inventory_snapshots`, `sequences`, `tickets`, `ticket_assets`, `ticket_attachments`, `ticket_chat_sessions`, `ticket_messages`, `ticket_history`, `sessions`, `password_reset_tokens`, `audit_events`, `email_messages`, `notifications`, `automation_failures`, `announcements`, `knowledge_articles`, `knowledge_article_versions`, `self_service_attempts`, `feedback`, `system_state`, `config_items`, `routing_rules`, `routing_rule_versions`, `notification_rules`, `event_catalog`, `domain_events`, `integration_connections`, `integration_logs`, `telephony_calls`, `integration_secrets`, `form_definitions`, `form_definition_versions`, `approval_workflows`, `task_templates`, `ticket_checklists`, `approval_requests`, `approval_decisions`, `report_definitions`, and `system_updates`.

Important relationship domains: organization/tenant ownership; users, employees, teams, groups, roles and memberships; queues and eligible teams; tickets, requester/assignee/team/queue, messages, history, attachments, chats, assets and endpoint actions; integrations and logs/secrets; forms and versions; approvals/tasks/checklists; reports; system update records. Do not hand-edit production tables—use a new Alembic migration and test upgrade/rollback behavior.

Migration order currently ends at `0023_smart_self_service.py`:

`0001_initial`, `0002_config_items`, `0003_assetpilot_inventory`, `0004_organizations_integrations`, `0005_studio_approvals_reports`, `0006_remove_legacy_asset_source_index`, `0007_form_templates_and_test_form`, `0008_requester_snapshot`, `0009_administration_foundation`, `0010_administration_control_plane`, `0011_incident_vertical_slice`, `0012_tasks_and_closure`, `0013_help_desk_experience`, `0014_password_reset_tokens`, `0015_endpoint_inventory_agents`, `0016_enterprise_agent_identity`, `0017_microsoft_sso_identity`, `0018_telephony_calls`, `0019_endpoint_enrollment_owner`, `0020_signed_system_updates`, `0021_ticket_live_chat`, `0022_endpoint_remediation`, `0023_smart_self_service`.

## 4. Backend API inventory

Routes are registered in `backend/itsm/main.py`. Request/response models are in `schemas.py`; authorization dependencies and cookie/JWT behavior are in `security.py`, `identity.py`, and the admin service layer. Invalid input normally returns Pydantic validation errors; domain/auth failures use appropriate HTTP errors. Inspect the handler for exact payload fields before implementing a client.

### Health, auth, bootstrap

`GET /api/health/live`, `GET /api/health/ready`, `POST /api/auth/login`, `GET /api/auth/microsoft/status`, `GET /api/auth/microsoft/start`, `GET /api/auth/me`, `PATCH /api/auth/profile`, `POST /api/auth/logout`, `POST /api/auth/change-password`, `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`, `GET /api/bootstrap`.

### Tickets and operations

`GET /api/tickets`, `GET /api/tickets/counts`, `POST /api/tickets`, `GET /api/tickets/{ticket_id}`, `PATCH /api/tickets/{ticket_id}`, `POST /api/tickets/{ticket_id}/reassign`, `POST /api/tickets/{ticket_id}/messages`, `POST /api/tickets/{ticket_id}/confirm`, `POST /api/tickets/{ticket_id}/reopen`, `POST /api/tickets/bulk`, `GET /api/dashboard`, `GET /api/reports/support`.

### Assets, employees, and endpoint integration

`GET /api/assets`, `GET /api/assets/summary`, `GET /api/assets/metadata`, `GET /api/assets/import/assetpilot/preview`, `POST /api/assets/import/assetpilot`, `GET /api/integrations/assetpilot/status`, `POST /api/integrations/assetpilot/create`, `POST /api/integrations/assetpilot/open/{asset_id}`, `GET /api/assets/{asset_id}`, `POST /api/assets`, `PATCH /api/assets/{asset_id}`, `POST /api/assets/{asset_id}/assign`, `GET /api/employees`, `GET /api/employees/{employee_id}`.

### Administration

Users: `GET /api/admin/users`, `POST /api/admin/users`, `POST /api/admin/users/{user_id}/reset-password`, `PATCH /api/admin/users/{user_id}`. Organization: `GET/PATCH /api/admin/organization`. Groups: `GET/POST /api/admin/groups`, `PATCH/DELETE /api/admin/groups/{item_id}`. Categories: `GET/POST /api/admin/categories`, `PATCH/DELETE /api/admin/categories/{item_id}`. Queues: `GET/POST /api/admin/queues`, `PATCH/DELETE /api/admin/queues/{item_id}`. Routing: `GET/POST /api/admin/routing-rules`, `PATCH/DELETE /api/admin/routing-rules/{item_id}`, `POST /api/admin/routing-rules/test`. Notifications: `GET/POST /api/admin/notification-rules`, `PATCH/DELETE /api/admin/notification-rules/{item_id}`. Integrations: `GET/POST /api/admin/integrations`, `PATCH /api/admin/integrations/{item_id}`, `POST /api/admin/integrations/{item_id}/test`, `GET /api/admin/integrations/{item_id}/logs`, and RingCentral secret GET/PATCH routes. Settings: `GET /api/admin/settings/{section}`, `PATCH /api/admin/settings/{item_id}`. Audit/health/failures: `GET /api/audit`, `GET /api/admin/failures`, `POST /api/admin/failures/{failure_id}/resolve`, `GET /api/admin/health`. Feedback: `POST /api/feedback`.

### Forms, approvals, reports, email, notifications

Forms: `GET /api/forms`, admin CRUD/copy/unarchive/version/restore routes under `/api/admin/forms`, and `POST /api/forms/{form_id}/submit`. Approvals/tasks: `GET /api/admin/approval-workflows`, `POST/PATCH /api/admin/approval-workflows`, task-template CRUD, checklist patch, `GET /api/approvals`, `POST /api/approvals/{approval_id}/decision`. Reports: `GET /api/reports/definitions`, admin report-definition CRUD, `GET /api/reports/{report_id}/run`, `GET /api/reports/{report_id}/csv`, and `GET /api/reports/tickets.csv`. Email intake is `POST /api/email/ingest`; in-app notifications are `GET /api/notifications`.

## 5. Frontend

Entry points are `frontend/src/main.tsx` and `App.tsx`. Major screens/components include `AdministrationConsole.tsx`, `AdministrationHub.tsx`, `AssetInventory.tsx`, `DeviceIntelligence.tsx`, `EndpointActions.tsx`, and `Studio.tsx`. API access is centralized in `frontend/src/api.ts`; hash-based navigation is coordinated by `App.tsx`. CSS is split by feature: `styles.css`, `helpdesk-redesign.css`, `administration-console.css`, `administration-hub.css`, `asset-inventory.css`, `device-intelligence.css`, `endpoint-actions.css`, `ticket-attachments.css`, `ticket-live-chat.css`, `ticket-reassignment.css`, `smart-self-service.css`, `professional-service-form.css`, `incident-form.css`, `routing.css`, `settings.css`, and related Studio/organization/operations/agent files. `infinx-theme.css` is an optional theme layer. Run `npm/pnpm build` from `frontend/` only when intentionally rebuilding browser assets.

## 6. Updates, versioning, and rollback

The administrator uploads a signed `.nsupdate` package through the System Updates page. The server verifies the trust key, rejects downgrades and reused package IDs, creates a verified pre-upgrade backup, stages the package in the directory configured by `ITSM_UPDATE_STAGING_DIRECTORY` (example: `C:/ProgramData/NorthstarDesk/updates`), records installation history, and restarts the managed services/task when complete. The update controller is implemented in `system_updates.py`/`update_api.py`; packaging is in `installer/update-package.py` and related `build-*.ps1` scripts. Keep the private signing key off the server. Failed updates must preserve the verified backup; inspect the recorded installation log before retrying.

Production configuration and data live outside the source tree (commonly `C:\ProgramData\NorthstarDesk` plus PostgreSQL). Preserve `.env`, certificates, database credentials, HTTPS configuration, and backups during upgrades. Use the documented backup/restore tools rather than copying a live database directory.

## 7. Build and deployment

Relevant installer/build artifacts include `installer/NorthstarDesk.iss`, `installer/NorthstarDeskServer.iss`, `installer/NorthstarDeskAgentRefresh.iss`, `installer/NorthstarDeskTheme.iss`, `installer/NorthstarDeskTicketAgent.iss`, `installer/NorthstarDeskIdentityTheme.iss`, `installer/NorthstarDeskIdentitySafety.iss`, `installer/NorthstarDeskRemoteAgentPublishing.iss`, `installer/NorthstarDeskUpdateController.iss`, `installer/NorthstarDeskUpdaterRepair.iss`, `installer/build-installer.ps1`, `installer/build-server-bundle.ps1`, and `installer/update-package.py`. The server executable entry point is `installer/server_entry.py`; the endpoint package entry points are `endpoint_agent/enterprise_entry.py` and `endpoint_agent/tray_entry.py`.

Operational scripts include `scripts/install.ps1`, `scripts/install.cmd`, `scripts/init-db.ps1`, `scripts/start.ps1`, `scripts/start.cmd`, `scripts/start-production.ps1`, `scripts/start-production.cmd`, `scripts/backup.ps1`, `scripts/restore.ps1`, `scripts/migrate-to-postgres.ps1`, `scripts/production-check.ps1`, and startup-task installers/removers. Deployment templates are `deployment/Caddyfile.example` and `deployment/production.env.example`.

## 8. Known limitations and risk areas

These are areas to verify, not claims that every item is currently broken: update tasks/history can remain in an installing/failed state after a service restart; endpoint enrollment/tray startup depends on correct `--server` arguments, Windows task registration, permissions, and network/TLS trust; external Graph, RingCentral, and Teams behavior depends on provider permissions and reachable endpoints; HTTPS validity depends on hostname, certificate chain, private-key match, and the active reverse proxy/service; browser hash navigation and live-chat refresh behavior have historically required regression testing; email threading requires preserving ticket identifiers and inbound mailbox polling; and database migrations must be tested against the target PostgreSQL version before production rollout. See `docs/KNOWN_LIMITATIONS.md`, `docs/TEST_RESULTS.md`, and `docs/ACCEPTANCE_CHECKLIST.md` for repository-specific evidence.

## 9. Safe examples (placeholders only)

Start locally:

```powershell
Set-Location C:\Users\<user>\Documents\ITSM
& .\scripts\start.cmd
```

PostgreSQL DSN shape (never commit a real password):

```text
postgresql+psycopg://<db_user>:<url_encoded_password>@<db_host>:5432/<db_name>
```

Endpoint enrollment uses a one-time token and server URL supplied by the admin UI; do not paste live tokens into documentation. The agent must run with its configured `--server` value and should not retain ticket/asset data locally.

## 10. Planned/requested work (backlog, not guaranteed shipped)

Requested future areas include: configurable announcement popups/toasts; password-expiry reminders and Azure self-service fallback; duplicate detection, priority/escalation and after-hours automation; satisfaction surveys, knowledge auto-linking, license expiry, and scheduled maintenance notes; robust email threading and chat/Teams support; custom drag-and-drop forms and report builder; asset-to-user correlation and inventory UX; automatic endpoint-agent updates and tray notifications; selectable consistent themes; multi-tenant deployment/reporting; and future subscription/licensing. Treat these as backlog until implemented, tested, and recorded in a release note.

## 11. Handoff rules for Claude

1. Create a branch and make a file-level change plan before coding.
2. Never expose or commit `.env`, private keys, OAuth client secrets, database passwords, certificate private keys, live tokens, or production dumps.
3. Preserve existing HTTPS, database, routing, email, agent, and update behavior unless the task explicitly targets it.
4. Reuse existing services/schemas/components; add migrations instead of mutating old migrations.
5. Run focused tests, the full test suite, frontend build, production checks, and a clean-install/upgrade/rollback smoke test before declaring a package ready.
6. Record changed files, migration IDs, configuration changes, test commands/results, package hash/version, and rollback instructions in the release notes.
7. Do not call a package “complete” until the built artifact—not only source code—contains the change and the target installation reports the expected version.

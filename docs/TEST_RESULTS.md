# Verification results

Verified on August 3, 2026 with Python 3.14.6 (the application supports Python 3.12+) and Node.js 24.14.

- React/TypeScript production build: passed; 22 modules transformed and optimized assets emitted to `frontend/dist`.
- Alembic migrations: passed from an empty database and an existing `0002_config_items` database through `0003_assetpilot_inventory`.
- Seed data: passed; 12 users, 10 employees, 25 assets, and 30 mixed-status tickets.
- Automated backend suite: 26 passed. Coverage includes login/logout, failed-login lockout, password policy, CSRF, role permissions, staff creation on behalf of a requester, ticket creation and record visibility, queue counts, least-active and round-robin assignment, unavailable-technician exclusion, public/internal/restricted messages, status transitions, priority/SLA calculation, scoped search, email deduplication and header threading, automatic-email suppression, unknown-requester exceptions, attachment metadata, native asset creation/editing/assignment/return, AssetPilot import completeness and idempotency, asset uniqueness and history, employee/asset support context, user availability updates, notifications, dashboard/reports, audit, health, exception resolution, and editable configuration.
- Worker cycle: passed with healthy heartbeat and SLA evaluation.
- HTTP smoke test: passed; `/api/health/live` returned `ok`, the built browser application returned HTTP 200, and the production shell contained Northstar Desk metadata.
- Interactive browser test: passed for staff ticket creation, requester details, queue counters and dashboard drill-down, employee support history, asset inventory details, user administration, and switching assignment rules to round robin.
- AssetPilot migration rehearsal: passed against a copy of the ITSM database; 1,165 assets, 720 employees, and 2,320 lifecycle events imported, and a second import created zero duplicates.

The FastAPI version used emits a Python 3.14 deprecation warning inside framework route inspection; this is non-failing and does not affect runtime behavior.

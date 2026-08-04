# Known limitations and next steps

- SMTP delivery adapters and editable notification templates are modeled but the first local build delivers durable in-app notifications. Add an authenticated TLS relay before production.
- Administration now supports user creation, role/availability changes, password resets, health/audit views, and active technician-assignment rules (least active, round robin, or manual). Categories, teams, SLA policies, calendars, holidays, templates, email settings, and retention still begin as seeded/configuration defaults; richer CRUD screens are a later increment.
- AssetPilot inventory is now unified into Northstar Desk with native create/edit, assignment/return, lifecycle history, and an idempotent local migration. Specialized AssetPilot shipment tracking, stock-target purchasing calculations, and spreadsheet-layout exports remain separate future ports if required.
- SLA targets use elapsed hours in this version. The schema and worker boundary support a business-calendar calculator, but holiday-aware pause/resume accounting is not yet complete.
- Merge/link workflows, custom saved views, customer satisfaction, and configurable report dimensions are not complete in the first version.
- External requesters are sent to the exception queue rather than automatically created by default.
- Restricted tickets use role and team rules rather than arbitrary access-control lists.
- Attachments are metadata-only by design; no file content is retained.
- SQLite supports evaluation only. Use PostgreSQL for concurrent team use.
- Microsoft Entra ID, Microsoft Graph, advanced automation, endpoint control, full CMDB, change/problem management, procurement, and clinical workflows are intentionally excluded.

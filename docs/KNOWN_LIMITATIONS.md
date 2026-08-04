# Known limitations and next steps

- SMTP delivery adapters and editable notification templates are modeled but the first local build delivers durable in-app notifications. Add an authenticated TLS relay before production.
- Administration exposes the most operationally important pages. Categories, teams, assignment rules, SLA policies, calendars, holidays, templates, email settings, and retention begin as seeded/configuration defaults; richer CRUD screens are the next increment.
- SLA targets use elapsed hours in this version. The schema and worker boundary support a business-calendar calculator, but holiday-aware pause/resume accounting is not yet complete.
- Merge/link workflows, custom saved views, customer satisfaction, and configurable report dimensions are not complete in the first version.
- External requesters are sent to the exception queue rather than automatically created by default.
- Restricted tickets use role and team rules rather than arbitrary access-control lists.
- Attachments are metadata-only by design; no file content is retained.
- SQLite supports evaluation only. Use PostgreSQL for concurrent team use.
- Microsoft Entra ID, Microsoft Graph, advanced automation, endpoint control, full CMDB, change/problem management, procurement, and clinical workflows are intentionally excluded.

# Administrator guide

Use the Administration area to review service health, automation failures, local accounts, and append-only audit activity. Dashboard and report numbers always query current records.

## Database and backup

SQLite is for local evaluation. For team use, create a PostgreSQL database and least-privilege account, set `ITSM_DATABASE_URL`, run `scripts\init-db.ps1`, and schedule PostgreSQL-native encrypted backups. Confirm restoration regularly. The health page intentionally shows backup as not configured until operational monitoring is integrated.

## Mailbox intake

Set `ITSM_IMAP_HOST`, `ITSM_IMAP_PORT`, and `ITSM_IMAP_USERNAME` in `.env`. Store the password with `scripts\configure-mail-secret.ps1 -Username <mailbox>`. The worker uses TLS IMAP, deduplicates by Message-ID, threads via In-Reply-To and References, ignores common automatic replies and bounces, removes quoted history when practical, and stores only attachment metadata. Unknown requesters create a visible exception for review.

## Accounts

Administrators can create local users and reset passwords through the API; temporary passwords must meet policy and force a change. Disable or replace seed users before production. Availability controls automatic assignment: only Available technicians are eligible.

## Recovery

Every failure includes a correlation ID or safe identifier. Review the automation exception queue, correct the underlying configuration, then resolve the event with a note. Secrets and tokens are filtered from safe details. Audit records cannot be edited through the application.


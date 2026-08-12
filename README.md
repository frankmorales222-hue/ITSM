# IT Support — Phase 1

Web-submitted ticket → round-robin assignment → employee "My Requests" view
→ public replies + status changes → technician queue, plus internal notes
and attachments. Session auth gates all of it.

## What's here

- `migrations/001_init.sql`, `migrations/002_add_password.sql` — Postgres
  schema (seed categories + a default team) plus `users.password_hash`
- `src/lib/db.ts` — Postgres connection pool
- `src/lib/assignment.ts` — round-robin assignment logic
- `src/lib/priority.ts` — impact × urgency → priority calculation
- `src/lib/tickets.ts` — ticket creation, reply/status updates, internal
  notes; shared by the web routes and the email intake webhook
- `src/lib/attachments.ts` — local-disk attachment storage (see
  [Attachments](#attachments) below)
- `src/lib/session.ts`, `src/lib/auth.ts` — signed session cookie +
  helpers for reading it in Server Components/Actions and Route Handlers
- `src/lib/password.ts` — scrypt password hashing (no external dependency)
- `src/lib/rate-limit.ts` — in-memory rate limiter for `/login`
- `src/app/login/page.tsx`, `src/app/api/auth/logout/route.ts` — auth
- `src/app/api/tickets/route.ts` — create ticket (assigns automatically) +
  list tickets, scoped to the session user
- `src/app/api/tickets/[id]/route.ts` — get ticket + conversation, post a
  reply, change status; restricted to the ticket's requester/assigned tech
- `src/app/api/attachments/[id]/route.ts` — download an attachment
- `src/app/api/email/inbound/route.ts` — email intake webhook (see below)
- `src/app/tickets/page.tsx` — "My Requests" list, with status filter +
  pagination
- `src/app/tickets/new/page.tsx` — "Report a problem" form
- `src/app/tickets/[id]/page.tsx` — ticket detail: conversation, reply +
  status change, attachments, and internal notes (technician-only)
- `src/app/technician/page.tsx` — technician queue, grouped/counted by
  status, with filter + pagination
- `src/app/globals.css` — the one stylesheet everything uses

## What's deliberately NOT here yet

- SSO/real identity provider — login is email + password (scrypt-hashed),
  which is a real improvement over trusting a raw `userId` param, but it's
  still not what should sit in front of real employee data long-term
- A caller for the email intake webhook — see [Email intake](#email-intake)
- MinIO/S3 for attachments — currently local disk under `./uploads`, fine
  for one dev machine, not for anything deployed
- A shared store for rate limiting / sessions — both are in-memory,
  single-process only; fine for phase 1, not for multiple instances

## Setup

```bash
npm install
cp .env.example .env       # fill in DATABASE_URL, SESSION_SECRET, EMAIL_WEBHOOK_SECRET
npm run migrate            # runs migrations/001_init.sql and 002_add_password.sql
npm run dev
```

You'll need at least one row in `users` (with a `password_hash` — see
`src/lib/password.ts`) and `team_members` (linked to the seeded "IT
Support" team) before login and ticket assignment do anything meaningful.
There's no seed data for people, intentionally, since that should come
from your actual directory later.

## Email intake

`POST /api/email/inbound` is the entry point — see the comment at the top
of `src/app/api/email/inbound/route.ts` for the exact behavior (threading
via `In-Reply-To`, dedup via `inbound_email_log.message_id`, no ticket
created for a sender that doesn't match an existing user). It requires an
`x-webhook-secret` header matching `EMAIL_WEBHOOK_SECRET`.

Nothing calls it yet. There's no mailbox, IMAP/SMTP credentials, or mail
provider configured in this environment, so there's nothing to poll or
subscribe to — building a poller against credentials that don't exist
would be code nobody could verify actually works. Two ways to wire it up
once there's a real mailbox:

1. **Provider webhook** — if the inbox is behind something like Mailgun,
   Postmark, or SendGrid's inbound parse, point its webhook at this route
   directly (mapping their payload shape to `{ messageId, inReplyTo, from,
   subject, body }`).
2. **Scheduled poller** — a small job (e.g. IMAP via `imapflow`) that runs
   on a schedule, reads new messages, and POSTs each one here.

## Full reference

See `it-support-phase1-data-model.md` from earlier in this conversation for
the complete schema rationale and what's deferred to phase 2+.

# IT Support — Phase 1

Web-submitted ticket → round-robin assignment → employee "My Requests" view
→ public replies + status changes → technician queue, plus internal notes
and attachments. Session auth gates all of it.

## What's here

- `migrations/001_init.sql`, `002_add_password.sql`,
  `003_add_password_setup_token.sql` — Postgres schema (seed categories +
  a default team) plus `users.password_hash` and the setup-token columns
- `src/lib/db.ts` — Postgres connection pool
- `src/lib/assignment.ts` — round-robin assignment logic
- `src/lib/priority.ts` — impact × urgency → priority calculation
- `src/lib/tickets.ts` — ticket creation, reply/status updates, internal
  notes; shared by the web routes and the email intake webhook
- `src/lib/attachments.ts` — S3-compatible (MinIO locally) attachment
  storage
- `src/lib/session.ts`, `src/lib/auth.ts` — signed session cookie +
  helpers for reading it in Server Components/Actions and Route Handlers
- `src/lib/password.ts` — scrypt password hashing (no external dependency)
- `src/lib/rate-limit.ts` — Redis-backed rate limiter for `/login`
- `src/lib/password-setup.ts` — one-time technician-issued password setup
  tokens (see [Password setup](#password-setup))
- `src/app/login/page.tsx`, `src/app/api/auth/logout/route.ts` — auth
- `src/app/set-password/page.tsx` — where a setup link lands
- `src/app/technician/users/page.tsx` — technician view for generating
  setup links
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
- `docker-compose.yml` — Postgres, Redis, MinIO for local dev
- `scripts/seed-technician.ts` — bootstraps the first technician (`npm run
  seed:technician`), see [Setup](#setup)
- `Dockerfile` — multi-stage build for the app itself (Next.js standalone
  output). Built and run locally against the compose infra to confirm it
  works; nowhere to deploy it yet — see [Deployment](#deployment)
- `.github/workflows/ci.yml` — type-check, unit tests, integration tests,
  and a production build on every push/PR. Verified locally end-to-end
  with [`act`](https://github.com/nektos/act) (no GitHub remote is
  configured on this repo, so it's never run on GitHub itself) — that run
  is what caught `psql` not being on the runner image, hence the explicit
  `apt-get install postgresql-client` step

## What's deliberately NOT here yet

- SSO/real identity provider — see [SSO](#sso) below
- A caller for the email intake webhook — see [Email intake](#email-intake)
- Page-level and browser E2E tests — see [Testing](#testing)

## Setup

Needs Postgres, Redis, and MinIO — `docker-compose.yml` covers all three:

```bash
docker compose up -d
npm install
cp .env.example .env       # fill in DATABASE_URL, SESSION_SECRET, EMAIL_WEBHOOK_SECRET
npm run migrate            # runs migrations/001, 002, and 003 in order
npm run dev
```

You'll need at least one row in `users` (with a `password_hash` — see
`src/lib/password.ts`) and `team_members` before login and ticket
assignment do anything meaningful. There's no seed data for people,
intentionally, since that should come from your actual directory later —
except the very first technician, who has to come from somewhere:

```bash
npm run seed:technician -- --email=you@example.com --name="Your Name"
```

Creates (or updates) an active technician on the "IT Support" team,
printing a generated password if you don't pass `--password`. Every
technician after this one gets onboarded through `/technician/users`
instead (see [Password setup](#password-setup)) — this script exists
because that page is technician-only, so the first one can't come from
there.

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

## Password setup

A user's first password isn't self-requested — `/technician/users` lists
every active user without a `password_hash` and lets a technician generate
a one-time link (`/set-password?token=...`, 24h expiry, single-use) to send
them directly.

This is deliberate, not a shortcut: a "forgot password" form that emails a
reset link proves the requester owns that email address. There's no
outbound email in this environment (same gap as [email
intake](#email-intake)), so a self-requested link would just hand a
working credential to whoever typed the address — no verification at all.
Routing it through an already-authenticated technician instead reuses a
trust boundary that already exists (technicians can already see and act on
tickets), rather than a proof of identity via an email channel that isn't there.

The token only exists as plaintext twice: in the technician's browser for
the one page load where it's generated, and in the link they send. The
database stores its SHA-256 hash, and the handoff from the server action
that creates it to the page that displays it goes through a 60-second,
single-read Redis slot — never a URL — so it can't end up sitting in
browser history or a server access log.

## SSO

Not implemented, and not scaffolded either — here's why. Real SSO (SAML or
OIDC) needs a real identity provider tenant (Okta, Azure AD, Google
Workspace) with a registered client ID/secret and redirect URI, none of
which exist in this dev environment. A library like Auth.js could be
wired up against a generic OIDC config read from env vars, but until
there's a real IdP to redirect to and back from, that integration can't
actually be exercised — it would be code nobody could verify works, same
problem as the email poller below.

The current design keeps this a contained swap when a real IdP shows up:
credential verification is centralized in `login()` inside
`src/app/login/page.tsx`, and session issuance/verification
(`src/lib/session.ts`, `src/lib/auth.ts`) doesn't care how identity was
established. Replacing SSO means replacing that one function with an
OIDC callback handler; nothing downstream changes.

## Testing

```bash
npm test               # unit — pure logic, no infra needed
npm run test:integration   # integration — needs Postgres + a migrated itsm_test DB
```

Unit tests (`vitest.config.ts`) cover the pure/self-contained logic:
priority calculation, session cookie signing (including tamper and expiry
rejection), password hashing, attachment validation, and the rate limiter
(against a real Redis, not a mock — the thing worth checking is the actual
INCR+EXPIRE behavior).

Integration tests (`vitest.integration.config.ts`, `*.integration.test.ts`)
cover the DB-touching logic — ticket creation, round-robin assignment,
reply/status updates, internal notes — and the API route handlers
themselves (`src/app/api/tickets/**/*.integration.test.ts`), calling the
actual `GET`/`POST`/`PATCH` exports with real signed session cookies to
check auth-required, cross-user access denied, and client-supplied
identity fields (`requesterId`, `authorId`) being ignored in favor of the
session. All against a real, separate database so it never touches dev
data:

```bash
createdb itsm_test              # once, if it doesn't exist yet
TEST_DATABASE_URL=postgresql://postgres:dev@localhost:5432/itsm_test npm run migrate:test
npm run test:integration
```

Each test truncates and reseeds the tables it needs
(`src/lib/test-fixtures.ts`) rather than relying on leftover state, so
they can run in any order.

Not covered yet: the pages themselves (Server Component rendering, the
`redirect()`-to-`/login` behavior, form submission through actual HTML) —
that needs a browser driving the real app (e.g. Playwright), which isn't
set up. The route handlers you'd hit *through* those pages are covered;
the React layer rendering the forms that call them isn't.

## Deployment

`Dockerfile` builds the app (Next.js `output: "standalone"`, see
`next.config.mjs`) into a small runtime image. Verified locally:

```bash
docker build -t itsm-app .
docker run -p 3001:3000 \
  -e DATABASE_URL=postgresql://postgres:dev@host.docker.internal:5432/itsm \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  -e S3_ENDPOINT=http://host.docker.internal:9000 \
  -e S3_BUCKET=itsm-attachments -e S3_ACCESS_KEY=minioadmin -e S3_SECRET_KEY=minioadmin \
  -e SESSION_SECRET=... -e EMAIL_WEBHOOK_SECRET=... \
  itsm-app
```

(`host.docker.internal` because the compose services publish to the host,
not a shared Docker network with the app container — `docker-compose.yml`
intentionally only runs the infra, not the app itself, since the app is
what you're actively developing and hot-reload via `npm run dev` on the
host is what this project actually uses day to day.)

That's as far as this goes. There's no hosting target — no Vercel
project, no cloud account, no CI deploy step — because none is
configured in this environment, and standing one up means a real
decision (which provider, which region, how secrets get there) that
isn't mine to make.

## Full reference

See `it-support-phase1-data-model.md` from earlier in this conversation for
the complete schema rationale and what's deferred to phase 2+.

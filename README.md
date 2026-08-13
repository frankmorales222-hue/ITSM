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
- `src/lib/admin-settings.ts` — encrypted integration config storage (see
  [Admin settings](#admin-settings))
- `src/lib/oidc.ts`, `src/app/api/auth/azure-ad/` — Azure AD OIDC login
  (see [SSO](#sso))
- `src/app/login/page.tsx`, `src/app/api/auth/logout/route.ts` — auth
- `src/app/set-password/page.tsx` — where a setup link lands
- `src/app/technician/users/page.tsx` — technician view for generating
  setup links
- `src/app/admin/page.tsx` — technician view for Azure AD/IMAP config
- `src/app/api/tickets/route.ts` — create ticket (assigns automatically) +
  list tickets, scoped to the session user
- `src/app/api/tickets/[id]/route.ts` — get ticket + conversation, post a
  reply, change status; restricted to the ticket's requester/assigned tech
- `src/app/api/attachments/[id]/route.ts` — download an attachment
- `src/app/api/email/inbound/route.ts` — email intake webhook,
  `scripts/poll-inbox.ts` — its IMAP caller (see
  [Email intake](#email-intake))
- `src/app/tickets/page.tsx` — "My Requests" list, with status filter +
  pagination
- `src/app/tickets/new/page.tsx` — "Report a problem" form
- `src/app/tickets/[id]/page.tsx` — ticket detail: conversation, reply +
  status change, attachments, and internal notes (technician-only)
- `src/app/technician/page.tsx` — technician queue, grouped/counted by
  status, with filter + pagination
- `src/lib/kb.ts`, `src/app/kb/` — minimal self-service knowledge base:
  technician-authored articles (draft/published), searchable by everyone,
  linked from the shared nav
- `src/lib/approval.ts` — manager approval for Access Request/Equipment
  Request tickets (uses the existing `users.manager_id`); blocks
  resolving/closing a ticket while approval is pending, wired into
  `src/app/tickets/[id]/page.tsx`
- `src/app/globals.css` — the one stylesheet everything uses
- `docker-compose.yml` — Postgres, Redis, MinIO for local dev
- `scripts/seed-technician.ts` — bootstraps the first technician (`npm run
  seed:technician`), see [Setup](#setup)
- `playwright.config.ts`, `e2e/` — browser E2E tests, see [Testing](#testing)
- `Dockerfile` — multi-stage build for the app itself (Next.js standalone
  output). Built and run locally against the compose infra to confirm it
  works; nowhere to deploy it yet — see [Deployment](#deployment)
- `.github/workflows/ci.yml` — type-check, unit tests, integration tests,
  E2E tests, and a production build on every push/PR. Verified locally
  end-to-end with [`act`](https://github.com/nektos/act) (no GitHub
  remote is configured on this repo, so it's never run on GitHub itself)
  — that run is what caught `psql` not being on the runner image, hence
  the explicit `apt-get install postgresql-client` step

## What's deliberately NOT here yet

- Email intake tested against a real inbox, and SSO tested against a real
  Azure AD tenant — both were built and verified against real (local,
  temporary) stand-ins instead; see [Email intake](#email-intake) and
  [SSO](#sso) for exactly what that did and didn't prove

## Setup

Needs Postgres, Redis, and MinIO — `docker-compose.yml` covers all three:

```bash
docker compose up -d
npm install
cp .env.example .env       # fill in DATABASE_URL, SESSION_SECRET, EMAIL_WEBHOOK_SECRET
npm run migrate            # runs migrations/001 through 008 in order
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

`scripts/poll-inbox.ts` (`npm run poll:email`) is the caller: connects via
IMAP (`imapflow`) using the mailbox configured through
[`/admin`](#admin-settings), parses unseen messages (`mailparser`), POSTs
each to the webhook above, and flags them `\Seen` regardless of outcome —
a message the webhook rejects (unknown sender, duplicate) won't succeed on
a later poll either, so leaving it unread would just retry it forever.
Meant to run on a schedule (cron, Task Scheduler); it's a script rather
than a background process because Next.js doesn't have a
long-running-worker story and a poller doesn't need one.

There's no real inbox in this environment, so this was verified against a
real (local, temporary) IMAP/SMTP server (`greenmail/standalone`, not part
of the checked-in setup): sent an email, ran the poller, confirmed a
ticket was created with the right subject/body; sent a reply with a
matching `In-Reply-To`, ran the poller again, confirmed it threaded onto
the same ticket instead of creating a second one; confirmed a second poll
with nothing new does nothing (the first message's `\Seen` flag holds).

If a real inbox is instead behind a provider with inbound-parse support
(Mailgun, Postmark, SendGrid), point its webhook at `/api/email/inbound`
directly instead of running the poller — same endpoint, no poller needed.

## Notifications

`ticket_notifications` (already in the phase-1 schema) backs two channels:

- **In-app** (`src/lib/notifications.ts`): a row per event, `/notifications`
  to view them, an unread-count badge in the nav on `/tickets` and
  `/technician`. Always written, synchronously, inside the same transaction
  as the change that triggered it (ticket assigned/reassigned, a reply from
  the other party, status changed/resolved/closed) — never for a user's own
  action on their own ticket.
- **Email**: fired after that transaction commits, not inside it, so a slow
  or unreachable SMTP server can't hold a ticket-mutation transaction open.
  Configured through [`/admin`](#admin-settings) (`src/lib/mailer.ts`,
  `nodemailer`); if nothing's configured, `sendMail` returns `false` and the
  in-app notification is all that happens — no error, no retry queue, since
  phase 1 has no background worker to retry from. A `ticket_notifications`
  row with `channel = 'email'` is only written once the send actually
  succeeds, so that table doubles as a "did this go out" log.

Verified against a real (local, temporary) SMTP server (`axllent/mailpit`,
not part of the checked-in setup): configured `/admin` to point at it,
reassigned a ticket to a second technician, and confirmed the email
actually arrived in Mailpit's inbox with the right subject/recipient, and
that a `ticket_notifications` row with `channel = 'email'` and a `sent_at`
was written.

## Password setup

Two ways to get a working password, both landing on the same
`/set-password?token=...` page (24h expiry, single-use,
`src/lib/password-setup.ts`):

- **Technician-issued**, for a user's *first* password: `/technician/users`
  lists every active user without a `password_hash` and lets a technician
  generate a link to send them directly (Slack, in person, whatever's
  real). This exists because a brand-new hire has no established inbox
  trust yet, and it reuses a trust boundary that already exists
  (technicians can already see and act on tickets).
- **Self-service**, for resetting a password you already have: `/forgot-password`
  (linked from `/login`) takes an email, and — now that [outbound
  email](#notifications) is real — sends the reset link to whatever
  address is already on file for that account, never one typed fresh into
  the form. Receiving it is what proves ownership. The response is
  identical (redirects to the same "if that email is registered..." page)
  whether or not the address matches a real, active account, and whether
  or not sending actually succeeds — the point is that nothing about the
  response should let someone probe which emails have accounts. Requests
  are rate-limited per email and per IP (`src/lib/rate-limit.ts`,
  3/15min and 10/15min) since each one costs a real outbound send.
  One accepted tradeoff: the matched-account path does a token write plus
  an SMTP round trip and the no-match path doesn't, so response *timing*
  isn't perfectly constant between the two — full constant-time behavior
  wasn't worth the complexity here.

The token only exists as plaintext twice: wherever it's generated (a
technician's browser for the one page load, or the reset email), and in
the link. The database stores its SHA-256 hash, and for the
technician-issued path the handoff from the server action that creates it
to the page that displays it goes through a 60-second, single-read Redis
slot — never a URL — so it can't end up sitting in browser history or a
server access log.

Verified against a real (local, temporary) SMTP server (`axllent/mailpit`):
requested a reset for a real account, retrieved the actual email via
Mailpit's API, followed its link, set a new password, and logged in with
it — then confirmed the same link is rejected on a second use ("invalid or
expired"), and that requesting a reset for an email with no account
produces the identical response with no email sent.

## Admin settings

`/admin` (technician-only) holds integration config that used to require
editing `.env` and restarting: Azure AD, IMAP, and SMTP credentials,
entered through a form and encrypted at rest (AES-256-GCM,
`src/lib/admin-settings.ts`, key in `ADMIN_SETTINGS_ENCRYPTION_KEY`).
Secrets are write-only in the UI — once saved, the form shows only
"configured", never the value back. A "Clear" action removes a section's
settings entirely.

## SSO

Real Azure AD (Entra ID) sign-in via standard OIDC authorization code +
PKCE (`openid-client`), config entered through [`/admin`](#admin-settings)
instead of `.env` so it can be set after deploy. `/login` only shows
"Sign in with Microsoft" once it's configured.

- `src/lib/oidc.ts` — discovery + the PKCE/state/nonce handoff. Verifier
  and nonce are stashed in Redis keyed by `state` (the one value
  guaranteed to survive the round trip to Microsoft and back), single-use,
  10-minute TTL
- `src/app/api/auth/azure-ad/start/route.ts` — builds the authorization
  URL and redirects
- `src/app/api/auth/azure-ad/callback/route.ts` — exchanges the code,
  reads the `email`/`name` ID token claims, and either logs in an
  existing user or auto-provisions one. Auto-provisioning is deliberate:
  Azure AD *is* the "actual directory" earlier parts of this app deferred
  to for who exists — there's no reason to also require someone be seeded
  here first once SSO is live

There's no real Azure AD tenant in this environment, so the actual login
screen was never exercised against Microsoft. What *was* verified,
end-to-end, against a real (local, mock) spec-compliant OIDC provider
(`oidc-provider`, run temporarily, not part of the checked-in suite):
discovery, PKCE, state, nonce, the authorization code exchange, ID token
claim extraction, first-login auto-provisioning, and second-login
matching the existing user instead of duplicating it. That's every moving
part except the one thing that requires an actual Microsoft tenant —
whether Azure's real endpoints behave the way its documentation says.

`AZURE_AD_AUTHORITY_HOST` (default `https://login.microsoftonline.com`)
is overridable — needed for Azure's sovereign-cloud variants (US Gov,
China) in real deployments, and what pointed the verification above at
the local mock provider in development.

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

E2E tests (`playwright.config.ts`, `e2e/`) drive a real Chromium browser
against a real running server — the layer the two suites above can't
reach: Server Component rendering, `redirect()` behavior, actual HTML
form submission (including a real file upload via `setInputFiles`, which
worked with Playwright but wasn't possible earlier in this project's
history with a different, more limited browser-automation tool). Needs
its own database (`itsm_e2e`) and Chromium itself:

```bash
createdb itsm_e2e
TEST_DATABASE_URL=postgresql://postgres:dev@localhost:5432/itsm_e2e npm run migrate:test
npx playwright install --with-deps chromium   # once
npm run test:e2e
```

Playwright starts its own `next dev` on port 3100 against a distinct
`.next-e2e` build directory (see `next.config.mjs`) and a separate
logical Redis DB (`redis://localhost:6379/1`) — both exist specifically
so this can run at the same time as a `npm run dev` you already have open
on port 3000 without the two fighting over the same build output or
sharing (and tripping) the same login rate-limit counters.

Covers the golden path end to end: login → file a ticket → open it,
attach a file, reply, resolve it → see it in the technician queue →
log out and confirm the session is actually gone. Plus the auth edge
cases: unauthenticated redirect, invalid credentials.

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

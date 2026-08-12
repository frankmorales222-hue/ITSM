# IT Support — Phase 1 scaffold

This is a starting skeleton, not a finished app. It implements the smallest
real slice of the loop: web-submitted ticket → round-robin assignment →
employee "My Requests" view → public replies + status changes. It's meant to
be opened in Claude Code and built out from here.

## What's here

- `migrations/001_init.sql` — full phase-1 Postgres schema, with seed
  categories and a default team
- `src/lib/db.ts` — Postgres connection pool
- `src/lib/assignment.ts` — round-robin assignment logic
- `src/lib/priority.ts` — impact × urgency → priority calculation
- `src/app/api/tickets/route.ts` — create ticket (assigns automatically) +
  list tickets
- `src/app/api/tickets/[id]/route.ts` — get ticket + conversation, post a
  reply, change status
- `src/app/tickets/page.tsx` — minimal "My Requests" list page

## What's deliberately NOT here yet

- Authentication/session handling — every route currently takes a raw
  `userId`, trusted as-is. This is the first thing to fix before this
  touches real data.
- Email intake (the `inbound_email_log` table exists in the schema; the
  mail-processing worker that reads inbox → creates/threads tickets does
  not exist yet)
- Technician dashboard/queue page (only the employee list page is scaffolded)
- Internal notes UI (the `ticket_notes` table and its separation from
  `ticket_replies` is in place; there's no route/page for it yet)
- Attachments upload flow (table exists; no upload endpoint or MinIO wiring)
- Any styling beyond bare HTML

## Setup

```bash
npm install
cp .env.example .env       # fill in DATABASE_URL
npm run migrate            # runs migrations/001_init.sql against DATABASE_URL
npm run dev
```

You'll need at least one row in `users` and `team_members` (linked to the
seeded "IT Support" team) before ticket creation/assignment will do
anything meaningful — there's no seed data for people, intentionally, since
that should come from your actual directory later.

## Suggested build order from here (in Claude Code)

1. **Auth** — wire up real sessions (even something simple to start) so
   routes stop trusting a raw `userId` param. This blocks everything else
   from being safe to point at real data.
2. **New ticket form** — a page at `/tickets/new` that POSTs to
   `/api/tickets`. This is the actual "Report a problem" experience.
3. **Ticket detail page** — `/tickets/[id]` reading from the GET endpoint,
   showing the conversation and a reply box.
4. **Technician dashboard** — a queue view filtered to
   `assigned_tech_id = currentUser`, grouped/counted by status. This is the
   other dashboard from your original ask.
5. **Email intake worker** — a scheduled job or webhook that reads an inbox,
   writes to `inbound_email_log`, and either creates a new ticket or
   threads a reply into an existing one via `In-Reply-To`. This is the
   highest-complexity item — build it last, once the core loop works.

## Full reference

See `it-support-phase1-data-model.md` from earlier in this conversation for
the complete schema rationale and what's deferred to phase 2+.

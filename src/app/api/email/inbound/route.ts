import crypto from "crypto";
import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { createTicket, getDefaultTeamId } from "@/lib/tickets";

// POST /api/email/inbound
// Body: { messageId, inReplyTo, from, subject, body }
// Header: x-webhook-secret: EMAIL_WEBHOOK_SECRET
//
// Entry point for email intake. There's no real inbox wired up in this dev
// scaffold (no IMAP/SMTP credentials configured) — a scheduled job or
// provider webhook (e.g. an inbound-parse hook) is expected to call this
// route per message, per the README's suggested build order. Every message
// is logged to inbound_email_log regardless of outcome so failed/unmatched
// intake is auditable.
//
// This is server-to-server, not user-facing, so it can't use the session
// cookie — it's gated by a shared secret instead. Without that, the `from`
// field alone would let anyone create tickets or thread replies as any
// user just by claiming their email address.
//
// Threading: if inReplyTo matches a message_id we've already logged for a
// ticket, the new message is appended as a reply on that ticket. Otherwise
// a new ticket is created, provided the sender's address matches an
// existing user — phase 1 deliberately does not create users from email,
// since the directory is the source of truth for who exists.
export async function POST(req: NextRequest) {
  const expectedSecret = process.env.EMAIL_WEBHOOK_SECRET;
  const providedSecret = req.headers.get("x-webhook-secret") ?? "";
  const expectedBuf = Buffer.from(expectedSecret ?? "");
  const providedBuf = Buffer.from(providedSecret);
  const secretOk =
    !!expectedSecret &&
    expectedBuf.length === providedBuf.length &&
    crypto.timingSafeEqual(expectedBuf, providedBuf);
  if (!secretOk) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { messageId, inReplyTo, from, subject, body } = await req.json();

  if (!messageId || !from || !body) {
    return NextResponse.json(
      { error: "messageId, from, and body are required" },
      { status: 400 }
    );
  }

  const existing = await pool.query(
    `SELECT id FROM inbound_email_log WHERE message_id = $1`,
    [messageId]
  );
  if (existing.rows.length > 0) {
    return NextResponse.json({ status: "duplicate" }, { status: 200 });
  }

  let threadTicketId: string | null = null;
  if (inReplyTo) {
    const threadResult = await pool.query(
      `SELECT ticket_id FROM inbound_email_log WHERE message_id = $1 AND ticket_id IS NOT NULL`,
      [inReplyTo]
    );
    threadTicketId = threadResult.rows[0]?.ticket_id ?? null;
  }

  const userResult = await pool.query(
    `SELECT id FROM users WHERE email = $1 AND is_active = true`,
    [from]
  );
  const senderId: string | null = userResult.rows[0]?.id ?? null;

  if (threadTicketId) {
    if (senderId) {
      await pool.query(
        `INSERT INTO ticket_replies (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
        [threadTicketId, senderId, body]
      );
    }
    await pool.query(
      `INSERT INTO inbound_email_log
        (message_id, in_reply_to, from_address, ticket_id, processed_status)
       VALUES ($1, $2, $3, $4, $5)`,
      [messageId, inReplyTo ?? null, from, threadTicketId, senderId ? "processed" : "no_matching_user"]
    );
    return NextResponse.json({ status: "threaded", ticketId: threadTicketId });
  }

  if (!senderId) {
    await pool.query(
      `INSERT INTO inbound_email_log
        (message_id, in_reply_to, from_address, ticket_id, processed_status)
       VALUES ($1, $2, $3, NULL, 'no_matching_user')`,
      [messageId, inReplyTo ?? null, from]
    );
    return NextResponse.json({ status: "no_matching_user" }, { status: 202 });
  }

  const teamId = await getDefaultTeamId();
  if (!teamId) {
    return NextResponse.json({ error: "No default team configured" }, { status: 500 });
  }

  const ticket = await createTicket({
    requesterId: senderId,
    openedById: senderId,
    subject: subject || "(no subject)",
    description: body,
    submissionChannel: "email",
    teamId,
  });

  await pool.query(
    `INSERT INTO inbound_email_log
      (message_id, in_reply_to, from_address, ticket_id, processed_status)
     VALUES ($1, $2, $3, $4, 'processed')`,
    [messageId, inReplyTo ?? null, from, ticket.id]
  );

  return NextResponse.json({ status: "created", ticketId: ticket.id }, { status: 201 });
}

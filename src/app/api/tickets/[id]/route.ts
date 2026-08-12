import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { addReplyAndUpdateStatus } from "@/lib/tickets";
import { getSessionUserIdFromRequest } from "@/lib/auth";

// GET /api/tickets/:id
// Returns the ticket plus its public conversation (replies only —
// ticket_notes is deliberately never joined here so internal notes can
// never leak into an employee-facing response). Restricted to the
// ticket's requester or assigned technician — a valid session alone
// isn't enough to read someone else's ticket.
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const userId = getSessionUserIdFromRequest(req);
  if (!userId) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;
  const ticketResult = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [id]);
  const ticket = ticketResult.rows[0];
  if (!ticket || (ticket.requester_id !== userId && ticket.assigned_tech_id !== userId)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const repliesResult = await pool.query(
    `SELECT r.*, u.display_name AS author_name
     FROM ticket_replies r
     JOIN users u ON u.id = r.author_id
     WHERE r.ticket_id = $1
     ORDER BY r.created_at ASC`,
    [id]
  );

  const historyResult = await pool.query(
    `SELECT * FROM ticket_status_history WHERE ticket_id = $1 ORDER BY created_at ASC`,
    [id]
  );

  return NextResponse.json({
    ticket,
    replies: repliesResult.rows,
    history: historyResult.rows,
  });
}

// PATCH /api/tickets/:id
// Body: { body?, status? }
// Adds a public reply and/or changes status. The author is the session
// user, not client-supplied — a caller can only ever post as themselves,
// and only on a ticket they're the requester or assigned technician for.
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const authorId = getSessionUserIdFromRequest(req);
  if (!authorId) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;

  const ticketResult = await pool.query(
    `SELECT requester_id, assigned_tech_id FROM tickets WHERE id = $1`,
    [id]
  );
  const ticket = ticketResult.rows[0];
  if (!ticket || (ticket.requester_id !== authorId && ticket.assigned_tech_id !== authorId)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const { body, status } = await req.json();

  try {
    const updated = await addReplyAndUpdateStatus({ ticketId: id, authorId, body, status });
    return NextResponse.json({ ticket: updated });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Failed to update ticket" }, { status: 500 });
  }
}

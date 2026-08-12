import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";

// GET /api/tickets/:id
// Returns the ticket plus its public conversation (replies only —
// ticket_notes is deliberately never joined here so internal notes can
// never leak into an employee-facing response).
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const ticketResult = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [params.id]);
  if (ticketResult.rows.length === 0) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const repliesResult = await pool.query(
    `SELECT r.*, u.display_name AS author_name
     FROM ticket_replies r
     JOIN users u ON u.id = r.author_id
     WHERE r.ticket_id = $1
     ORDER BY r.created_at ASC`,
    [params.id]
  );

  const historyResult = await pool.query(
    `SELECT * FROM ticket_status_history WHERE ticket_id = $1 ORDER BY created_at ASC`,
    [params.id]
  );

  return NextResponse.json({
    ticket: ticketResult.rows[0],
    replies: repliesResult.rows,
    history: historyResult.rows,
  });
}

// PATCH /api/tickets/:id
// Body: { authorId, body?, status? }
// Adds a public reply and/or changes status. Kept as one endpoint since a
// status change is very often accompanied by a reply (e.g. resolving).
export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const { authorId, body, status } = await req.json();

  if (!authorId) {
    return NextResponse.json({ error: "authorId is required" }, { status: 400 });
  }

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    if (body) {
      await client.query(
        `INSERT INTO ticket_replies (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
        [params.id, authorId, body]
      );
    }

    if (status) {
      const currentResult = await client.query(`SELECT status FROM tickets WHERE id = $1`, [params.id]);
      const fromStatus = currentResult.rows[0]?.status;

      if (status === "resolved") {
        await client.query(
          `UPDATE tickets SET status = $1, resolved_at = now(), resolved_by_id = $2, updated_at = now() WHERE id = $3`,
          [status, authorId, params.id]
        );
      } else if (status === "closed") {
        await client.query(
          `UPDATE tickets SET status = $1, closed_at = now(), closed_by_id = $2, updated_at = now() WHERE id = $3`,
          [status, authorId, params.id]
        );
      } else {
        await client.query(
          `UPDATE tickets SET status = $1, updated_at = now() WHERE id = $2`,
          [status, params.id]
        );
      }

      await client.query(
        `INSERT INTO ticket_status_history (ticket_id, changed_by_id, from_status, to_status)
         VALUES ($1, $2, $3, $4)`,
        [params.id, authorId, fromStatus, status]
      );
    }

    await client.query("COMMIT");
    const result = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [params.id]);
    return NextResponse.json({ ticket: result.rows[0] });
  } catch (err) {
    await client.query("ROLLBACK");
    console.error(err);
    return NextResponse.json({ error: "Failed to update ticket" }, { status: 500 });
  } finally {
    client.release();
  }
}

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { assignRoundRobin } from "@/lib/assignment";
import { calculatePriority } from "@/lib/priority";

// GET /api/tickets?userId=...&role=employee|technician
// Employees see only their own tickets; technicians see their team's queue.
export async function GET(req: NextRequest) {
  const userId = req.nextUrl.searchParams.get("userId");
  const role = req.nextUrl.searchParams.get("role") ?? "employee";

  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 });
  }

  const query =
    role === "technician"
      ? `SELECT * FROM tickets WHERE assigned_tech_id = $1 ORDER BY created_at DESC`
      : `SELECT * FROM tickets WHERE requester_id = $1 ORDER BY created_at DESC`;

  const result = await pool.query(query, [userId]);
  return NextResponse.json({ tickets: result.rows });
}

// POST /api/tickets
// Body: { requesterId, openedById, subject, description, categoryId,
//         impact, urgency, submissionChannel, teamId }
export async function POST(req: NextRequest) {
  const body = await req.json();
  const {
    requesterId,
    openedById,
    subject,
    description,
    categoryId,
    impact,
    urgency,
    submissionChannel,
    teamId,
  } = body;

  if (!requesterId || !openedById || !subject || !description || !submissionChannel || !teamId) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  const priority = impact && urgency ? calculatePriority(impact, urgency) : "normal";

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const seqResult = await client.query(`SELECT nextval('ticket_number_seq') AS n`);
    const ticketNumber = `INC-${String(seqResult.rows[0].n).padStart(6, "0")}`;

    const insertResult = await client.query(
      `INSERT INTO tickets
        (ticket_number, request_type, submission_channel, requester_id, opened_by_id,
         subject, description, category_id, impact, urgency, priority, status,
         assigned_team_id)
       VALUES ($1, 'incident', $2, $3, $4, $5, $6, $7, $8, $9, $10, 'open', $11)
       RETURNING *`,
      [
        ticketNumber,
        submissionChannel,
        requesterId,
        openedById,
        subject,
        description,
        categoryId ?? null,
        impact ?? null,
        urgency ?? null,
        priority,
        teamId,
      ]
    );
    const ticket = insertResult.rows[0];

    // Round-robin assign within the same transaction's connection.
    const assignedTechId = await assignRoundRobin(teamId);
    if (assignedTechId) {
      await client.query(
        `UPDATE tickets SET assigned_tech_id = $1, status = 'assigned', updated_at = now() WHERE id = $2`,
        [assignedTechId, ticket.id]
      );
      ticket.assigned_tech_id = assignedTechId;
      ticket.status = "assigned";
    }

    await client.query(
      `INSERT INTO ticket_status_history (ticket_id, from_status, to_status, note)
       VALUES ($1, NULL, $2, 'Ticket created')`,
      [ticket.id, ticket.status]
    );

    await client.query("COMMIT");
    return NextResponse.json({ ticket }, { status: 201 });
  } catch (err) {
    await client.query("ROLLBACK");
    console.error(err);
    return NextResponse.json({ error: "Failed to create ticket" }, { status: 500 });
  } finally {
    client.release();
  }
}

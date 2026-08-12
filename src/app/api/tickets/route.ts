import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { createTicket } from "@/lib/tickets";
import { getSessionUserIdFromRequest } from "@/lib/auth";

// GET /api/tickets?role=employee|technician
// Employees see only their own tickets; technicians see their team's queue.
// The acting user comes from the session cookie, never a client-supplied
// userId — a request can only ever see its own data.
export async function GET(req: NextRequest) {
  const userId = getSessionUserIdFromRequest(req);
  if (!userId) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const role = req.nextUrl.searchParams.get("role") ?? "employee";

  const query =
    role === "technician"
      ? `SELECT * FROM tickets WHERE assigned_tech_id = $1 ORDER BY created_at DESC`
      : `SELECT * FROM tickets WHERE requester_id = $1 ORDER BY created_at DESC`;

  const result = await pool.query(query, [userId]);
  return NextResponse.json({ tickets: result.rows });
}

// POST /api/tickets
// Body: { subject, description, categoryId, impact, urgency,
//         submissionChannel, teamId }
// requesterId/openedById are the session user, not client-supplied — a
// caller can only ever file a ticket as themselves.
export async function POST(req: NextRequest) {
  const userId = getSessionUserIdFromRequest(req);
  if (!userId) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const body = await req.json();
  const { subject, description, categoryId, impact, urgency, submissionChannel, teamId } = body;

  if (!subject || !description || !submissionChannel || !teamId) {
    return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
  }

  try {
    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject,
      description,
      categoryId,
      impact,
      urgency,
      submissionChannel,
      teamId,
    });
    return NextResponse.json({ ticket }, { status: 201 });
  } catch (err) {
    console.error(err);
    return NextResponse.json({ error: "Failed to create ticket" }, { status: 500 });
  }
}

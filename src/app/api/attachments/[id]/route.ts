import path from "path";
import fs from "fs/promises";
import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { getAttachmentById, UPLOADS_DIR } from "@/lib/attachments";
import { getSessionUserIdFromRequest } from "@/lib/auth";

// GET /api/attachments/:id — serves the file. Gated to the ticket's
// requester or assigned technician, same as the rest of the ticket data.
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const userId = getSessionUserIdFromRequest(req);
  if (!userId) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;
  const attachment = await getAttachmentById(id);
  if (!attachment) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const ticketResult = await pool.query(
    `SELECT requester_id, assigned_tech_id FROM tickets WHERE id = $1`,
    [attachment.ticket_id]
  );
  const ticket = ticketResult.rows[0];
  if (!ticket || (ticket.requester_id !== userId && ticket.assigned_tech_id !== userId)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const buffer = await fs.readFile(path.join(UPLOADS_DIR, attachment.storage_path));
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": attachment.content_type,
      "Content-Disposition": `attachment; filename="${encodeURIComponent(attachment.file_name)}"`,
    },
  });
}

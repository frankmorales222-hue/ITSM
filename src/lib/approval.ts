import { pool } from "./db";
import { notifyByEmail } from "./notifications";

// Categories where the request itself (new access, new equipment) is the
// kind of thing a manager should sign off on before IT acts on it — not
// every ticket, just these two.
const APPROVAL_REQUIRED_CATEGORIES = ["Access Request", "Equipment Request"];

// Called once, at ticket creation, with the category already known — so
// this only ever runs against a category name, not a live lookup elsewhere.
export function categoryRequiresApproval(categoryName: string | null | undefined): boolean {
  return !!categoryName && APPROVAL_REQUIRED_CATEGORIES.includes(categoryName);
}

async function setApproval({
  ticketId,
  approverId,
  status,
  note,
}: {
  ticketId: string;
  approverId: string;
  status: "approved" | "rejected";
  note?: string;
}) {
  const client = await pool.connect();
  let notifyRecipientId: string | null = null;
  try {
    await client.query("BEGIN");

    const result = await client.query(
      `SELECT approval_status, assigned_tech_id, requester_id FROM tickets WHERE id = $1`,
      [ticketId]
    );
    if (result.rows.length === 0) {
      throw new Error("Ticket not found");
    }
    const { approval_status: current, assigned_tech_id: assignedTechId } = result.rows[0];

    if (current !== "pending") {
      await client.query("ROLLBACK");
      return;
    }

    await client.query(
      `UPDATE tickets
       SET approval_status = $1, approved_by_id = $2, approved_at = now(), approval_note = $3, updated_at = now()
       WHERE id = $4`,
      [status, approverId, note ?? null, ticketId]
    );

    const note_ = note ? ` Note: ${note}` : "";
    await client.query(`INSERT INTO ticket_notes (ticket_id, author_id, body) VALUES ($1, $2, $3)`, [
      ticketId,
      approverId,
      `Approval ${status}.${note_}`,
    ]);

    if (assignedTechId) {
      await client.query(
        `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
         VALUES ($1, $2, $3, 'in_app', now())`,
        [ticketId, assignedTechId, status === "approved" ? "ticket_approved" : "ticket_rejected"]
      );
      notifyRecipientId = assignedTechId;
    }

    await client.query("COMMIT");

    if (notifyRecipientId) {
      await notifyByEmail({
        ticketId,
        recipientId: notifyRecipientId,
        event: status === "approved" ? "ticket_approved" : "ticket_rejected",
      });
    }
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function approveTicket(args: { ticketId: string; approverId: string; note?: string }) {
  await setApproval({ ...args, status: "approved" });
}

export async function rejectTicket(args: { ticketId: string; approverId: string; note?: string }) {
  await setApproval({ ...args, status: "rejected" });
}

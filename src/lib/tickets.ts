import { pool } from "./db";
import { assignRoundRobin } from "./assignment";
import { calculatePriority } from "./priority";

type SubmissionChannel = "web" | "email" | "technician";

export interface CreateTicketInput {
  requesterId: string;
  openedById: string;
  subject: string;
  description: string;
  categoryId?: string | null;
  impact?: "high" | "medium" | "low" | null;
  urgency?: "high" | "medium" | "low" | null;
  submissionChannel: SubmissionChannel;
  teamId: string;
}

// Shared by the web ticket-creation endpoint and the email intake worker so
// assignment/priority/history logic only lives in one place.
export async function createTicket(input: CreateTicketInput) {
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
  } = input;

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
    return ticket;
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function getDefaultTeamId(): Promise<string | null> {
  const result = await pool.query(`SELECT id FROM teams WHERE name = 'IT Support' LIMIT 1`);
  return result.rows[0]?.id ?? null;
}

// Internal notes are a separate table from ticket_replies specifically so
// they can never leak into an employee-facing query by accident.
export async function getNotesForTicket(ticketId: string) {
  const result = await pool.query(
    `SELECT n.*, u.display_name AS author_name
     FROM ticket_notes n
     JOIN users u ON u.id = n.author_id
     WHERE n.ticket_id = $1
     ORDER BY n.created_at ASC`,
    [ticketId]
  );
  return result.rows;
}

export async function addNote({
  ticketId,
  authorId,
  body,
}: {
  ticketId: string;
  authorId: string;
  body: string;
}) {
  await pool.query(
    `INSERT INTO ticket_notes (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
    [ticketId, authorId, body]
  );
}

export interface AddReplyInput {
  ticketId: string;
  authorId: string;
  body?: string;
  status?: string;
}

// Adds a public reply and/or changes status. Kept as one operation since a
// status change is very often accompanied by a reply (e.g. resolving).
export async function addReplyAndUpdateStatus({ ticketId, authorId, body, status }: AddReplyInput) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    if (body) {
      await client.query(
        `INSERT INTO ticket_replies (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
        [ticketId, authorId, body]
      );
    }

    if (status) {
      const currentResult = await client.query(`SELECT status FROM tickets WHERE id = $1`, [ticketId]);
      const fromStatus = currentResult.rows[0]?.status;

      if (status === "resolved") {
        await client.query(
          `UPDATE tickets SET status = $1, resolved_at = now(), resolved_by_id = $2, updated_at = now() WHERE id = $3`,
          [status, authorId, ticketId]
        );
      } else if (status === "closed") {
        await client.query(
          `UPDATE tickets SET status = $1, closed_at = now(), closed_by_id = $2, updated_at = now() WHERE id = $3`,
          [status, authorId, ticketId]
        );
      } else {
        await client.query(
          `UPDATE tickets SET status = $1, updated_at = now() WHERE id = $2`,
          [status, ticketId]
        );
      }

      await client.query(
        `INSERT INTO ticket_status_history (ticket_id, changed_by_id, from_status, to_status)
         VALUES ($1, $2, $3, $4)`,
        [ticketId, authorId, fromStatus, status]
      );
    }

    await client.query("COMMIT");
    const result = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [ticketId]);
    return result.rows[0];
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

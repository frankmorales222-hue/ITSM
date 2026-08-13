import { pool } from "./db";
import { assignRoundRobin } from "./assignment";
import { calculatePriority, bumpPriority } from "./priority";
import { calculateDueAt } from "./sla";
import { STATUSES } from "./ticket-filters";
import { notifyByEmail, type NotificationEvent } from "./notifications";
import { categoryRequiresApproval } from "./approval";

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
  const dueAt = calculateDueAt(priority);

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const seqResult = await client.query(`SELECT nextval('ticket_number_seq') AS n`);
    const ticketNumber = `INC-${String(seqResult.rows[0].n).padStart(6, "0")}`;

    // Approval is only meaningful if there's someone to approve it — a
    // category that normally needs sign-off silently skips it for a
    // requester with no manager on file, rather than blocking the ticket
    // on an approval that can never happen.
    let approvalStatus: "pending" | null = null;
    if (categoryId) {
      const [categoryResult, requesterResult] = await Promise.all([
        client.query(`SELECT name FROM categories WHERE id = $1`, [categoryId]),
        client.query(`SELECT manager_id FROM users WHERE id = $1`, [requesterId]),
      ]);
      const requiresApproval = categoryRequiresApproval(categoryResult.rows[0]?.name);
      if (requiresApproval && requesterResult.rows[0]?.manager_id) {
        approvalStatus = "pending";
      }
    }

    const insertResult = await client.query(
      `INSERT INTO tickets
        (ticket_number, request_type, submission_channel, requester_id, opened_by_id,
         subject, description, category_id, impact, urgency, priority, status,
         assigned_team_id, due_at, approval_status)
       VALUES ($1, 'incident', $2, $3, $4, $5, $6, $7, $8, $9, $10, 'open', $11, $12, $13)
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
        dueAt,
        approvalStatus,
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

      await client.query(
        `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
         VALUES ($1, $2, 'ticket_assigned', 'in_app', now())`,
        [ticket.id, assignedTechId]
      );
    }

    await client.query(
      `INSERT INTO ticket_status_history (ticket_id, from_status, to_status, note)
       VALUES ($1, NULL, $2, 'Ticket created')`,
      [ticket.id, ticket.status]
    );

    await client.query("COMMIT");

    if (assignedTechId) {
      await notifyByEmail({ ticketId: ticket.id, recipientId: assignedTechId, event: "ticket_assigned" });
    }

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

// Reassignment isn't a status change, so it's logged as an internal note
// (technician-only, same audit trail readers already check) rather than
// adding a dedicated history table.
export async function reassignTicket({
  ticketId,
  newTechId,
  reassignedById,
}: {
  ticketId: string;
  newTechId: string;
  reassignedById: string;
}) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const currentResult = await client.query(
      `SELECT t.assigned_tech_id, t.status, u.display_name AS current_tech_name
       FROM tickets t
       LEFT JOIN users u ON u.id = t.assigned_tech_id
       WHERE t.id = $1`,
      [ticketId]
    );
    if (currentResult.rows.length === 0) {
      throw new Error("Ticket not found");
    }
    const { assigned_tech_id: fromTechId, status, current_tech_name: fromTechName } = currentResult.rows[0];

    if (fromTechId === newTechId) {
      await client.query("ROLLBACK");
      return;
    }

    const newTechResult = await client.query(`SELECT display_name FROM users WHERE id = $1`, [newTechId]);
    const newTechName = newTechResult.rows[0]?.display_name ?? "Unknown";

    const nextStatus = status === "open" ? "assigned" : status;
    await client.query(
      `UPDATE tickets SET assigned_tech_id = $1, status = $2, updated_at = now() WHERE id = $3`,
      [newTechId, nextStatus, ticketId]
    );

    const note = fromTechName
      ? `Reassigned from ${fromTechName} to ${newTechName}.`
      : `Assigned to ${newTechName}.`;
    await client.query(
      `INSERT INTO ticket_notes (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
      [ticketId, reassignedById, note]
    );

    if (newTechId !== reassignedById) {
      await client.query(
        `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
         VALUES ($1, $2, 'ticket_assigned', 'in_app', now())`,
        [ticketId, newTechId]
      );
    }

    await client.query("COMMIT");

    if (newTechId !== reassignedById) {
      await notifyByEmail({ ticketId, recipientId: newTechId, event: "ticket_assigned" });
    }
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

// Bumps priority a level and notifies the rest of the assigned team (not
// just the current assignee) — escalation is meant to pull in more eyes,
// not just restate what the assignee already knows.
export async function escalateTicket({
  ticketId,
  actorId,
  reason,
}: {
  ticketId: string;
  actorId: string;
  reason?: string;
}) {
  const client = await pool.connect();
  const pendingEmails: { recipientId: string; event: NotificationEvent }[] = [];
  try {
    await client.query("BEGIN");

    const currentResult = await client.query(
      `SELECT priority, is_escalated, assigned_team_id FROM tickets WHERE id = $1`,
      [ticketId]
    );
    if (currentResult.rows.length === 0) {
      throw new Error("Ticket not found");
    }
    const { priority, is_escalated: alreadyEscalated, assigned_team_id: teamId } = currentResult.rows[0];

    if (alreadyEscalated) {
      await client.query("ROLLBACK");
      return;
    }

    const newPriority = bumpPriority(priority);

    await client.query(
      `UPDATE tickets
       SET is_escalated = true, escalated_at = now(), escalated_by_id = $1,
           escalation_reason = $2, priority = $3, updated_at = now()
       WHERE id = $4`,
      [actorId, reason ?? null, newPriority, ticketId]
    );

    const note =
      priority === newPriority
        ? `Escalated by request.${reason ? ` Reason: ${reason}` : ""}`
        : `Escalated — priority raised from ${priority} to ${newPriority}.${reason ? ` Reason: ${reason}` : ""}`;
    await client.query(`INSERT INTO ticket_notes (ticket_id, author_id, body) VALUES ($1, $2, $3)`, [
      ticketId,
      actorId,
      note,
    ]);

    if (teamId) {
      const teammatesResult = await client.query(
        `SELECT u.id
         FROM team_members tm
         JOIN users u ON u.id = tm.user_id
         WHERE tm.team_id = $1 AND u.is_technician = true AND u.is_active = true AND u.id != $2`,
        [teamId, actorId]
      );
      for (const row of teammatesResult.rows) {
        await client.query(
          `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
           VALUES ($1, $2, 'ticket_escalated', 'in_app', now())`,
          [ticketId, row.id]
        );
        pendingEmails.push({ recipientId: row.id, event: "ticket_escalated" });
      }
    }

    await client.query("COMMIT");

    for (const { recipientId, event } of pendingEmails) {
      await notifyByEmail({ ticketId, recipientId, event });
    }
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

// Scoped to tickets assigned to actorId so a technician can only bulk-edit
// their own queue, matching what the technician page shows them.
export async function bulkUpdateStatus({
  ticketIds,
  status,
  actorId,
}: {
  ticketIds: string[];
  status: string;
  actorId: string;
}) {
  if (ticketIds.length === 0 || !STATUSES.includes(status)) {
    return;
  }

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const currentResult = await client.query(
      `SELECT id, status FROM tickets WHERE id = ANY($1) AND assigned_tech_id = $2`,
      [ticketIds, actorId]
    );
    const rows = currentResult.rows;
    if (rows.length === 0) {
      await client.query("ROLLBACK");
      return;
    }
    const idsToUpdate = rows.map((r) => r.id);

    if (status === "resolved") {
      await client.query(
        `UPDATE tickets SET status = $1, resolved_at = now(), resolved_by_id = $2, updated_at = now() WHERE id = ANY($3)`,
        [status, actorId, idsToUpdate]
      );
    } else if (status === "closed") {
      await client.query(
        `UPDATE tickets SET status = $1, closed_at = now(), closed_by_id = $2, updated_at = now() WHERE id = ANY($3)`,
        [status, actorId, idsToUpdate]
      );
    } else {
      await client.query(
        `UPDATE tickets SET status = $1, updated_at = now() WHERE id = ANY($2)`,
        [status, idsToUpdate]
      );
    }

    for (const row of rows) {
      await client.query(
        `INSERT INTO ticket_status_history (ticket_id, changed_by_id, from_status, to_status)
         VALUES ($1, $2, $3, $4)`,
        [row.id, actorId, row.status, status]
      );
    }

    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
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
  const pendingEmails: { recipientId: string; event: NotificationEvent }[] = [];
  try {
    await client.query("BEGIN");

    const ticketResult = await client.query(
      `SELECT status, requester_id, assigned_tech_id FROM tickets WHERE id = $1`,
      [ticketId]
    );
    const { status: fromStatus, requester_id: requesterId, assigned_tech_id: assignedTechId } =
      ticketResult.rows[0];

    if (body) {
      await client.query(
        `INSERT INTO ticket_replies (ticket_id, author_id, body) VALUES ($1, $2, $3)`,
        [ticketId, authorId, body]
      );

      const replyEvent = authorId === requesterId ? "requester_replied" : "technician_replied";
      const replyRecipient = authorId === requesterId ? assignedTechId : requesterId;
      if (replyRecipient && replyRecipient !== authorId) {
        await client.query(
          `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
           VALUES ($1, $2, $3, 'in_app', now())`,
          [ticketId, replyRecipient, replyEvent]
        );
        pendingEmails.push({ recipientId: replyRecipient, event: replyEvent });
      }
    }

    if (status) {
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

      if (requesterId && requesterId !== authorId) {
        const statusEvent: NotificationEvent =
          status === "resolved" ? "ticket_resolved" : status === "closed" ? "ticket_closed" : "status_changed";
        await client.query(
          `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
           VALUES ($1, $2, $3, 'in_app', now())`,
          [ticketId, requesterId, statusEvent]
        );
        pendingEmails.push({ recipientId: requesterId, event: statusEvent });
      }
    }

    await client.query("COMMIT");

    for (const { recipientId, event } of pendingEmails) {
      await notifyByEmail({ ticketId, recipientId, event });
    }

    const result = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [ticketId]);
    return result.rows[0];
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

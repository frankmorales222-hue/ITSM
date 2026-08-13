import { pool } from "./db";
import { sendMail } from "./mailer";

export type NotificationEvent =
  | "ticket_assigned"
  | "technician_replied"
  | "requester_replied"
  | "status_changed"
  | "ticket_resolved"
  | "ticket_closed"
  | "ticket_escalated"
  | "ticket_approved"
  | "ticket_rejected";

export const EVENT_LABELS: Record<NotificationEvent, string> = {
  ticket_assigned: "Assigned to you",
  technician_replied: "Technician replied",
  requester_replied: "Requester replied",
  status_changed: "Status changed",
  ticket_resolved: "Resolved",
  ticket_closed: "Closed",
  ticket_escalated: "Escalated",
  ticket_approved: "Approved",
  ticket_rejected: "Rejected",
};

// In-app only for phase 1 (channel = 'in_app'); email notifications reuse
// this same table with channel = 'email' once outbound email exists.
export async function createNotification({
  ticketId,
  recipientId,
  event,
}: {
  ticketId: string;
  recipientId: string;
  event: NotificationEvent;
}) {
  await pool.query(
    `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
     VALUES ($1, $2, $3, 'in_app', now())`,
    [ticketId, recipientId, event]
  );
}

export async function getNotificationsForUser(userId: string, limit = 50) {
  const result = await pool.query(
    `SELECT n.*, t.ticket_number, t.subject
     FROM ticket_notifications n
     JOIN tickets t ON t.id = n.ticket_id
     WHERE n.recipient_id = $1 AND n.channel = 'in_app'
     ORDER BY n.created_at DESC
     LIMIT $2`,
    [userId, limit]
  );
  return result.rows;
}

export async function getUnreadNotificationCount(userId: string): Promise<number> {
  const result = await pool.query(
    `SELECT count(*)::int AS n
     FROM ticket_notifications
     WHERE recipient_id = $1 AND channel = 'in_app' AND read_at IS NULL`,
    [userId]
  );
  return result.rows[0].n;
}

export async function markNotificationRead(notificationId: string, userId: string) {
  await pool.query(
    `UPDATE ticket_notifications SET read_at = now()
     WHERE id = $1 AND recipient_id = $2 AND read_at IS NULL`,
    [notificationId, userId]
  );
}

export async function markAllNotificationsRead(userId: string) {
  await pool.query(
    `UPDATE ticket_notifications SET read_at = now()
     WHERE recipient_id = $1 AND channel = 'in_app' AND read_at IS NULL`,
    [userId]
  );
}

// Called after the triggering DB transaction has already committed, so a
// slow/unreachable SMTP server never holds a ticket-mutation transaction
// open. Swallows its own errors — a failed email must never surface as a
// failure of the user-facing action that triggered it.
export async function notifyByEmail({
  ticketId,
  recipientId,
  event,
}: {
  ticketId: string;
  recipientId: string;
  event: NotificationEvent;
}): Promise<void> {
  try {
    const result = await pool.query(
      `SELECT u.email, t.ticket_number, t.subject
       FROM users u, tickets t
       WHERE u.id = $1 AND t.id = $2`,
      [recipientId, ticketId]
    );
    const row = result.rows[0];
    if (!row) return;

    const label = EVENT_LABELS[event];
    const sent = await sendMail({
      to: row.email,
      subject: `[${row.ticket_number}] ${label}`,
      text: `${label}\n\n${row.ticket_number}: ${row.subject}`,
    });

    if (sent) {
      await pool.query(
        `INSERT INTO ticket_notifications (ticket_id, recipient_id, event, channel, sent_at)
         VALUES ($1, $2, $3, 'email', now())`,
        [ticketId, recipientId, event]
      );
    }
  } catch (err) {
    console.error("Failed to send email notification:", err);
  }
}

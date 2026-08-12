// Ticket detail page — conversation (public replies only) + a reply box
// and status control. The acting user is the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { addReplyAndUpdateStatus } from "@/lib/tickets";
import { getSessionUserId } from "@/lib/auth";

const STATUSES = [
  "open",
  "assigned",
  "in_progress",
  "waiting_on_you",
  "waiting_on_vendor",
  "on_hold",
  "pending_verification",
  "resolved",
  "closed",
  "cancelled",
];

async function getTicket(id: string) {
  const ticketResult = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [id]);
  if (ticketResult.rows.length === 0) {
    return null;
  }

  const repliesResult = await pool.query(
    `SELECT r.*, u.display_name AS author_name
     FROM ticket_replies r
     JOIN users u ON u.id = r.author_id
     WHERE r.ticket_id = $1
     ORDER BY r.created_at ASC`,
    [id]
  );

  return { ticket: ticketResult.rows[0], replies: repliesResult.rows };
}

export default async function TicketDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }
  const data = await getTicket(id);
  if (!data) {
    return (
      <main style={{ padding: 24, fontFamily: "sans-serif" }}>
        <p>Ticket not found.</p>
      </main>
    );
  }
  const { ticket, replies } = data;

  async function submitReply(formData: FormData) {
    "use server";
    const authorId = await getSessionUserId();
    if (!authorId) {
      redirect("/login");
    }
    const body = String(formData.get("body") ?? "").trim();
    const status = String(formData.get("status") ?? "");

    await addReplyAndUpdateStatus({
      ticketId: id,
      authorId,
      body: body || undefined,
      status: status || undefined,
    });

    redirect(`/tickets/${id}`);
  }

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 640 }}>
      <p>
        <a href="/tickets">&larr; My Requests</a>
      </p>
      <h1>
        {ticket.ticket_number}: {ticket.subject}
      </h1>
      <p>
        Status: <strong>{ticket.status}</strong> &nbsp;|&nbsp; Priority:{" "}
        <strong>{ticket.priority}</strong>
      </p>
      <p style={{ whiteSpace: "pre-wrap" }}>{ticket.description}</p>

      <h2>Conversation</h2>
      {replies.length === 0 && <p>No replies yet.</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {replies.map((r: any) => (
          <li
            key={r.id}
            style={{ borderBottom: "1px solid #eee", padding: "8px 0" }}
          >
            <strong>{r.author_name}</strong>{" "}
            <span style={{ color: "#888" }}>
              {new Date(r.created_at).toLocaleString()}
            </span>
            <p style={{ whiteSpace: "pre-wrap", margin: "4px 0 0" }}>{r.body}</p>
          </li>
        ))}
      </ul>

      <h2>Reply</h2>
      <form action={submitReply}>
        <textarea name="body" rows={4} style={{ width: "100%" }} />
        <div style={{ marginTop: 8 }}>
          <label htmlFor="status">Change status</label>
          <br />
          <select id="status" name="status" defaultValue={ticket.status}>
            <option value="">(no change)</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" style={{ marginTop: 8 }}>
          Submit
        </button>
      </form>
    </main>
  );
}

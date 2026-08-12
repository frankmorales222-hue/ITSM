// Ticket detail page — conversation (public replies only) + a reply box,
// status control, and attachments, visible to the ticket's requester or
// assigned technician. Internal notes are technician-only, gated
// server-side (not just hidden in the UI) since ticket_notes must never
// reach the requester.

import { redirect, notFound } from "next/navigation";
import { pool } from "@/lib/db";
import { addReplyAndUpdateStatus, getNotesForTicket, addNote } from "@/lib/tickets";
import {
  getAttachmentsForTicket,
  saveAttachment,
  assertValidAttachment,
  AttachmentValidationError,
} from "@/lib/attachments";
import { getSessionUserId, isTechnician } from "@/lib/auth";

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

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default async function TicketDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { id } = await params;
  const { error } = await searchParams;
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }

  const data = await getTicket(id);
  if (!data) {
    notFound();
  }
  const { ticket, replies } = data;

  const canView = ticket.requester_id === sessionUserId || ticket.assigned_tech_id === sessionUserId;
  if (!canView) {
    notFound();
  }

  const isTech = await isTechnician(sessionUserId);
  const [attachments, notes] = await Promise.all([
    getAttachmentsForTicket(id),
    isTech ? getNotesForTicket(id) : Promise.resolve([]),
  ]);

  async function submitReply(formData: FormData) {
    "use server";
    const authorId = await getSessionUserId();
    if (!authorId) {
      redirect("/login");
    }
    const body = String(formData.get("body") ?? "").trim();
    const status = String(formData.get("status") ?? "");
    const file = formData.get("attachment") as File | null;
    const hasFile = file && file.size > 0;

    if (hasFile) {
      try {
        assertValidAttachment(file);
      } catch (err) {
        if (err instanceof AttachmentValidationError) {
          redirect(`/tickets/${id}?error=${encodeURIComponent(err.message)}`);
        }
        throw err;
      }
    }

    await addReplyAndUpdateStatus({
      ticketId: id,
      authorId,
      body: body || undefined,
      status: status || undefined,
    });

    if (hasFile) {
      await saveAttachment({ ticketId: id, uploadedById: authorId, file });
    }

    redirect(`/tickets/${id}`);
  }

  async function submitNote(formData: FormData) {
    "use server";
    const authorId = await getSessionUserId();
    if (!authorId || !(await isTechnician(authorId))) {
      redirect("/login");
    }
    const body = String(formData.get("note") ?? "").trim();
    if (body) {
      await addNote({ ticketId: id, authorId, body });
    }
    redirect(`/tickets/${id}`);
  }

  return (
    <main>
      <nav className="nav">
        <a href="/tickets">&larr; My Requests</a>
      </nav>

      <div className="card">
        <h1>
          {ticket.ticket_number}: {ticket.subject}
        </h1>
        <p>
          <span className="badge">{ticket.status}</span>{" "}
          <span className="badge">{ticket.priority}</span>
        </p>
        <p style={{ whiteSpace: "pre-wrap" }}>{ticket.description}</p>
      </div>

      <div className="card">
        <h2>Conversation</h2>
        {replies.length === 0 && <p className="muted">No replies yet.</p>}
        {replies.map((r: any) => (
          <div key={r.id} className="reply">
            <div className="reply-meta">
              <strong>{r.author_name}</strong> &middot;{" "}
              {new Date(r.created_at).toLocaleString()}
            </div>
            <p className="reply-body">{r.body}</p>
          </div>
        ))}

        <h2>Attachments</h2>
        {attachments.length === 0 && <p className="muted">No attachments.</p>}
        {attachments.length > 0 && (
          <ul style={{ paddingLeft: 20 }}>
            {attachments.map((a: any) => (
              <li key={a.id}>
                <a href={`/api/attachments/${a.id}`}>{a.file_name}</a>{" "}
                <span className="muted">
                  ({formatSize(a.size_bytes)}, {a.uploaded_by_name})
                </span>
              </li>
            ))}
          </ul>
        )}

        <h2>Reply</h2>
        {error && <p className="error">{error}</p>}
        <form action={submitReply} encType="multipart/form-data">
          <div className="field">
            <textarea name="body" rows={4} placeholder="Write a reply..." />
          </div>
          <div className="field">
            <label htmlFor="attachment">Attach a file (optional)</label>
            <input id="attachment" name="attachment" type="file" />
          </div>
          <div className="field" style={{ maxWidth: 220 }}>
            <label htmlFor="status">Change status</label>
            <select id="status" name="status" defaultValue="">
              <option value="">(no change)</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <button type="submit">Submit</button>
        </form>
      </div>

      {isTech && (
        <div className="card">
          <h2>Internal Notes</h2>
          <p className="muted">Visible to technicians only — never shown to the requester.</p>
          {notes.length === 0 && <p className="muted">No notes yet.</p>}
          {notes.map((n: any) => (
            <div key={n.id} className="note">
              <div className="reply-meta">
                <strong>{n.author_name}</strong> &middot;{" "}
                {new Date(n.created_at).toLocaleString()}
              </div>
              <p className="reply-body">{n.body}</p>
            </div>
          ))}
          <form action={submitNote} style={{ marginTop: 12 }}>
            <div className="field">
              <textarea name="note" rows={3} placeholder="Add an internal note..." />
            </div>
            <button type="submit" className="secondary">
              Add note
            </button>
          </form>
        </div>
      )}
    </main>
  );
}

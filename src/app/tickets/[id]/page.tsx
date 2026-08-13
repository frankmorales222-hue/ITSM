// Ticket detail page — conversation (public replies only) + a reply box,
// status control, and attachments, visible to the ticket's requester or
// assigned technician. Internal notes are technician-only, gated
// server-side (not just hidden in the UI) since ticket_notes must never
// reach the requester.

import { redirect, notFound } from "next/navigation";
import { pool } from "@/lib/db";
import { addReplyAndUpdateStatus, getNotesForTicket, addNote, reassignTicket, escalateTicket } from "@/lib/tickets";
import { approveTicket, rejectTicket } from "@/lib/approval";
import {
  getAttachmentsForTicket,
  saveAttachment,
  assertValidAttachment,
  assertWithinTicketQuota,
  AttachmentValidationError,
} from "@/lib/attachments";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import { getActiveTechnicians } from "@/lib/ticket-filters";
import { isOverdue } from "@/lib/sla";
import Nav from "@/components/Nav";
import ConfirmSubmitButton from "@/components/ConfirmSubmitButton";

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
  const ticketResult = await pool.query(
    `SELECT t.*, c.name AS category_name, u.display_name AS assigned_tech_name,
            e.display_name AS escalated_by_name, r.manager_id AS requester_manager_id,
            a.display_name AS approved_by_name
     FROM tickets t
     LEFT JOIN categories c ON c.id = t.category_id
     LEFT JOIN users u ON u.id = t.assigned_tech_id
     LEFT JOIN users e ON e.id = t.escalated_by_id
     LEFT JOIN users r ON r.id = t.requester_id
     LEFT JOIN users a ON a.id = t.approved_by_id
     WHERE t.id = $1`,
    [id]
  );
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

  const isManager = ticket.requester_manager_id === sessionUserId;
  const canView =
    ticket.requester_id === sessionUserId || ticket.assigned_tech_id === sessionUserId || isManager;
  if (!canView) {
    notFound();
  }

  const isTech = await isTechnician(sessionUserId);
  const [attachments, notes, technicians] = await Promise.all([
    getAttachmentsForTicket(id),
    isTech ? getNotesForTicket(id) : Promise.resolve([]),
    isTech ? getActiveTechnicians() : Promise.resolve([]),
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

    if ((status === "resolved" || status === "closed") && ticket.approval_status === "pending") {
      redirect(
        `/tickets/${id}?error=${encodeURIComponent(
          "This ticket is awaiting manager approval and can't be resolved or closed yet."
        )}`
      );
    }

    if (hasFile) {
      try {
        assertValidAttachment(file);
        await assertWithinTicketQuota(id, file);
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

  async function submitReassign(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || !(await isTechnician(actorId))) {
      redirect("/login");
    }
    const newTechId = String(formData.get("technician") ?? "");
    if (newTechId) {
      await reassignTicket({ ticketId: id, newTechId, reassignedById: actorId });
    }
    redirect(`/tickets/${id}`);
  }

  async function submitEscalate(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || !(await isTechnician(actorId))) {
      redirect("/login");
    }
    const reason = String(formData.get("reason") ?? "").trim();
    await escalateTicket({ ticketId: id, actorId, reason: reason || undefined });
    redirect(`/tickets/${id}`);
  }

  async function submitApprove(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || actorId !== ticket.requester_manager_id) {
      redirect("/login");
    }
    const note = String(formData.get("note") ?? "").trim();
    await approveTicket({ ticketId: id, approverId: actorId, note: note || undefined });
    redirect(`/tickets/${id}`);
  }

  async function submitReject(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || actorId !== ticket.requester_manager_id) {
      redirect("/login");
    }
    const note = String(formData.get("note") ?? "").trim();
    await rejectTicket({ ticketId: id, approverId: actorId, note: note || undefined });
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
      <Nav userId={sessionUserId} />

      <div className="card">
        <h1>
          {ticket.ticket_number}: {ticket.subject}
        </h1>
        <p>
          <span className="badge">{ticket.status}</span>{" "}
          <span className="badge">{ticket.priority}</span>
          {ticket.category_name && <span className="badge">{ticket.category_name}</span>}{" "}
          {ticket.due_at &&
            (isOverdue(ticket) ? (
              <span className="badge badge-overdue">Overdue</span>
            ) : (
              <span className="badge">Due {new Date(ticket.due_at).toLocaleString()}</span>
            ))}{" "}
          {ticket.is_escalated && <span className="badge badge-overdue">Escalated</span>}{" "}
          {ticket.approval_status === "pending" && (
            <span className="badge badge-overdue">Awaiting approval</span>
          )}
          {ticket.approval_status === "rejected" && (
            <span className="badge badge-overdue">Approval rejected</span>
          )}
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
        <form action={submitReply}>
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
          <h2>Assignment</h2>
          <p className="muted">
            Currently assigned to: {ticket.assigned_tech_name ?? "Unassigned"}
          </p>
          <form action={submitReassign} style={{ display: "flex", gap: 12, alignItems: "flex-end" }}>
            <div className="field" style={{ maxWidth: 240, marginBottom: 0 }}>
              <label htmlFor="technician">Reassign to</label>
              <select id="technician" name="technician" defaultValue={ticket.assigned_tech_id ?? ""}>
                <option value="" disabled>
                  Select a technician
                </option>
                {technicians.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.display_name}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" className="secondary">
              Reassign
            </button>
          </form>
        </div>
      )}

      {ticket.approval_status && (isTech || isManager) && (
        <div className="card">
          <h2>Approval</h2>
          {ticket.approval_status === "pending" ? (
            isManager ? (
              <>
                <p className="muted">This request needs your approval before IT can act on it.</p>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                  <form action={submitApprove}>
                    <div className="field">
                      <textarea name="note" rows={2} placeholder="Note (optional)" />
                    </div>
                    <button type="submit">Approve</button>
                  </form>
                  <form action={submitReject}>
                    <div className="field">
                      <textarea name="note" rows={2} placeholder="Reason (optional)" />
                    </div>
                    <ConfirmSubmitButton
                      className="secondary"
                      message="Reject this request? The requester and technician will be notified."
                    >
                      Reject
                    </ConfirmSubmitButton>
                  </form>
                </div>
              </>
            ) : (
              <p className="muted">Waiting on the requester's manager to approve this request.</p>
            )
          ) : (
            <p className="muted">
              {ticket.approval_status === "approved" ? "Approved" : "Rejected"} by{" "}
              {ticket.approved_by_name ?? "the manager"} on{" "}
              {new Date(ticket.approved_at).toLocaleString()}.
              {ticket.approval_note && ` Note: ${ticket.approval_note}`}
            </p>
          )}
        </div>
      )}

      {isTech && (
        <div className="card">
          <h2>Escalation</h2>
          {ticket.is_escalated ? (
            <p className="muted">
              Escalated by {ticket.escalated_by_name ?? "a technician"} on{" "}
              {new Date(ticket.escalated_at).toLocaleString()}.
              {ticket.escalation_reason && ` Reason: ${ticket.escalation_reason}`}
            </p>
          ) : (
            <>
              <p className="muted">
                Raises priority a level and notifies the rest of the assigned team.
              </p>
              <form action={submitEscalate}>
                <div className="field">
                  <textarea name="reason" rows={2} placeholder="Reason (optional)" />
                </div>
                <ConfirmSubmitButton
                  className="secondary"
                  message="Escalate this ticket? This raises its priority and notifies the rest of the team."
                >
                  Escalate
                </ConfirmSubmitButton>
              </form>
            </>
          )}
        </div>
      )}

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

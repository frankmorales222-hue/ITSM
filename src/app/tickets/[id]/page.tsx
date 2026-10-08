// Ticket detail page — a unified activity timeline (replies, status
// changes, and for technicians, internal notes/audit entries) plus a
// reply box, status control, and attachments. Visible to the ticket's
// requester, assigned technician, or (once approval applies) the
// requester's manager. Internal notes stay technician-only, gated
// server-side (not just hidden in the UI) since ticket_notes must never
// reach the requester — see getTimeline's includeInternal parameter.

import { redirect, notFound } from "next/navigation";
import { pool } from "@/lib/db";
import { addReplyAndUpdateStatus, addNote, reassignTicket, escalateTicket } from "@/lib/tickets";
import { approveTicket, rejectTicket } from "@/lib/approval";
import { getTimeline } from "@/lib/timeline";
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
import { StatusBadge, PriorityBadge } from "@/components/StatusBadge";
import AjaxForm from "@/components/AjaxForm";
import ModalTrigger from "@/components/Modal";
import Timeline from "@/components/Timeline";

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
  return ticketResult.rows[0] ?? null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default async function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }

  const ticket = await getTicket(id);
  if (!ticket) {
    notFound();
  }

  const isManager = ticket.requester_manager_id === sessionUserId;
  const canView =
    ticket.requester_id === sessionUserId || ticket.assigned_tech_id === sessionUserId || isManager;
  if (!canView) {
    notFound();
  }

  const isTech = await isTechnician(sessionUserId);
  const [attachments, timeline, technicians] = await Promise.all([
    getAttachmentsForTicket(id),
    getTimeline(id, isTech),
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
      return { error: "This ticket is awaiting manager approval and can't be resolved or closed yet." };
    }

    if (hasFile) {
      try {
        assertValidAttachment(file);
        await assertWithinTicketQuota(id, file);
      } catch (err) {
        if (err instanceof AttachmentValidationError) {
          return { error: err.message };
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
  }

  async function submitReassign(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || !(await isTechnician(actorId))) {
      redirect("/login");
    }
    const newTechId = String(formData.get("technician") ?? "");
    if (!newTechId) {
      return { error: "Select a technician first." };
    }
    await reassignTicket({ ticketId: id, newTechId, reassignedById: actorId });
  }

  async function submitEscalate(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || !(await isTechnician(actorId))) {
      redirect("/login");
    }
    const reason = String(formData.get("reason") ?? "").trim();
    await escalateTicket({ ticketId: id, actorId, reason: reason || undefined });
  }

  async function submitApprove(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || actorId !== ticket.requester_manager_id) {
      redirect("/login");
    }
    const note = String(formData.get("note") ?? "").trim();
    await approveTicket({ ticketId: id, approverId: actorId, note: note || undefined });
  }

  async function submitReject(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId || actorId !== ticket.requester_manager_id) {
      redirect("/login");
    }
    const note = String(formData.get("note") ?? "").trim();
    await rejectTicket({ ticketId: id, approverId: actorId, note: note || undefined });
  }

  async function submitNote(formData: FormData) {
    "use server";
    const authorId = await getSessionUserId();
    if (!authorId || !(await isTechnician(authorId))) {
      redirect("/login");
    }
    const body = String(formData.get("note") ?? "").trim();
    if (!body) {
      return { error: "Note can't be empty." };
    }
    await addNote({ ticketId: id, authorId, body });
  }

  return (
    <main>
      <Nav userId={sessionUserId} />

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <h1 style={{ marginBottom: 12 }}>
            {ticket.ticket_number}: {ticket.subject}
          </h1>
          {isTech && (
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              <ModalTrigger label="Reassign" title="Reassign ticket" buttonClassName="secondary">
                <AjaxForm action={submitReassign} successMessage="Ticket reassigned." resetOnSuccess={false}>
                  <p className="muted">
                    Currently assigned to: {ticket.assigned_tech_name ?? "Unassigned"}
                  </p>
                  <div className="field">
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
                  <button type="submit">Reassign</button>
                </AjaxForm>
              </ModalTrigger>

              {!ticket.is_escalated && (
                <ModalTrigger label="Escalate" title="Escalate ticket" buttonClassName="secondary">
                  <AjaxForm action={submitEscalate} successMessage="Ticket escalated." resetOnSuccess={false}>
                    <p className="muted">
                      Raises priority a level and notifies the rest of the assigned team.
                    </p>
                    <div className="field">
                      <label htmlFor="reason">Reason (optional)</label>
                      <textarea id="reason" name="reason" rows={2} />
                    </div>
                    <button type="submit">Escalate</button>
                  </AjaxForm>
                </ModalTrigger>
              )}
            </div>
          )}
        </div>
        <p>
          <StatusBadge status={ticket.status} /> <PriorityBadge priority={ticket.priority} />
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

      {ticket.approval_status && (isTech || isManager) && (
        <div className="card">
          <h2>Approval</h2>
          {ticket.approval_status === "pending" ? (
            isManager ? (
              <>
                <p className="muted">This request needs your approval before IT can act on it.</p>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                  <AjaxForm action={submitApprove} successMessage="Request approved.">
                    <div className="field">
                      <textarea name="note" rows={2} placeholder="Note (optional)" />
                    </div>
                    <button type="submit">Approve</button>
                  </AjaxForm>
                  <AjaxForm action={submitReject} successMessage="Request rejected.">
                    <div className="field">
                      <textarea name="note" rows={2} placeholder="Reason (optional)" />
                    </div>
                    <ConfirmSubmitButton
                      className="secondary"
                      message="Reject this request? The requester and technician will be notified."
                    >
                      Reject
                    </ConfirmSubmitButton>
                  </AjaxForm>
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

      <div className="card">
        <h2>Activity</h2>
        <Timeline entries={timeline} />

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
        <AjaxForm action={submitReply} successMessage="Reply sent.">
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
        </AjaxForm>
      </div>

      {isTech && (
        <div className="card">
          <h2>Add internal note</h2>
          <p className="muted">Visible to technicians only — already included in the timeline above.</p>
          <AjaxForm action={submitNote} successMessage="Note added.">
            <div className="field">
              <textarea name="note" rows={3} placeholder="Add an internal note..." />
            </div>
            <button type="submit" className="secondary">
              Add note
            </button>
          </AjaxForm>
        </div>
      )}
    </main>
  );
}

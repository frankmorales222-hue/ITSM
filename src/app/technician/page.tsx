// Technician queue — tickets assigned to the current tech, grouped and
// counted by status. "Current tech" is the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { getSessionUserId } from "@/lib/auth";
import { bulkUpdateStatus } from "@/lib/tickets";
import { isOverdue } from "@/lib/sla";
import Nav from "@/components/Nav";
import ConfirmBulkStatusButton from "@/components/ConfirmBulkStatusButton";
import {
  STATUSES,
  buildTicketWhere,
  buildFilterQueryString,
  getActiveCategories,
  type TicketFilters,
} from "@/lib/ticket-filters";

const PAGE_SIZE = 20;

async function getAssignedTickets(userId: string, filters: TicketFilters, page: number) {
  const offset = (page - 1) * PAGE_SIZE;
  const { where, params } = buildTicketWhere("assigned_tech_id", userId, filters);

  const countResult = await pool.query(
    `SELECT count(*)::int AS total FROM tickets WHERE ${where}`,
    params
  );
  const total = countResult.rows[0].total;

  const listParams = [...params, PAGE_SIZE, offset];
  const result = await pool.query(
    `SELECT t.*, c.name AS category_name
     FROM tickets t
     LEFT JOIN categories c ON c.id = t.category_id
     WHERE ${where}
     ORDER BY t.created_at DESC
     LIMIT $${listParams.length - 1} OFFSET $${listParams.length}`,
    listParams
  );

  return { tickets: result.rows, total };
}

async function getStatusCounts(userId: string) {
  const result = await pool.query(
    `SELECT status, count(*)::int AS n FROM tickets WHERE assigned_tech_id = $1 GROUP BY status`,
    [userId]
  );
  return result.rows as { status: string; n: number }[];
}

export default async function TechnicianPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; category?: string; q?: string; page?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const { status, category, q, page: pageParam } = await searchParams;
  const filters: TicketFilters = { status, category, q };
  const page = Math.max(1, Number(pageParam) || 1);
  const [{ tickets, total }, counts, categories] = await Promise.all([
    getAssignedTickets(userId, filters, page),
    getStatusCounts(userId),
    getActiveCategories(),
  ]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const query = buildFilterQueryString(filters);
  const currentUrl = `/technician?page=${page}${query}`;

  async function submitBulkStatus(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId) {
      redirect("/login");
    }
    const ticketIds = formData.getAll("ticketIds").map(String);
    const newStatus = String(formData.get("bulkStatus") ?? "");
    if (ticketIds.length > 0 && newStatus) {
      await bulkUpdateStatus({ ticketIds, status: newStatus, actorId });
    }
    redirect(currentUrl);
  }

  return (
    <main>
      <Nav userId={userId} />

      <h1>Technician Queue</h1>

      <div className="status-groups">
        {counts.map((c) => (
          <a key={c.status} className="status-group" href={`/technician?status=${c.status}`}>
            <strong>{c.status}</strong>: {c.n}
          </a>
        ))}
      </div>

      <form method="GET" style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div className="field" style={{ maxWidth: 240, marginBottom: 0 }}>
          <label htmlFor="q">Search</label>
          <input id="q" name="q" defaultValue={q ?? ""} placeholder="Subject or description" />
        </div>
        <div className="field" style={{ maxWidth: 200, marginBottom: 0 }}>
          <label htmlFor="status">Status</label>
          <select id="status" name="status" defaultValue={status ?? ""}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ maxWidth: 200, marginBottom: 0 }}>
          <label htmlFor="category">Category</label>
          <select id="category" name="category" defaultValue={category ?? ""}>
            <option value="">All</option>
            {categories.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="secondary">
          Apply
        </button>
      </form>

      {tickets.length === 0 && <p className="muted">Nothing matches.</p>}
      {tickets.length > 0 && (
        <form action={submitBulkStatus}>
          <div
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              margin: "12px 0",
            }}
          >
            <label htmlFor="bulkStatus" className="muted">
              Set status for selected:
            </label>
            <select id="bulkStatus" name="bulkStatus" defaultValue="" style={{ maxWidth: 200 }}>
              <option value="" disabled>
                Choose status
              </option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <ConfirmBulkStatusButton />
          </div>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Number</th>
                <th>Subject</th>
                <th>Category</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Due</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((t: any) => (
                <tr key={t.id}>
                  <td>
                    <input type="checkbox" name="ticketIds" value={t.id} />
                  </td>
                  <td>
                    <a href={`/tickets/${t.id}`}>{t.ticket_number}</a>
                  </td>
                  <td>
                    {t.subject}
                    {t.is_escalated && (
                      <>
                        {" "}
                        <span className="badge badge-overdue">Escalated</span>
                      </>
                    )}
                    {t.approval_status === "pending" && (
                      <>
                        {" "}
                        <span className="badge badge-overdue">Awaiting approval</span>
                      </>
                    )}
                  </td>
                  <td className="muted">{t.category_name ?? "—"}</td>
                  <td>
                    <span className="badge">{t.status}</span>
                  </td>
                  <td>{t.priority}</td>
                  <td>
                    {t.due_at ? (
                      isOverdue(t) ? (
                        <span className="badge badge-overdue">Overdue</span>
                      ) : (
                        new Date(t.due_at).toLocaleString()
                      )
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </form>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          {page > 1 && <a href={`/technician?page=${page - 1}${query}`}>&larr; Prev</a>}
          <span className="muted">
            Page {page} of {totalPages}
          </span>
          {page < totalPages && <a href={`/technician?page=${page + 1}${query}`}>Next &rarr;</a>}
        </div>
      )}
    </main>
  );
}

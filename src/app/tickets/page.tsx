import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/auth";
import { pool } from "@/lib/db";

const PAGE_SIZE = 20;

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

async function getTickets(userId: string, status: string | undefined, page: number) {
  const offset = (page - 1) * PAGE_SIZE;
  const params: any[] = [userId];
  let where = `requester_id = $1`;
  if (status) {
    params.push(status);
    where += ` AND status = $${params.length}`;
  }

  const countResult = await pool.query(
    `SELECT count(*)::int AS total FROM tickets WHERE ${where}`,
    params
  );
  const total = countResult.rows[0].total;

  params.push(PAGE_SIZE, offset);
  const result = await pool.query(
    `SELECT * FROM tickets WHERE ${where} ORDER BY created_at DESC LIMIT $${params.length - 1} OFFSET $${params.length}`,
    params
  );

  return { tickets: result.rows, total };
}

export default async function TicketsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; page?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const { status, page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);
  const { tickets, total } = await getTickets(userId, status, page);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const query = status ? `&status=${status}` : "";

  return (
    <main>
      <nav className="nav">
        <a href="/tickets/new">Report a problem</a>
        <a href="/technician">Technician queue</a>
        <form action="/api/auth/logout" method="POST" className="form-inline">
          <button type="submit" className="secondary">
            Log out
          </button>
        </form>
      </nav>

      <h1>My Requests</h1>

      <form method="GET" className="field" style={{ maxWidth: 220 }}>
        <label htmlFor="status">Filter by status</label>
        <select id="status" name="status" defaultValue={status ?? ""}>
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button type="submit" className="secondary" style={{ marginTop: 8 }}>
          Apply
        </button>
      </form>

      {tickets.length === 0 && <p className="muted">No requests yet.</p>}
      {tickets.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Number</th>
              <th>Subject</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t: any) => (
              <tr key={t.id}>
                <td>
                  <a href={`/tickets/${t.id}`}>{t.ticket_number}</a>
                </td>
                <td>{t.subject}</td>
                <td>
                  <span className="badge">{t.status}</span>
                </td>
                <td>{t.priority}</td>
                <td>{new Date(t.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {totalPages > 1 && (
        <div className="pagination">
          {page > 1 && <a href={`/tickets?page=${page - 1}${query}`}>&larr; Prev</a>}
          <span className="muted">
            Page {page} of {totalPages}
          </span>
          {page < totalPages && <a href={`/tickets?page=${page + 1}${query}`}>Next &rarr;</a>}
        </div>
      )}
    </main>
  );
}

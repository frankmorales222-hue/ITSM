// Technician queue — tickets assigned to the current tech, grouped and
// counted by status. "Current tech" is the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { getSessionUserId } from "@/lib/auth";

const PAGE_SIZE = 20;

async function getAssignedTickets(userId: string, status: string | undefined, page: number) {
  const offset = (page - 1) * PAGE_SIZE;
  const params: any[] = [userId];
  let where = `assigned_tech_id = $1`;
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
  searchParams: Promise<{ status?: string; page?: string }>;
}) {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const { status, page: pageParam } = await searchParams;
  const page = Math.max(1, Number(pageParam) || 1);
  const [{ tickets, total }, counts] = await Promise.all([
    getAssignedTickets(userId, status, page),
    getStatusCounts(userId),
  ]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const query = status ? `&status=${status}` : "";

  return (
    <main>
      <nav className="nav">
        <a href="/tickets">&larr; My Requests</a>
      </nav>

      <h1>Technician Queue</h1>

      <div className="status-groups">
        {counts.map((c) => (
          <a key={c.status} className="status-group" href={`/technician?status=${c.status}`}>
            <strong>{c.status}</strong>: {c.n}
          </a>
        ))}
      </div>

      {tickets.length === 0 && <p className="muted">Nothing assigned to you.</p>}
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

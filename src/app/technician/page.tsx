// Technician queue — tickets assigned to the current tech, grouped and
// counted by status. "Current tech" is the session user.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { getSessionUserId } from "@/lib/auth";

async function getAssignedTickets(userId: string) {
  const result = await pool.query(
    `SELECT * FROM tickets WHERE assigned_tech_id = $1 ORDER BY created_at DESC`,
    [userId]
  );
  return result.rows;
}

export default async function TechnicianPage() {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  const tickets = await getAssignedTickets(userId);

  const byStatus = new Map<string, any[]>();
  for (const t of tickets) {
    const list = byStatus.get(t.status) ?? [];
    list.push(t);
    byStatus.set(t.status, list);
  }

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <p>
        <a href="/tickets">&larr; My Requests</a>
      </p>
      <h1>Technician Queue</h1>
      {tickets.length === 0 && <p>Nothing assigned to you.</p>}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
        {[...byStatus.entries()].map(([status, list]) => (
          <div
            key={status}
            style={{ border: "1px solid #ccc", borderRadius: 4, padding: "8px 12px" }}
          >
            <strong>{status}</strong>: {list.length}
          </div>
        ))}
      </div>

      {[...byStatus.entries()].map(([status, list]) => (
        <section key={status} style={{ marginBottom: 24 }}>
          <h2>{status}</h2>
          <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
                <th>Number</th>
                <th>Subject</th>
                <th>Priority</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {list.map((t: any) => (
                <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
                  <td>
                    <a href={`/tickets/${t.id}`}>{t.ticket_number}</a>
                  </td>
                  <td>{t.subject}</td>
                  <td>{t.priority}</td>
                  <td>{new Date(t.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </main>
  );
}

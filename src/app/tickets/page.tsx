import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/auth";
import { pool } from "@/lib/db";

async function getTickets(userId: string) {
  const result = await pool.query(
    `SELECT * FROM tickets WHERE requester_id = $1 ORDER BY created_at DESC`,
    [userId]
  );
  return result.rows;
}

export default async function TicketsPage() {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  const tickets = await getTickets(userId);

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>My Requests</h1>
      <p>
        <a href="/tickets/new">Report a problem</a> &nbsp;|&nbsp;{" "}
        <a href="/technician">Technician queue</a> &nbsp;|&nbsp;{" "}
        <form action="/api/auth/logout" method="POST" style={{ display: "inline" }}>
          <button type="submit">Log out</button>
        </form>
      </p>
      {tickets.length === 0 && <p>No requests yet.</p>}
      <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Number</th>
            <th>Subject</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t: any) => (
            <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>
                <a href={`/tickets/${t.id}`}>{t.ticket_number}</a>
              </td>
              <td>{t.subject}</td>
              <td>{t.status}</td>
              <td>{t.priority}</td>
              <td>{new Date(t.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

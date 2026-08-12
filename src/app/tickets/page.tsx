// Minimal "My Requests" list. Auth/session wiring is intentionally not
// included yet — replace the hardcoded userId with your session's user
// once auth is in place.

async function getTickets(userId: string) {
  const res = await fetch(
    `${process.env.NEXT_PUBLIC_APP_URL}/api/tickets?userId=${userId}&role=employee`,
    { cache: "no-store" }
  );
  const data = await res.json();
  return data.tickets ?? [];
}

export default async function TicketsPage() {
  const userId = process.env.DEV_USER_ID ?? "";
  const tickets = userId ? await getTickets(userId) : [];

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif" }}>
      <h1>My Requests</h1>
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
              <td>{t.ticket_number}</td>
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

import { redirect, notFound } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import {
  getSummaryStats,
  getAvgResolutionHours,
  getStatusBreakdown,
  getPriorityBreakdown,
  getCategoryBreakdown,
  getTechnicianWorkload,
} from "@/lib/reports";
import Nav from "@/components/Nav";

function formatHours(hours: number | null): string {
  if (hours === null) return "—";
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

export default async function ReportsPage() {
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }
  if (!(await isTechnician(sessionUserId))) {
    notFound();
  }

  const [summary, avgResolutionHours, statusBreakdown, priorityBreakdown, categoryBreakdown, workload] =
    await Promise.all([
      getSummaryStats(),
      getAvgResolutionHours(),
      getStatusBreakdown(),
      getPriorityBreakdown(),
      getCategoryBreakdown(),
      getTechnicianWorkload(),
    ]);

  return (
    <main>
      <Nav userId={sessionUserId} />

      <h1>Reports</h1>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
        <div className="card" style={{ flex: "1 1 160px" }}>
          <div className="muted">Open tickets</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.open_count}</div>
        </div>
        <div className="card" style={{ flex: "1 1 160px" }}>
          <div className="muted">Overdue</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: "var(--color-danger)" }}>
            {summary.overdue_count}
          </div>
        </div>
        <div className="card" style={{ flex: "1 1 160px" }}>
          <div className="muted">Resolved (7d)</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.resolved_this_week}</div>
        </div>
        <div className="card" style={{ flex: "1 1 160px" }}>
          <div className="muted">Created (7d)</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.created_this_week}</div>
        </div>
        <div className="card" style={{ flex: "1 1 160px" }}>
          <div className="muted">Avg. resolution time</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>{formatHours(avgResolutionHours)}</div>
        </div>
      </div>

      <div className="card">
        <h2>By status</h2>
        <table>
          <tbody>
            {statusBreakdown.map((row) => (
              <tr key={row.status}>
                <td>
                  <span className="badge">{row.status}</span>
                </td>
                <td>{row.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>By priority</h2>
        <table>
          <tbody>
            {priorityBreakdown.map((row) => (
              <tr key={row.priority}>
                <td>{row.priority}</td>
                <td>{row.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>By category</h2>
        <table>
          <tbody>
            {categoryBreakdown.map((row) => (
              <tr key={row.category}>
                <td>{row.category}</td>
                <td>{row.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Open tickets per technician</h2>
        {workload.length === 0 && <p className="muted">No open tickets are currently assigned.</p>}
        {workload.length > 0 && (
          <table>
            <tbody>
              {workload.map((row) => (
                <tr key={row.display_name}>
                  <td>{row.display_name}</td>
                  <td>{row.open_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}

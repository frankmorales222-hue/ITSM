import { redirect } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import {
  ALL_WIDGETS,
  DEFAULT_ORDER,
  getWidgetOrder,
  setWidgetOrder,
  getMyOpenCount,
  getMyOverdueCount,
  getRecentActivity,
} from "@/lib/dashboard";
import { getTechnicianWorkload } from "@/lib/reports";
import { getNotificationsForUser, EVENT_LABELS } from "@/lib/notifications";
import Nav from "@/components/Nav";
import ModalTrigger from "@/components/Modal";
import DashboardCustomizer from "@/components/DashboardCustomizer";
import { StatusBadge } from "@/components/StatusBadge";

export default async function DashboardPage() {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }
  const isTech = await isTechnician(userId);

  const availableWidgets = ALL_WIDGETS.filter((w) => !w.techOnly || isTech);
  const availableKeys = new Set(availableWidgets.map((w) => w.key));

  const storedOrder = await getWidgetOrder(userId);
  // Anything the user hasn't seen yet (new widget, or tech-only widget
  // that just became available) still shows up in the customizer, tacked
  // onto the end rather than silently missing.
  const fullOrderForCustomizer = [
    ...storedOrder.filter((k) => availableKeys.has(k)),
    ...DEFAULT_ORDER.filter((k) => availableKeys.has(k) && !storedOrder.includes(k)),
  ];
  const visibleOrder = storedOrder.filter((k) => availableKeys.has(k));

  const [myOpenCount, overdueCount, recentActivity, workload, notifications] = await Promise.all([
    visibleOrder.includes("my_open") ? getMyOpenCount(userId, isTech) : Promise.resolve(0),
    visibleOrder.includes("overdue") ? getMyOverdueCount(userId, isTech) : Promise.resolve(0),
    visibleOrder.includes("recent_activity") ? getRecentActivity(userId, isTech) : Promise.resolve([]),
    visibleOrder.includes("team_workload") && isTech ? getTechnicianWorkload() : Promise.resolve([]),
    visibleOrder.includes("notifications") ? getNotificationsForUser(userId, 5) : Promise.resolve([]),
  ]);

  async function submitCustomize(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId) {
      redirect("/login");
    }
    let order: string[];
    try {
      order = JSON.parse(String(formData.get("order") ?? "[]"));
    } catch {
      return { error: "Something went wrong saving that." };
    }
    if (!Array.isArray(order) || !order.every((v) => typeof v === "string")) {
      return { error: "Something went wrong saving that." };
    }
    await setWidgetOrder(actorId, order);
  }

  const widgetContent: Record<string, React.ReactNode> = {
    my_open: (
      <div className="card stat-tile">
        <div className="muted">My open tickets</div>
        <div className="stat-value">{myOpenCount}</div>
      </div>
    ),
    overdue: (
      <div className="card stat-tile">
        <div className="muted">Overdue</div>
        <div className="stat-value" style={{ color: "var(--color-danger)" }}>
          {overdueCount}
        </div>
      </div>
    ),
    recent_activity: (
      <div className="card">
        <h2>Recent activity</h2>
        {recentActivity.length === 0 && <p className="muted">Nothing yet.</p>}
        {recentActivity.map((t: any) => (
          <div key={t.id} className="reply" style={{ padding: "8px 0" }}>
            <a href={`/tickets/${t.id}`}>
              {t.ticket_number}: {t.subject}
            </a>{" "}
            <StatusBadge status={t.status} />
          </div>
        ))}
      </div>
    ),
    team_workload: isTech ? (
      <div className="card">
        <h2>Team workload</h2>
        {workload.length === 0 && <p className="muted">No open tickets are currently assigned.</p>}
        {workload.map((row: any) => (
          <div key={row.display_name} className="reply" style={{ padding: "8px 0" }}>
            {row.display_name} <span className="muted">— {row.open_count} open</span>
          </div>
        ))}
      </div>
    ) : null,
    notifications: (
      <div className="card">
        <h2>Notifications</h2>
        {notifications.length === 0 && <p className="muted">No notifications yet.</p>}
        {notifications.map((n: any) => (
          <div key={n.id} className="reply" style={{ padding: "8px 0", opacity: n.read_at ? 0.6 : 1 }}>
            <a href={`/tickets/${n.ticket_id}`}>
              {EVENT_LABELS[n.event as keyof typeof EVENT_LABELS] ?? n.event} &middot; {n.ticket_number}
            </a>
          </div>
        ))}
        <p style={{ marginTop: 8 }}>
          <a href="/notifications">See all</a>
        </p>
      </div>
    ),
  };

  return (
    <main>
      <Nav userId={userId} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Dashboard</h1>
        <ModalTrigger label="Customize" title="Customize dashboard" buttonClassName="secondary">
          <DashboardCustomizer
            widgets={availableWidgets}
            initialOrder={fullOrderForCustomizer}
            initialVisible={visibleOrder}
            action={submitCustomize}
          />
        </ModalTrigger>
      </div>

      <div className="widget-grid">
        {visibleOrder.map((key) => (
          <div key={key}>{widgetContent[key]}</div>
        ))}
      </div>
      {visibleOrder.length === 0 && (
        <p className="muted">All widgets are hidden — use Customize to add some back.</p>
      )}
    </main>
  );
}

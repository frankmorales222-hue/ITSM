import { redirect } from "next/navigation";
import { getSessionUserId } from "@/lib/auth";
import {
  getNotificationsForUser,
  markNotificationRead,
  markAllNotificationsRead,
  EVENT_LABELS,
} from "@/lib/notifications";
import Nav from "@/components/Nav";

export default async function NotificationsPage() {
  const userId = await getSessionUserId();
  if (!userId) {
    redirect("/login");
  }

  const notifications = await getNotificationsForUser(userId);

  async function submitMarkRead(formData: FormData) {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId) {
      redirect("/login");
    }
    const notificationId = String(formData.get("notificationId") ?? "");
    if (notificationId) {
      await markNotificationRead(notificationId, actorId);
    }
    redirect("/notifications");
  }

  async function submitMarkAllRead() {
    "use server";
    const actorId = await getSessionUserId();
    if (!actorId) {
      redirect("/login");
    }
    await markAllNotificationsRead(actorId);
    redirect("/notifications");
  }

  return (
    <main>
      <Nav userId={userId} />

      <h1>Notifications</h1>

      {notifications.some((n: any) => !n.read_at) && (
        <form action={submitMarkAllRead} style={{ marginBottom: 16 }}>
          <button type="submit" className="secondary">
            Mark all as read
          </button>
        </form>
      )}

      {notifications.length === 0 && <p className="muted">No notifications yet.</p>}

      {notifications.map((n: any) => (
        <div key={n.id} className="card" style={{ opacity: n.read_at ? 0.65 : 1 }}>
          <p style={{ margin: 0 }}>
            {!n.read_at && <span className="badge badge-overdue">New</span>}{" "}
            <strong>{EVENT_LABELS[n.event as keyof typeof EVENT_LABELS] ?? n.event}</strong> &middot;{" "}
            <a href={`/tickets/${n.ticket_id}`}>
              {n.ticket_number}: {n.subject}
            </a>
          </p>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            {new Date(n.created_at).toLocaleString()}
          </p>
          {!n.read_at && (
            <form action={submitMarkRead} style={{ marginTop: 8 }}>
              <input type="hidden" name="notificationId" value={n.id} />
              <button type="submit" className="secondary">
                Mark as read
              </button>
            </form>
          )}
        </div>
      ))}
    </main>
  );
}

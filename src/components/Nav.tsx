import { isTechnician } from "@/lib/auth";
import { getUnreadNotificationCount } from "@/lib/notifications";

// Single shared sidebar for every authenticated page, so navigation and the
// notifications badge are consistent instead of each page hand-rolling its
// own subset of links. Rendered as a fixed sidebar via CSS (see .sidebar in
// globals.css) regardless of where it sits in the DOM, so every page can
// keep rendering <Nav> as its first child without needing a shared
// layout.tsx wrapping every route.
export default async function Nav({ userId }: { userId: string }) {
  const [isTech, unreadCount] = await Promise.all([
    isTechnician(userId),
    getUnreadNotificationCount(userId),
  ]);

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">IT Support</div>

      <a href="/dashboard">Dashboard</a>
      <a href="/tickets">My Requests</a>
      <a href="/tickets/new">Report a problem</a>
      <a href="/kb">Knowledge Base</a>
      <a href="/notifications">
        Notifications
        {unreadCount > 0 && <span className="sidebar-badge">{unreadCount}</span>}
      </a>

      {isTech && (
        <>
          <div className="sidebar-section">Technician</div>
          <a href="/technician">Technician Queue</a>
          <a href="/reports">Reports</a>
          <a href="/technician/users">Users without a password</a>
          <a href="/admin">Admin</a>
        </>
      )}

      <div className="sidebar-footer">
        <form action="/api/auth/logout" method="POST">
          <button type="submit" className="secondary">
            Log out
          </button>
        </form>
      </div>
    </nav>
  );
}

import { isTechnician } from "@/lib/auth";
import { getUnreadNotificationCount } from "@/lib/notifications";

// Single shared header for every authenticated page, so navigation and the
// notifications badge are consistent instead of each page hand-rolling its
// own subset of links.
export default async function Nav({ userId }: { userId: string }) {
  const [isTech, unreadCount] = await Promise.all([
    isTechnician(userId),
    getUnreadNotificationCount(userId),
  ]);

  return (
    <nav className="nav">
      <a href="/tickets">My Requests</a>
      <a href="/tickets/new">Report a problem</a>
      <a href="/kb">Knowledge Base</a>
      {isTech && <a href="/technician">Technician Queue</a>}
      {isTech && <a href="/reports">Reports</a>}
      {isTech && <a href="/technician/users">Users without a password</a>}
      {isTech && <a href="/admin">Admin</a>}
      <a href="/notifications">Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}</a>
      <form action="/api/auth/logout" method="POST" className="form-inline">
        <button type="submit" className="secondary">
          Log out
        </button>
      </form>
    </nav>
  );
}

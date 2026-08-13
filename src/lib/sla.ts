// Response-time targets by priority. No external spec for phase 1 — chosen
// to be directionally sane (critical fastest, low slowest) and easy to
// tune later without touching call sites.
const SLA_HOURS: Record<string, number> = {
  critical: 4,
  high: 8,
  medium: 24,
  normal: 48,
  low: 72,
};

export function calculateDueAt(priority: string, from: Date = new Date()): Date {
  const hours = SLA_HOURS[priority] ?? SLA_HOURS.normal;
  return new Date(from.getTime() + hours * 60 * 60 * 1000);
}

const OPEN_STATUSES = new Set([
  "open",
  "assigned",
  "in_progress",
  "waiting_on_you",
  "waiting_on_vendor",
  "on_hold",
  "pending_verification",
]);

export function isOverdue(ticket: { due_at: string | Date | null; status: string }): boolean {
  if (!ticket.due_at || !OPEN_STATUSES.has(ticket.status)) {
    return false;
  }
  return new Date(ticket.due_at).getTime() < Date.now();
}

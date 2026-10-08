import { pool } from "./db";

export interface WidgetDef {
  key: string;
  label: string;
  techOnly?: boolean;
}

export const ALL_WIDGETS: WidgetDef[] = [
  { key: "my_open", label: "My open tickets" },
  { key: "overdue", label: "Overdue" },
  { key: "recent_activity", label: "Recent activity" },
  { key: "team_workload", label: "Team workload", techOnly: true },
  { key: "notifications", label: "Notifications" },
];

export const DEFAULT_ORDER = ALL_WIDGETS.map((w) => w.key);

// The stored array can contain stale keys (a widget that no longer
// exists) or be missing newly-added ones — always intersect with
// ALL_WIDGETS and fall back to the default for anything unset.
export async function getWidgetOrder(userId: string): Promise<string[]> {
  const result = await pool.query(`SELECT dashboard_widgets FROM users WHERE id = $1`, [userId]);
  const stored = result.rows[0]?.dashboard_widgets as string[] | null;
  if (!stored || stored.length === 0) {
    return DEFAULT_ORDER;
  }
  const validKeys = new Set(ALL_WIDGETS.map((w) => w.key));
  return stored.filter((k) => validKeys.has(k));
}

export async function setWidgetOrder(userId: string, order: string[]): Promise<void> {
  const validKeys = new Set(ALL_WIDGETS.map((w) => w.key));
  const cleaned = order.filter((k) => validKeys.has(k));
  await pool.query(`UPDATE users SET dashboard_widgets = $1 WHERE id = $2`, [cleaned, userId]);
}

const OPEN_STATUSES_SQL = `('resolved', 'closed', 'cancelled')`;

export async function getMyOpenCount(userId: string, isTech: boolean): Promise<number> {
  const column = isTech ? "assigned_tech_id" : "requester_id";
  const result = await pool.query(
    `SELECT count(*)::int AS n FROM tickets WHERE ${column} = $1 AND status NOT IN ${OPEN_STATUSES_SQL}`,
    [userId]
  );
  return result.rows[0].n;
}

export async function getMyOverdueCount(userId: string, isTech: boolean): Promise<number> {
  const column = isTech ? "assigned_tech_id" : "requester_id";
  const result = await pool.query(
    `SELECT count(*)::int AS n FROM tickets
     WHERE ${column} = $1 AND status NOT IN ${OPEN_STATUSES_SQL} AND due_at < now()`,
    [userId]
  );
  return result.rows[0].n;
}

export async function getRecentActivity(userId: string, isTech: boolean, limit = 5) {
  const column = isTech ? "assigned_tech_id" : "requester_id";
  const result = await pool.query(
    `SELECT id, ticket_number, subject, status, updated_at
     FROM tickets
     WHERE ${column} = $1
     ORDER BY updated_at DESC
     LIMIT $2`,
    [userId, limit]
  );
  return result.rows;
}

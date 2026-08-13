import { pool } from "./db";

const OPEN_STATUSES_SQL = `('resolved', 'closed', 'cancelled')`;

export async function getSummaryStats() {
  const result = await pool.query(`
    SELECT
      count(*) FILTER (WHERE status NOT IN ${OPEN_STATUSES_SQL})::int AS open_count,
      count(*) FILTER (WHERE due_at < now() AND status NOT IN ${OPEN_STATUSES_SQL})::int AS overdue_count,
      count(*) FILTER (WHERE resolved_at >= now() - interval '7 days')::int AS resolved_this_week,
      count(*) FILTER (WHERE created_at >= now() - interval '7 days')::int AS created_this_week
    FROM tickets
  `);
  return result.rows[0] as {
    open_count: number;
    overdue_count: number;
    resolved_this_week: number;
    created_this_week: number;
  };
}

export async function getAvgResolutionHours(): Promise<number | null> {
  const result = await pool.query(`
    SELECT avg(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600) AS avg_hours
    FROM tickets
    WHERE resolved_at IS NOT NULL
  `);
  const avg = result.rows[0].avg_hours;
  return avg === null ? null : Number(avg);
}

export async function getStatusBreakdown() {
  const result = await pool.query(
    `SELECT status, count(*)::int AS n FROM tickets GROUP BY status ORDER BY n DESC`
  );
  return result.rows as { status: string; n: number }[];
}

export async function getPriorityBreakdown() {
  const result = await pool.query(
    `SELECT priority, count(*)::int AS n FROM tickets GROUP BY priority ORDER BY n DESC`
  );
  return result.rows as { priority: string; n: number }[];
}

export async function getCategoryBreakdown() {
  const result = await pool.query(`
    SELECT COALESCE(c.name, 'Uncategorized') AS category, count(*)::int AS n
    FROM tickets t
    LEFT JOIN categories c ON c.id = t.category_id
    GROUP BY c.name
    ORDER BY n DESC
  `);
  return result.rows as { category: string; n: number }[];
}

export async function getTechnicianWorkload() {
  const result = await pool.query(`
    SELECT u.display_name, count(*)::int AS open_count
    FROM tickets t
    JOIN users u ON u.id = t.assigned_tech_id
    WHERE t.status NOT IN ${OPEN_STATUSES_SQL}
    GROUP BY u.display_name
    ORDER BY open_count DESC
  `);
  return result.rows as { display_name: string; open_count: number }[];
}

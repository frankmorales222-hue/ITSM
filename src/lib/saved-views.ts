import { pool } from "./db";
import type { TicketFilters } from "./ticket-filters";

export type ViewPage = "tickets" | "technician";

export async function createSavedView({
  userId,
  page,
  name,
  filters,
}: {
  userId: string;
  page: ViewPage;
  name: string;
  filters: TicketFilters;
}) {
  await pool.query(
    `INSERT INTO saved_views (user_id, page, name, filters) VALUES ($1, $2, $3, $4)`,
    [userId, page, name, JSON.stringify(filters)]
  );
}

export async function getSavedViews(userId: string, page: ViewPage) {
  const result = await pool.query(
    `SELECT id, name, filters FROM saved_views WHERE user_id = $1 AND page = $2 ORDER BY created_at ASC`,
    [userId, page]
  );
  return result.rows as { id: string; name: string; filters: TicketFilters }[];
}

export async function deleteSavedView(id: string, userId: string) {
  await pool.query(`DELETE FROM saved_views WHERE id = $1 AND user_id = $2`, [id, userId]);
}

import { pool } from "./db";

export const STATUSES = [
  "open",
  "assigned",
  "in_progress",
  "waiting_on_you",
  "waiting_on_vendor",
  "on_hold",
  "pending_verification",
  "resolved",
  "closed",
  "cancelled",
];

export interface TicketFilters {
  status?: string;
  category?: string;
  q?: string;
}

// Shared by /tickets and /technician — same filter set (status, category,
// free-text search over subject/description), just a different base
// ownership column (requester_id vs assigned_tech_id).
export function buildTicketWhere(
  ownerColumn: "requester_id" | "assigned_tech_id",
  ownerId: string,
  filters: TicketFilters
): { where: string; params: any[] } {
  const params: any[] = [ownerId];
  let where = `${ownerColumn} = $1`;

  if (filters.status) {
    params.push(filters.status);
    where += ` AND status = $${params.length}`;
  }
  if (filters.category) {
    params.push(filters.category);
    where += ` AND category_id = $${params.length}`;
  }
  if (filters.q) {
    params.push(`%${filters.q}%`);
    where += ` AND (subject ILIKE $${params.length} OR description ILIKE $${params.length})`;
  }

  return { where, params };
}

export function buildFilterQueryString(filters: TicketFilters): string {
  const parts: string[] = [];
  if (filters.status) parts.push(`status=${encodeURIComponent(filters.status)}`);
  if (filters.category) parts.push(`category=${encodeURIComponent(filters.category)}`);
  if (filters.q) parts.push(`q=${encodeURIComponent(filters.q)}`);
  return parts.length ? `&${parts.join("&")}` : "";
}

export async function getActiveCategories() {
  const result = await pool.query(
    `SELECT id, name FROM categories WHERE is_active = true ORDER BY sort_order`
  );
  return result.rows;
}

export async function getActiveTechnicians() {
  const result = await pool.query(
    `SELECT id, display_name FROM users WHERE is_technician = true AND is_active = true ORDER BY display_name`
  );
  return result.rows;
}

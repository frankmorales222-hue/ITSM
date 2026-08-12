import { cookies } from "next/headers";
import { NextRequest } from "next/server";
import { pool } from "./db";
import { SESSION_COOKIE_NAME, verifySessionCookieValue } from "./session";

// Server Components / Server Actions read cookies via next/headers.
export async function getSessionUserId(): Promise<string | null> {
  const store = await cookies();
  return verifySessionCookieValue(store.get(SESSION_COOKIE_NAME)?.value);
}

// Route Handlers read cookies off the incoming request instead.
export function getSessionUserIdFromRequest(req: NextRequest): string | null {
  return verifySessionCookieValue(req.cookies.get(SESSION_COOKIE_NAME)?.value);
}

// Gates access to technician-only surfaces (internal notes, the technician
// queue). Always check this server-side — never rely on hiding UI alone.
export async function isTechnician(userId: string): Promise<boolean> {
  const result = await pool.query(`SELECT is_technician FROM users WHERE id = $1`, [userId]);
  return result.rows[0]?.is_technician === true;
}

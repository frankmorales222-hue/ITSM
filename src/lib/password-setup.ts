import crypto from "crypto";
import { pool } from "./db";
import { redis } from "./redis";

// Technician-issued, not self-requested: a user typing their own email
// into a "forgot password" form and being handed a working link would be
// account takeover, since we have no way to prove they own that email
// (no outbound mail configured — see README). Instead a technician
// generates the link and relays it out-of-band (Slack, in person,
// whatever's real), the same trust boundary that already lets
// technicians see/act on tickets. Only the token's hash is stored.
const TOKEN_TTL_MS = 1000 * 60 * 60 * 24; // 24 hours

function hashToken(token: string): string {
  return crypto.createHash("sha256").update(token).digest("hex");
}

export async function createSetupToken(userId: string): Promise<string> {
  const token = crypto.randomBytes(32).toString("hex");
  const expiresAt = new Date(Date.now() + TOKEN_TTL_MS);
  await pool.query(
    `UPDATE users SET password_setup_token_hash = $1, password_setup_expires_at = $2 WHERE id = $3`,
    [hashToken(token), expiresAt, userId]
  );
  return token;
}

export async function consumeSetupToken(token: string): Promise<string | null> {
  const result = await pool.query(
    `SELECT id FROM users
     WHERE password_setup_token_hash = $1
       AND password_setup_expires_at > now()
       AND is_active = true`,
    [hashToken(token)]
  );
  return result.rows[0]?.id ?? null;
}

export async function clearSetupToken(userId: string): Promise<void> {
  await pool.query(
    `UPDATE users SET password_setup_token_hash = NULL, password_setup_expires_at = NULL WHERE id = $1`,
    [userId]
  );
}

// Short-lived, single-view handoff so a freshly generated token never has
// to travel through a URL query string (which ends up in browser history
// and server access logs) to get from the server action back to the
// technician's screen. Keyed by the technician's own session id — nothing
// URL-visible to guess.
const REVEAL_TTL_SECONDS = 60;

export async function stashRevealToken(technicianId: string, targetUserId: string, token: string) {
  await redis.set(
    `passwordSetupReveal:${technicianId}`,
    JSON.stringify({ targetUserId, token }),
    "EX",
    REVEAL_TTL_SECONDS
  );
}

export async function takeRevealToken(
  technicianId: string
): Promise<{ targetUserId: string; token: string } | null> {
  const key = `passwordSetupReveal:${technicianId}`;
  const raw = await redis.get(key);
  if (!raw) return null;
  await redis.del(key);
  return JSON.parse(raw);
}

export async function usersWithoutPassword(page = 1, pageSize = 20) {
  const offset = (page - 1) * pageSize;

  const countResult = await pool.query(
    `SELECT count(*)::int AS total FROM users WHERE password_hash IS NULL AND is_active = true`
  );
  const total = countResult.rows[0].total;

  const result = await pool.query(
    `SELECT id, display_name, email,
            password_setup_token_hash IS NOT NULL AND password_setup_expires_at > now() AS has_pending_link
     FROM users
     WHERE password_hash IS NULL AND is_active = true
     ORDER BY display_name
     LIMIT $1 OFFSET $2`,
    [pageSize, offset]
  );
  return { users: result.rows, total };
}

import crypto from "crypto";

// Signed, stateless session cookie: "<userId>.<expiresAtMs>.<hmac>". No
// server-side session store needed for phase 1 — the signature is what
// stops a client from forging or editing a userId, which is the actual
// problem being fixed (routes used to trust a client-supplied userId
// outright).
export const SESSION_COOKIE_NAME = "itsm_session";
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 7; // 7 days
export const SESSION_MAX_AGE_SECONDS = SESSION_TTL_MS / 1000;

function getSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error("SESSION_SECRET is not set");
  }
  return secret;
}

function sign(payload: string): string {
  return crypto.createHmac("sha256", getSecret()).update(payload).digest("hex");
}

export function createSessionCookieValue(userId: string): string {
  const expiresAt = Date.now() + SESSION_TTL_MS;
  const payload = `${userId}.${expiresAt}`;
  return `${payload}.${sign(payload)}`;
}

export function verifySessionCookieValue(value: string | undefined | null): string | null {
  if (!value) return null;

  const parts = value.split(".");
  if (parts.length !== 3) return null;
  const [userId, expiresAtStr, signature] = parts;

  const expected = sign(`${userId}.${expiresAtStr}`);
  const expectedBuf = Buffer.from(expected);
  const actualBuf = Buffer.from(signature);
  if (expectedBuf.length !== actualBuf.length || !crypto.timingSafeEqual(expectedBuf, actualBuf)) {
    return null;
  }

  const expiresAt = Number(expiresAtStr);
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) {
    return null;
  }

  return userId;
}

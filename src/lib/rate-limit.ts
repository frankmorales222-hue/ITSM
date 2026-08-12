import { redis } from "./redis";

// Redis-backed so this holds up across multiple app instances — an
// in-memory Map only rate-limits the process it's running in, which
// defeats the purpose once there's more than one.
const DEFAULT_WINDOW_SECONDS = 60;
const DEFAULT_MAX_ATTEMPTS = 5;

export async function isRateLimited(
  key: string,
  opts: { windowSeconds?: number; maxAttempts?: number } = {}
): Promise<boolean> {
  const windowSeconds = opts.windowSeconds ?? DEFAULT_WINDOW_SECONDS;
  const maxAttempts = opts.maxAttempts ?? DEFAULT_MAX_ATTEMPTS;

  const redisKey = `ratelimit:${key}`;
  const count = await redis.incr(redisKey);
  if (count === 1) {
    await redis.expire(redisKey, windowSeconds);
  }
  return count > maxAttempts;
}

// Shared by the API route and the new-ticket page's server action so the
// policy (and the key format) only lives in one place. Generous compared
// to login — reporting several distinct issues in a short window is
// normal; the point is stopping a scripted flood, not a busy afternoon.
export async function isTicketCreationRateLimited(userId: string): Promise<boolean> {
  return isRateLimited(`ticket-create:${userId}`, { windowSeconds: 300, maxAttempts: 10 });
}

import { redis } from "./redis";

// Redis-backed so this holds up across multiple app instances — an
// in-memory Map only rate-limits the process it's running in, which
// defeats the purpose once there's more than one.
const WINDOW_SECONDS = 60;
const MAX_ATTEMPTS = 5;

export async function isRateLimited(key: string): Promise<boolean> {
  const redisKey = `ratelimit:${key}`;
  const count = await redis.incr(redisKey);
  if (count === 1) {
    await redis.expire(redisKey, WINDOW_SECONDS);
  }
  return count > MAX_ATTEMPTS;
}

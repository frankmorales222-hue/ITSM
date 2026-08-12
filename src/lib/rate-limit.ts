// In-memory rate limiter. Good enough to slow down credential guessing in
// dev/phase-1; it resets on restart and only works within a single
// process, so it won't hold up once this runs behind multiple instances —
// swap for a shared store (Redis, etc.) before then.
const WINDOW_MS = 60_000;
const MAX_ATTEMPTS = 5;

const attempts = new Map<string, { count: number; windowStart: number }>();

export function isRateLimited(key: string): boolean {
  const now = Date.now();
  const entry = attempts.get(key);

  if (!entry || now - entry.windowStart > WINDOW_MS) {
    attempts.set(key, { count: 1, windowStart: now });
    return false;
  }

  entry.count += 1;
  return entry.count > MAX_ATTEMPTS;
}

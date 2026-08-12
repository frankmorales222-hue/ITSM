import Redis from "ioredis";

declare global {
  // eslint-disable-next-line no-var
  var __redis: Redis | undefined;
}

// lazyConnect: this module gets imported during `next build`, which has
// no Redis to connect to — without it, ioredis logs connection-refused
// noise on every build even though nothing actually needed Redis yet.
export const redis =
  global.__redis ??
  new Redis(process.env.REDIS_URL ?? "redis://localhost:6379", { lazyConnect: true });

if (process.env.NODE_ENV !== "production") {
  global.__redis = redis;
}

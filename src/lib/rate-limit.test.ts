import { describe, it, expect, afterAll } from "vitest";
import crypto from "crypto";
import { isRateLimited } from "./rate-limit";
import { redis } from "./redis";

// Runs against a real Redis (see vitest.setup.ts / REDIS_URL) rather than
// mocking the client — the thing worth testing here is the actual
// INCR+EXPIRE behavior, which a mock would just assert back at itself.
describe("isRateLimited", () => {
  afterAll(async () => {
    await redis.quit();
  });

  it("allows the first MAX_ATTEMPTS (5) calls, then blocks", async () => {
    const key = `test:${crypto.randomUUID()}`;
    const results: boolean[] = [];
    for (let i = 0; i < 6; i++) {
      results.push(await isRateLimited(key));
    }
    expect(results).toEqual([false, false, false, false, false, true]);
  });

  it("tracks separate keys independently", async () => {
    const keyA = `test:${crypto.randomUUID()}`;
    const keyB = `test:${crypto.randomUUID()}`;

    for (let i = 0; i < 5; i++) {
      await isRateLimited(keyA);
    }
    expect(await isRateLimited(keyA)).toBe(true);
    expect(await isRateLimited(keyB)).toBe(false);
  });
});

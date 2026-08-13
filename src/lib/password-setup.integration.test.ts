import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createSetupToken, consumeSetupToken, clearSetupToken } from "./password-setup";
import { pool } from "./db";
import { resetTestDb, createTestUser } from "./test-fixtures";

describe("password setup / reset tokens", () => {
  beforeEach(resetTestDb);

  it("round-trips: a fresh token resolves back to its owner", async () => {
    const userId = await createTestUser();
    const token = await createSetupToken(userId);

    expect(await consumeSetupToken(token)).toBe(userId);
  });

  it("rejects a token that was never issued", async () => {
    await createTestUser();
    expect(await consumeSetupToken("not-a-real-token")).toBeNull();
  });

  it("rejects an expired token", async () => {
    const userId = await createTestUser();
    const token = await createSetupToken(userId);
    // createSetupToken always sets a 24h expiry — force it into the past
    // to exercise the expiry check without waiting a day.
    await pool.query(`UPDATE users SET password_setup_expires_at = now() - interval '1 hour' WHERE id = $1`, [
      userId,
    ]);

    expect(await consumeSetupToken(token)).toBeNull();
  });

  it("rejects a token for a deactivated account", async () => {
    const userId = await createTestUser();
    const token = await createSetupToken(userId);
    await pool.query(`UPDATE users SET is_active = false WHERE id = $1`, [userId]);

    expect(await consumeSetupToken(token)).toBeNull();
  });

  it("issuing a new token invalidates the previous one (only one live token per user)", async () => {
    const userId = await createTestUser();
    const firstToken = await createSetupToken(userId);
    const secondToken = await createSetupToken(userId);

    expect(await consumeSetupToken(firstToken)).toBeNull();
    expect(await consumeSetupToken(secondToken)).toBe(userId);
  });

  it("clearSetupToken invalidates a still-valid token", async () => {
    const userId = await createTestUser();
    const token = await createSetupToken(userId);
    await clearSetupToken(userId);

    expect(await consumeSetupToken(token)).toBeNull();
  });
});

afterAll(async () => {
  await pool.end();
});

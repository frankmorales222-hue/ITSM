import { describe, it, expect, beforeEach, afterAll } from "vitest";
import {
  setSetting,
  getSetting,
  deleteSetting,
  isSettingConfigured,
  getAzureAdConfig,
  setAzureAdConfig,
  clearAzureAdConfig,
  getImapConfig,
  setImapConfig,
  clearImapConfig,
} from "./admin-settings";
import { pool } from "./db";
import { resetTestDb, createTestUser } from "./test-fixtures";

describe("admin settings", () => {
  beforeEach(resetTestDb);
  afterAll(async () => {
    await pool.end();
  });

  it("round-trips a value through encryption", async () => {
    const userId = await createTestUser();
    await setSetting("some_key", "super secret value", userId);
    expect(await getSetting("some_key")).toBe("super secret value");
  });

  it("stores ciphertext in the DB, not plaintext", async () => {
    const userId = await createTestUser();
    await setSetting("some_key", "super secret value", userId);
    const row = await pool.query(`SELECT value_encrypted FROM admin_settings WHERE key = $1`, [
      "some_key",
    ]);
    expect(row.rows[0].value_encrypted).not.toContain("super secret value");
  });

  it("returns null for a key that was never set", async () => {
    expect(await getSetting("nope")).toBeNull();
  });

  it("overwrites on a second set", async () => {
    const userId = await createTestUser();
    await setSetting("some_key", "first", userId);
    await setSetting("some_key", "second", userId);
    expect(await getSetting("some_key")).toBe("second");
  });

  it("deleteSetting removes it", async () => {
    const userId = await createTestUser();
    await setSetting("some_key", "value", userId);
    await deleteSetting("some_key");
    expect(await getSetting("some_key")).toBeNull();
  });

  it("isSettingConfigured reflects presence", async () => {
    const userId = await createTestUser();
    expect(await isSettingConfigured("some_key")).toBe(false);
    await setSetting("some_key", "value", userId);
    expect(await isSettingConfigured("some_key")).toBe(true);
  });

  it("Azure AD config is null until all three fields are set", async () => {
    const userId = await createTestUser();
    expect(await getAzureAdConfig()).toBeNull();

    await setAzureAdConfig(
      { tenantId: "tenant-1", clientId: "client-1", clientSecret: "secret-1" },
      userId
    );
    expect(await getAzureAdConfig()).toEqual({
      tenantId: "tenant-1",
      clientId: "client-1",
      clientSecret: "secret-1",
    });

    await clearAzureAdConfig();
    expect(await getAzureAdConfig()).toBeNull();
  });

  it("IMAP config is null until all four fields are set", async () => {
    const userId = await createTestUser();
    expect(await getImapConfig()).toBeNull();

    await setImapConfig(
      { host: "imap.example.com", port: 993, user: "support@example.com", password: "pw" },
      userId
    );
    expect(await getImapConfig()).toEqual({
      host: "imap.example.com",
      port: 993,
      user: "support@example.com",
      password: "pw",
    });

    await clearImapConfig();
    expect(await getImapConfig()).toBeNull();
  });
});

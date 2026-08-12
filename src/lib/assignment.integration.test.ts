import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { assignRoundRobin } from "./assignment";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

describe("assignRoundRobin", () => {
  beforeEach(resetTestDb);
  afterAll(async () => {
    await pool.end();
  });

  it("returns null for a team with no members", async () => {
    const teamId = await createTestTeam();
    expect(await assignRoundRobin(teamId)).toBeNull();
  });

  it("assigns the sole member every time", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);

    expect(await assignRoundRobin(teamId)).toBe(userId);
    expect(await assignRoundRobin(teamId)).toBe(userId);
  });

  it("cycles through members in id order, then wraps around", async () => {
    const teamId = await createTestTeam();
    const userIds = [await createTestUser(), await createTestUser(), await createTestUser()];
    for (const userId of userIds) {
      await addToTeam(teamId, userId);
    }
    const sortedIds = [...userIds].sort();

    const assignments = [
      await assignRoundRobin(teamId),
      await assignRoundRobin(teamId),
      await assignRoundRobin(teamId),
      await assignRoundRobin(teamId), // wraps back to the first
    ];

    expect(assignments).toEqual([sortedIds[0], sortedIds[1], sortedIds[2], sortedIds[0]]);
  });

  it("skips inactive members", async () => {
    const teamId = await createTestTeam();
    const activeUserId = await createTestUser();
    const inactiveUserId = await createTestUser();
    await addToTeam(teamId, activeUserId);
    await addToTeam(teamId, inactiveUserId);
    await pool.query(`UPDATE users SET is_active = false WHERE id = $1`, [inactiveUserId]);

    expect(await assignRoundRobin(teamId)).toBe(activeUserId);
    expect(await assignRoundRobin(teamId)).toBe(activeUserId);
  });
});

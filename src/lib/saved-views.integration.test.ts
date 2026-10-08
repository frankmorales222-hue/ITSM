import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createSavedView, getSavedViews, deleteSavedView } from "./saved-views";
import { pool } from "./db";
import { resetTestDb, createTestUser } from "./test-fixtures";

describe("saved views", () => {
  beforeEach(resetTestDb);

  it("creates and lists a saved view scoped to its page", async () => {
    const userId = await createTestUser();
    await createSavedView({
      userId,
      page: "tickets",
      name: "My open critical tickets",
      filters: { status: "open", category: undefined, q: "critical" },
    });

    const ticketsViews = await getSavedViews(userId, "tickets");
    expect(ticketsViews).toHaveLength(1);
    expect(ticketsViews[0].name).toBe("My open critical tickets");
    expect(ticketsViews[0].filters).toEqual({ status: "open", q: "critical" });

    const technicianViews = await getSavedViews(userId, "technician");
    expect(technicianViews).toHaveLength(0);
  });

  it("scopes views to their owner", async () => {
    const userA = await createTestUser();
    const userB = await createTestUser();
    await createSavedView({ userId: userA, page: "tickets", name: "A's view", filters: {} });

    expect(await getSavedViews(userA, "tickets")).toHaveLength(1);
    expect(await getSavedViews(userB, "tickets")).toHaveLength(0);
  });

  it("deletes a view only for its owner", async () => {
    const userA = await createTestUser();
    const userB = await createTestUser();
    await createSavedView({ userId: userA, page: "tickets", name: "A's view", filters: {} });
    const [view] = await getSavedViews(userA, "tickets");

    await deleteSavedView(view.id, userB);
    expect(await getSavedViews(userA, "tickets")).toHaveLength(1);

    await deleteSavedView(view.id, userA);
    expect(await getSavedViews(userA, "tickets")).toHaveLength(0);
  });
});

afterAll(async () => {
  await pool.end();
});

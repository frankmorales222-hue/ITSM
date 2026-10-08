import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket } from "./tickets";
import {
  ALL_WIDGETS,
  DEFAULT_ORDER,
  getWidgetOrder,
  setWidgetOrder,
  getMyOpenCount,
  getMyOverdueCount,
  getRecentActivity,
} from "./dashboard";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

describe("widget order", () => {
  beforeEach(resetTestDb);

  it("returns the default order for a user who hasn't customized", async () => {
    const userId = await createTestUser();
    expect(await getWidgetOrder(userId)).toEqual(DEFAULT_ORDER);
  });

  it("stores and returns a custom order", async () => {
    const userId = await createTestUser();
    const custom = ["notifications", "my_open"];
    await setWidgetOrder(userId, custom);
    expect(await getWidgetOrder(userId)).toEqual(custom);
  });

  it("drops unknown widget keys when saving", async () => {
    const userId = await createTestUser();
    await setWidgetOrder(userId, ["my_open", "not_a_real_widget"]);
    expect(await getWidgetOrder(userId)).toEqual(["my_open"]);
  });

  it("every widget key is unique and ALL_WIDGETS matches DEFAULT_ORDER", () => {
    const keys = ALL_WIDGETS.map((w) => w.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(DEFAULT_ORDER).toEqual(keys);
  });
});

describe("widget data", () => {
  beforeEach(resetTestDb);

  async function makeAssignedTicket() {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);
    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Dashboard widget test",
      description: "...",
      submissionChannel: "web",
      teamId,
    });
    return { ticket, requesterId, techId };
  }

  it("counts open tickets scoped to requester for a non-technician", async () => {
    const { requesterId, techId } = await makeAssignedTicket();
    expect(await getMyOpenCount(requesterId, false)).toBe(1);
    expect(await getMyOpenCount(techId, false)).toBe(0);
  });

  it("counts open tickets scoped to assignee for a technician", async () => {
    const { techId, requesterId } = await makeAssignedTicket();
    expect(await getMyOpenCount(techId, true)).toBe(1);
    expect(await getMyOpenCount(requesterId, true)).toBe(0);
  });

  it("counts overdue tickets past their due_at", async () => {
    const { ticket, requesterId } = await makeAssignedTicket();
    expect(await getMyOverdueCount(requesterId, false)).toBe(0);

    await pool.query(`UPDATE tickets SET due_at = now() - interval '1 hour' WHERE id = $1`, [ticket.id]);
    expect(await getMyOverdueCount(requesterId, false)).toBe(1);
  });

  it("lists recent activity ordered by most recently updated", async () => {
    const { requesterId } = await makeAssignedTicket();
    const activity = await getRecentActivity(requesterId, false);
    expect(activity).toHaveLength(1);
    expect(activity[0].subject).toBe("Dashboard widget test");
  });
});

afterAll(async () => {
  await pool.end();
});

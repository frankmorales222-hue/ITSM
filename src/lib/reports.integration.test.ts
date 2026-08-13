import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, addReplyAndUpdateStatus } from "./tickets";
import {
  getSummaryStats,
  getAvgResolutionHours,
  getStatusBreakdown,
  getPriorityBreakdown,
  getCategoryBreakdown,
  getTechnicianWorkload,
} from "./reports";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam, getDefaultCategoryId } from "./test-fixtures";

describe("reports", () => {
  beforeEach(resetTestDb);

  async function makeAssignedTicket() {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);
    const categoryId = await getDefaultCategoryId();
    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Report test ticket",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
      impact: "high",
      urgency: "high",
    });
    return { ticket, requesterId, techId };
  }

  it("counts open tickets and excludes resolved/closed/cancelled", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    let summary = await getSummaryStats();
    expect(summary.open_count).toBe(1);

    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "resolved" });
    summary = await getSummaryStats();
    expect(summary.open_count).toBe(0);
    expect(summary.resolved_this_week).toBe(1);
  });

  it("counts overdue tickets whose due_at is in the past and still open", async () => {
    const { ticket } = await makeAssignedTicket();
    await pool.query(`UPDATE tickets SET due_at = now() - interval '1 hour' WHERE id = $1`, [ticket.id]);

    const summary = await getSummaryStats();
    expect(summary.overdue_count).toBe(1);
  });

  it("computes average resolution time in hours", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    await pool.query(
      `UPDATE tickets SET created_at = now() - interval '4 hours' WHERE id = $1`,
      [ticket.id]
    );
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "resolved" });

    const avgHours = await getAvgResolutionHours();
    expect(avgHours).not.toBeNull();
    expect(avgHours!).toBeGreaterThan(3.9);
    expect(avgHours!).toBeLessThan(4.1);
  });

  it("returns null average resolution time when nothing is resolved", async () => {
    await makeAssignedTicket();
    expect(await getAvgResolutionHours()).toBeNull();
  });

  it("breaks down tickets by status", async () => {
    await makeAssignedTicket();
    const breakdown = await getStatusBreakdown();
    expect(breakdown.find((r) => r.status === "assigned")?.n).toBe(1);
  });

  it("breaks down tickets by priority", async () => {
    await makeAssignedTicket();
    const breakdown = await getPriorityBreakdown();
    expect(breakdown.find((r) => r.priority === "critical")?.n).toBe(1);
  });

  it("breaks down tickets by category", async () => {
    await makeAssignedTicket();
    const breakdown = await getCategoryBreakdown();
    expect(breakdown.reduce((sum, r) => sum + r.n, 0)).toBe(1);
    expect(breakdown[0].category).not.toBe("Uncategorized");
  });

  it("reports open-ticket workload per technician", async () => {
    const { techId } = await makeAssignedTicket();
    const workload = await getTechnicianWorkload();
    expect(workload).toHaveLength(1);
    expect(workload[0].open_count).toBe(1);

    const techName = (await pool.query(`SELECT display_name FROM users WHERE id = $1`, [techId])).rows[0]
      .display_name;
    expect(workload[0].display_name).toBe(techName);
  });
});

afterAll(async () => {
  await pool.end();
});

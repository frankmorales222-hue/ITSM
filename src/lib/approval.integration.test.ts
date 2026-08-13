import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, addReplyAndUpdateStatus } from "./tickets";
import { approveTicket, rejectTicket, categoryRequiresApproval } from "./approval";
import { getNotificationsForUser } from "./notifications";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

async function getCategoryId(name: string): Promise<string> {
  const result = await pool.query(`SELECT id FROM categories WHERE name = $1`, [name]);
  return result.rows[0].id;
}

describe("categoryRequiresApproval", () => {
  it("requires approval for Access Request and Equipment Request", () => {
    expect(categoryRequiresApproval("Access Request")).toBe(true);
    expect(categoryRequiresApproval("Equipment Request")).toBe(true);
  });

  it("does not require approval for other categories", () => {
    expect(categoryRequiresApproval("Hardware")).toBe(false);
    expect(categoryRequiresApproval(null)).toBe(false);
    expect(categoryRequiresApproval(undefined)).toBe(false);
  });
});

describe("approval on ticket creation", () => {
  beforeEach(resetTestDb);

  it("sets approval_status to pending for an approval-required category when the requester has a manager", async () => {
    const teamId = await createTestTeam();
    const managerId = await createTestUser();
    const requesterId = await createTestUser({ managerId });
    const categoryId = await getCategoryId("Access Request");

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "New laptop request",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });

    expect(ticket.approval_status).toBe("pending");
  });

  it("skips approval when the category doesn't require it", async () => {
    const teamId = await createTestTeam();
    const managerId = await createTestUser();
    const requesterId = await createTestUser({ managerId });
    const categoryId = await getCategoryId("Hardware");

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Broken laptop",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });

    expect(ticket.approval_status).toBeNull();
  });

  it("skips approval when the requester has no manager on file", async () => {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const categoryId = await getCategoryId("Access Request");

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "New access request",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });

    expect(ticket.approval_status).toBeNull();
  });
});

describe("approveTicket / rejectTicket", () => {
  beforeEach(resetTestDb);

  async function makePendingApprovalTicket() {
    const teamId = await createTestTeam();
    const managerId = await createTestUser();
    const requesterId = await createTestUser({ managerId });
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);
    const categoryId = await getCategoryId("Equipment Request");

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "New monitor",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });

    return { ticket, managerId, requesterId, techId };
  }

  it("approves a pending ticket and records who approved it", async () => {
    const { ticket, managerId } = await makePendingApprovalTicket();
    await approveTicket({ ticketId: ticket.id, approverId: managerId, note: "Go ahead" });

    const result = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [ticket.id]);
    const updated = result.rows[0];
    expect(updated.approval_status).toBe("approved");
    expect(updated.approved_by_id).toBe(managerId);
    expect(updated.approval_note).toBe("Go ahead");
    expect(updated.approved_at).not.toBeNull();
  });

  it("rejects a pending ticket", async () => {
    const { ticket, managerId } = await makePendingApprovalTicket();
    await rejectTicket({ ticketId: ticket.id, approverId: managerId, note: "Not this quarter" });

    const result = await pool.query(`SELECT approval_status, approval_note FROM tickets WHERE id = $1`, [
      ticket.id,
    ]);
    expect(result.rows[0].approval_status).toBe("rejected");
    expect(result.rows[0].approval_note).toBe("Not this quarter");
  });

  it("is a no-op if the ticket isn't pending anymore", async () => {
    const { ticket, managerId } = await makePendingApprovalTicket();
    await approveTicket({ ticketId: ticket.id, approverId: managerId, note: "first" });
    await rejectTicket({ ticketId: ticket.id, approverId: managerId, note: "second" });

    const result = await pool.query(`SELECT approval_status, approval_note FROM tickets WHERE id = $1`, [
      ticket.id,
    ]);
    // Still approved from the first call — the second (reject) call did nothing.
    expect(result.rows[0].approval_status).toBe("approved");
    expect(result.rows[0].approval_note).toBe("first");
  });

  it("logs an internal note documenting the decision", async () => {
    const { ticket, managerId } = await makePendingApprovalTicket();
    await approveTicket({ ticketId: ticket.id, approverId: managerId, note: "Go ahead" });

    const notes = await pool.query(`SELECT body FROM ticket_notes WHERE ticket_id = $1`, [ticket.id]);
    expect(notes.rows).toHaveLength(1);
    expect(notes.rows[0].body).toContain("approved");
    expect(notes.rows[0].body).toContain("Go ahead");
  });

  it("notifies the assigned technician when approved", async () => {
    const { ticket, managerId, techId } = await makePendingApprovalTicket();
    await approveTicket({ ticketId: ticket.id, approverId: managerId });

    const notifications = await getNotificationsForUser(techId);
    expect(notifications.find((n) => n.event === "ticket_approved")).toBeDefined();
  });

  it("notifies the assigned technician when rejected", async () => {
    const { ticket, managerId, techId } = await makePendingApprovalTicket();
    await rejectTicket({ ticketId: ticket.id, approverId: managerId });

    const notifications = await getNotificationsForUser(techId);
    expect(notifications.find((n) => n.event === "ticket_rejected")).toBeDefined();
  });
});

describe("resolving a ticket while approval is pending", () => {
  beforeEach(resetTestDb);

  it("addReplyAndUpdateStatus itself does not block on approval status (enforcement is at the page layer)", async () => {
    // This documents the current design: the DB-level status transition
    // isn't blocked by approval_status — the ticket detail page's
    // submitReply action checks approval_status before calling this and
    // redirects with an error instead. Covered here so the boundary is
    // explicit if that enforcement point ever moves.
    const teamId = await createTestTeam();
    const managerId = await createTestUser();
    const requesterId = await createTestUser({ managerId });
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);
    const categoryId = await pool
      .query(`SELECT id FROM categories WHERE name = 'Access Request'`)
      .then((r) => r.rows[0].id);

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Needs approval",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });
    expect(ticket.approval_status).toBe("pending");

    const updated = await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "resolved" });
    expect(updated.status).toBe("resolved");
  });
});

afterAll(async () => {
  await pool.end();
});

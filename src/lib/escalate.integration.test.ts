import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, escalateTicket } from "./tickets";
import { getNotificationsForUser } from "./notifications";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

async function makeAssignedTicket(overrides: { impact?: "high" | "medium" | "low"; urgency?: "high" | "medium" | "low" } = {}) {
  const teamId = await createTestTeam();
  const requesterId = await createTestUser();
  const techId = await createTestUser({ isTechnician: true });
  await addToTeam(teamId, techId);
  const ticket = await createTicket({
    requesterId,
    openedById: requesterId,
    subject: "Escalation test ticket",
    description: "...",
    submissionChannel: "web",
    teamId,
    ...overrides,
  });
  return { ticket, requesterId, techId, teamId };
}

describe("escalateTicket", () => {
  beforeEach(resetTestDb);

  it("flags the ticket, bumps priority one level, and records the reason", async () => {
    const { ticket, techId } = await makeAssignedTicket({ impact: "medium", urgency: "medium" });
    expect(ticket.priority).toBe("medium");

    await escalateTicket({ ticketId: ticket.id, actorId: techId, reason: "Exec is asking" });

    const result = await pool.query(`SELECT * FROM tickets WHERE id = $1`, [ticket.id]);
    const updated = result.rows[0];
    expect(updated.is_escalated).toBe(true);
    expect(updated.priority).toBe("high");
    expect(updated.escalated_by_id).toBe(techId);
    expect(updated.escalation_reason).toBe("Exec is asking");
    expect(updated.escalated_at).not.toBeNull();
  });

  it("caps priority at critical instead of erroring", async () => {
    const { ticket, techId } = await makeAssignedTicket({ impact: "high", urgency: "high" });
    expect(ticket.priority).toBe("critical");

    await escalateTicket({ ticketId: ticket.id, actorId: techId });

    const result = await pool.query(`SELECT priority FROM tickets WHERE id = $1`, [ticket.id]);
    expect(result.rows[0].priority).toBe("critical");
  });

  it("is a no-op if the ticket is already escalated", async () => {
    const { ticket, techId } = await makeAssignedTicket({ impact: "medium", urgency: "medium" });
    await escalateTicket({ ticketId: ticket.id, actorId: techId, reason: "first" });
    await escalateTicket({ ticketId: ticket.id, actorId: techId, reason: "second" });

    const result = await pool.query(`SELECT priority, escalation_reason FROM tickets WHERE id = $1`, [
      ticket.id,
    ]);
    // Only the first escalation's bump and reason should have taken effect.
    expect(result.rows[0].priority).toBe("high");
    expect(result.rows[0].escalation_reason).toBe("first");
  });

  it("logs an internal note documenting the escalation", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    await escalateTicket({ ticketId: ticket.id, actorId: techId, reason: "Customer is furious" });

    const notes = await pool.query(`SELECT body FROM ticket_notes WHERE ticket_id = $1`, [ticket.id]);
    expect(notes.rows).toHaveLength(1);
    expect(notes.rows[0].body).toContain("Escalated");
    expect(notes.rows[0].body).toContain("Customer is furious");
  });

  it("notifies other technicians on the team, but not the escalating actor", async () => {
    const { ticket, techId, teamId } = await makeAssignedTicket();
    const otherTechId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, otherTechId);

    await escalateTicket({ ticketId: ticket.id, actorId: techId, reason: "Needs help" });

    const otherNotifications = await getNotificationsForUser(otherTechId);
    expect(otherNotifications.find((n) => n.event === "ticket_escalated")).toBeDefined();

    const actorNotifications = await getNotificationsForUser(techId);
    expect(actorNotifications.find((n) => n.event === "ticket_escalated")).toBeUndefined();
  });
});

afterAll(async () => {
  await pool.end();
});

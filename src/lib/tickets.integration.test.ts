import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, addReplyAndUpdateStatus, addNote, getNotesForTicket } from "./tickets";
import { pool } from "./db";
import {
  resetTestDb,
  createTestTeam,
  createTestUser,
  addToTeam,
  getDefaultCategoryId,
} from "./test-fixtures";

describe("createTicket", () => {
  beforeEach(resetTestDb);

  it("calculates priority from impact x urgency", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);

    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Server on fire",
      description: "Literally on fire",
      submissionChannel: "web",
      teamId,
      impact: "high",
      urgency: "high",
    });

    expect(ticket.priority).toBe("critical");
  });

  it("defaults to normal priority when impact/urgency aren't given", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);

    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Question",
      description: "How do I...",
      submissionChannel: "web",
      teamId,
    });

    expect(ticket.priority).toBe("normal");
  });

  it("auto-assigns to a team member and records status history", async () => {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Laptop dead",
      description: "Won't turn on",
      submissionChannel: "web",
      teamId,
    });

    expect(ticket.assigned_tech_id).toBe(techId);
    expect(ticket.status).toBe("assigned");

    const history = await pool.query(
      `SELECT * FROM ticket_status_history WHERE ticket_id = $1 ORDER BY created_at`,
      [ticket.id]
    );
    expect(history.rows).toHaveLength(1);
    expect(history.rows[0].to_status).toBe("assigned");
    expect(history.rows[0].from_status).toBeNull();
  });

  it("leaves status as open with no assignment when the team has no members", async () => {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();

    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "No one to assign",
      description: "...",
      submissionChannel: "web",
      teamId,
    });

    expect(ticket.assigned_tech_id).toBeNull();
    expect(ticket.status).toBe("open");
  });

  it("generates a unique, sequential-looking ticket_number", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);

    const t1 = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "First",
      description: "...",
      submissionChannel: "web",
      teamId,
    });
    const t2 = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Second",
      description: "...",
      submissionChannel: "web",
      teamId,
    });

    expect(t1.ticket_number).toMatch(/^INC-\d{6}$/);
    expect(t2.ticket_number).not.toBe(t1.ticket_number);
  });

  it("stores the given category", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);
    const categoryId = await getDefaultCategoryId();

    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Categorized",
      description: "...",
      submissionChannel: "web",
      teamId,
      categoryId,
    });

    expect(ticket.category_id).toBe(categoryId);
  });
});

describe("addReplyAndUpdateStatus", () => {
  beforeEach(resetTestDb);

  async function makeTicket() {
    const teamId = await createTestTeam();
    const userId = await createTestUser();
    await addToTeam(teamId, userId);
    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Test ticket",
      description: "...",
      submissionChannel: "web",
      teamId,
    });
    return { ticket, userId };
  }

  it("adds a reply without changing status", async () => {
    const { ticket, userId } = await makeTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: userId, body: "Working on it" });

    const replies = await pool.query(`SELECT * FROM ticket_replies WHERE ticket_id = $1`, [ticket.id]);
    expect(replies.rows).toHaveLength(1);
    expect(replies.rows[0].body).toBe("Working on it");

    const current = await pool.query(`SELECT status FROM tickets WHERE id = $1`, [ticket.id]);
    expect(current.rows[0].status).toBe(ticket.status);
  });

  it("sets resolved_at and resolved_by_id when resolving", async () => {
    const { ticket, userId } = await makeTicket();
    const updated = await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: userId, status: "resolved" });

    expect(updated.status).toBe("resolved");
    expect(updated.resolved_at).not.toBeNull();
    expect(updated.resolved_by_id).toBe(userId);
  });

  it("sets closed_at and closed_by_id when closing", async () => {
    const { ticket, userId } = await makeTicket();
    const updated = await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: userId, status: "closed" });

    expect(updated.status).toBe("closed");
    expect(updated.closed_at).not.toBeNull();
    expect(updated.closed_by_id).toBe(userId);
  });

  it("records from_status -> to_status in history", async () => {
    const { ticket, userId } = await makeTicket();
    const fromStatus = ticket.status;
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: userId, status: "in_progress" });

    const history = await pool.query(
      `SELECT * FROM ticket_status_history WHERE ticket_id = $1 ORDER BY created_at DESC LIMIT 1`,
      [ticket.id]
    );
    expect(history.rows[0].from_status).toBe(fromStatus);
    expect(history.rows[0].to_status).toBe("in_progress");
  });
});

describe("internal notes", () => {
  beforeEach(resetTestDb);

  it("round-trips a note and includes the author's name", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, userId);
    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Needs a note",
      description: "...",
      submissionChannel: "web",
      teamId,
    });

    await addNote({ ticketId: ticket.id, authorId: userId, body: "Internal only" });
    const notes = await getNotesForTicket(ticket.id);

    expect(notes).toHaveLength(1);
    expect(notes[0].body).toBe("Internal only");
    expect(notes[0].author_name).toBe("Test User");
  });

  it("keeps notes out of ticket_replies", async () => {
    const teamId = await createTestTeam();
    const userId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, userId);
    const ticket = await createTicket({
      requesterId: userId,
      openedById: userId,
      subject: "Needs a note",
      description: "...",
      submissionChannel: "web",
      teamId,
    });

    await addNote({ ticketId: ticket.id, authorId: userId, body: "Should never be a public reply" });

    const replies = await pool.query(`SELECT * FROM ticket_replies WHERE ticket_id = $1`, [ticket.id]);
    expect(replies.rows).toHaveLength(0);
  });
});

afterAll(async () => {
  await pool.end();
});

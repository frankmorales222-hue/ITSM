import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, addReplyAndUpdateStatus, addNote } from "./tickets";
import { getTimeline } from "./timeline";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

describe("getTimeline", () => {
  beforeEach(resetTestDb);

  async function makeTicket() {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);
    const ticket = await createTicket({
      requesterId,
      openedById: requesterId,
      subject: "Timeline test ticket",
      description: "...",
      submissionChannel: "web",
      teamId,
    });
    return { ticket, requesterId, techId };
  }

  it("includes the ticket-creation status entry and a reply, in chronological order", async () => {
    const { ticket, requesterId } = await makeTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: requesterId, body: "Any update?" });

    const timeline = await getTimeline(ticket.id, false);
    expect(timeline.length).toBeGreaterThanOrEqual(2);
    expect(timeline[0].type).toBe("status_change");
    expect(timeline.some((e) => e.type === "reply" && e.body === "Any update?")).toBe(true);
    for (let i = 1; i < timeline.length; i++) {
      expect(new Date(timeline[i].createdAt).getTime()).toBeGreaterThanOrEqual(
        new Date(timeline[i - 1].createdAt).getTime()
      );
    }
  });

  it("excludes internal notes when includeInternal is false", async () => {
    const { ticket, techId } = await makeTicket();
    await addNote({ ticketId: ticket.id, authorId: techId, body: "Internal only" });

    const publicTimeline = await getTimeline(ticket.id, false);
    expect(publicTimeline.some((e) => e.type === "note")).toBe(false);
  });

  it("includes internal notes when includeInternal is true", async () => {
    const { ticket, techId } = await makeTicket();
    await addNote({ ticketId: ticket.id, authorId: techId, body: "Internal only" });

    const fullTimeline = await getTimeline(ticket.id, true);
    const noteEntry = fullTimeline.find((e) => e.type === "note");
    expect(noteEntry).toBeDefined();
    expect(noteEntry?.body).toBe("Internal only");
  });

  it("records from/to status on a status_change entry", async () => {
    const { ticket, techId } = await makeTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "in_progress" });

    const timeline = await getTimeline(ticket.id, false);
    const change = timeline.find((e) => e.type === "status_change" && e.toStatus === "in_progress");
    expect(change).toBeDefined();
    expect(change?.fromStatus).toBe("assigned");
  });
});

afterAll(async () => {
  await pool.end();
});

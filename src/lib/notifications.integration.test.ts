import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { createTicket, addReplyAndUpdateStatus, reassignTicket } from "./tickets";
import { getNotificationsForUser, getUnreadNotificationCount, markNotificationRead, markAllNotificationsRead } from "./notifications";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

async function makeAssignedTicket() {
  const teamId = await createTestTeam();
  const requesterId = await createTestUser();
  const techId = await createTestUser({ isTechnician: true });
  await addToTeam(teamId, techId);
  const ticket = await createTicket({
    requesterId,
    openedById: requesterId,
    subject: "Test ticket",
    description: "...",
    submissionChannel: "web",
    teamId,
  });
  return { ticket, requesterId, techId, teamId };
}

describe("notifications", () => {
  beforeEach(resetTestDb);

  it("notifies the assigned technician when a ticket is auto-assigned", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    const notifications = await getNotificationsForUser(techId);
    expect(notifications).toHaveLength(1);
    expect(notifications[0].event).toBe("ticket_assigned");
    expect(notifications[0].ticket_id).toBe(ticket.id);
  });

  it("notifies the assigned technician when the requester replies", async () => {
    const { ticket, requesterId, techId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: requesterId, body: "Any update?" });

    const notifications = await getNotificationsForUser(techId);
    const replyNotif = notifications.find((n) => n.event === "requester_replied");
    expect(replyNotif).toBeDefined();
  });

  it("notifies the requester when a technician replies", async () => {
    const { ticket, requesterId, techId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, body: "Looking into it" });

    const notifications = await getNotificationsForUser(requesterId);
    const replyNotif = notifications.find((n) => n.event === "technician_replied");
    expect(replyNotif).toBeDefined();
  });

  it("does not notify the author of their own reply", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, body: "Note to self" });

    const notifications = await getNotificationsForUser(techId);
    expect(notifications.find((n) => n.event === "technician_replied")).toBeUndefined();
  });

  it("notifies the requester with ticket_resolved when a technician resolves the ticket", async () => {
    const { ticket, requesterId, techId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "resolved" });

    const notifications = await getNotificationsForUser(requesterId);
    expect(notifications.find((n) => n.event === "ticket_resolved")).toBeDefined();
  });

  it("does not notify the requester when they change the status themselves", async () => {
    const { ticket, requesterId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: requesterId, status: "waiting_on_vendor" });

    const notifications = await getNotificationsForUser(requesterId);
    expect(notifications.find((n) => n.event === "status_changed")).toBeUndefined();
  });

  it("notifies the new technician on reassignment", async () => {
    const { ticket, teamId, techId: firstTechId } = await makeAssignedTicket();
    const secondTechId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, secondTechId);

    await reassignTicket({ ticketId: ticket.id, newTechId: secondTechId, reassignedById: firstTechId });

    const notifications = await getNotificationsForUser(secondTechId);
    expect(notifications.find((n) => n.event === "ticket_assigned")).toBeDefined();
  });

  it("tracks unread count and supports marking read", async () => {
    const { techId } = await makeAssignedTicket();

    expect(await getUnreadNotificationCount(techId)).toBe(1);

    const notifications = await getNotificationsForUser(techId);
    await markNotificationRead(notifications[0].id, techId);

    expect(await getUnreadNotificationCount(techId)).toBe(0);
  });

  it("mark-as-read is scoped to the recipient", async () => {
    const { techId } = await makeAssignedTicket();
    const otherUserId = await createTestUser();

    const notifications = await getNotificationsForUser(techId);
    await markNotificationRead(notifications[0].id, otherUserId);

    expect(await getUnreadNotificationCount(techId)).toBe(1);
  });

  it("markAllNotificationsRead clears every unread notification for a user", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    await addReplyAndUpdateStatus({ ticketId: ticket.id, authorId: techId, status: "in_progress" });

    await markAllNotificationsRead(techId);
    expect(await getUnreadNotificationCount(techId)).toBe(0);
  });
});

afterAll(async () => {
  await pool.end();
});

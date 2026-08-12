import { describe, it, expect, beforeEach, afterAll } from "vitest";
import crypto from "crypto";
import { assertWithinTicketQuota, AttachmentValidationError } from "./attachments";
import { createTicket } from "./tickets";
import { pool } from "./db";
import { resetTestDb, createTestTeam, createTestUser, addToTeam } from "./test-fixtures";

function makeFile(name: string, sizeBytes: number): File {
  return new File([new Uint8Array(sizeBytes)], name);
}

async function makeTicket() {
  const teamId = await createTestTeam();
  const userId = await createTestUser();
  await addToTeam(teamId, userId);
  return createTicket({
    requesterId: userId,
    openedById: userId,
    subject: "Test ticket",
    description: "...",
    submissionChannel: "web",
    teamId,
  });
}

async function insertAttachmentRow(ticketId: string, uploadedById: string, sizeBytes: number) {
  await pool.query(
    `INSERT INTO ticket_attachments (ticket_id, uploaded_by_id, file_name, storage_path, content_type, size_bytes)
     VALUES ($1, $2, 'existing.txt', $3, 'text/plain', $4)`,
    [ticketId, uploadedById, crypto.randomUUID(), sizeBytes]
  );
}

describe("assertWithinTicketQuota", () => {
  beforeEach(resetTestDb);
  afterAll(async () => {
    await pool.end();
  });

  it("allows a small file on a ticket with no attachments yet", async () => {
    const ticket = await makeTicket();
    await expect(assertWithinTicketQuota(ticket.id, makeFile("a.txt", 1024))).resolves.not.toThrow();
  });

  it("rejects once the ticket already has 20 attachments", async () => {
    const ticket = await makeTicket();
    for (let i = 0; i < 20; i++) {
      await insertAttachmentRow(ticket.id, ticket.requester_id, 100);
    }
    await expect(assertWithinTicketQuota(ticket.id, makeFile("a.txt", 100))).rejects.toThrow(
      AttachmentValidationError
    );
  });

  it("rejects when adding the file would exceed the 200 MB total", async () => {
    const ticket = await makeTicket();
    await insertAttachmentRow(ticket.id, ticket.requester_id, 199 * 1024 * 1024);
    await expect(
      assertWithinTicketQuota(ticket.id, makeFile("big.zip", 2 * 1024 * 1024))
    ).rejects.toThrow(AttachmentValidationError);
  });

  it("counts existing attachments only for this ticket, not others", async () => {
    const ticketA = await makeTicket();
    const ticketB = await makeTicket();
    for (let i = 0; i < 20; i++) {
      await insertAttachmentRow(ticketA.id, ticketA.requester_id, 100);
    }
    await expect(assertWithinTicketQuota(ticketB.id, makeFile("a.txt", 100))).resolves.not.toThrow();
  });
});

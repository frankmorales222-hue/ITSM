import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { NextRequest } from "next/server";
import { GET, PATCH } from "./route";
import { pool } from "@/lib/db";
import { createTicket } from "@/lib/tickets";
import { createSessionCookieValue, SESSION_COOKIE_NAME } from "@/lib/session";
import {
  resetTestDb,
  createTestTeam,
  createTestUser,
  addToTeam,
} from "@/lib/test-fixtures";

function cookieHeader(userId: string): string {
  return `${SESSION_COOKIE_NAME}=${createSessionCookieValue(userId)}`;
}

function req(url: string, init?: ConstructorParameters<typeof NextRequest>[1]): NextRequest {
  return new NextRequest(new URL(url, "http://localhost:3000"), init);
}

function paramsFor(id: string) {
  return { params: Promise.resolve({ id }) };
}

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
  const strangerId = await createTestUser();
  return { ticket, requesterId, techId, strangerId };
}

describe("GET /api/tickets/:id", () => {
  beforeEach(resetTestDb);

  it("401s without a session", async () => {
    const { ticket } = await makeAssignedTicket();
    const res = await GET(req(`/api/tickets/${ticket.id}`), paramsFor(ticket.id));
    expect(res.status).toBe(401);
  });

  it("404s for a user who isn't the requester or assigned tech", async () => {
    const { ticket, strangerId } = await makeAssignedTicket();
    const res = await GET(
      req(`/api/tickets/${ticket.id}`, { headers: { cookie: cookieHeader(strangerId) } }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(404);
  });

  it("404s for a nonexistent ticket id (not a 500)", async () => {
    const userId = await createTestUser();
    const fakeId = "00000000-0000-0000-0000-000000000000";
    const res = await GET(
      req(`/api/tickets/${fakeId}`, { headers: { cookie: cookieHeader(userId) } }),
      paramsFor(fakeId)
    );
    expect(res.status).toBe(404);
  });

  it("200s for the requester", async () => {
    const { ticket, requesterId } = await makeAssignedTicket();
    const res = await GET(
      req(`/api/tickets/${ticket.id}`, { headers: { cookie: cookieHeader(requesterId) } }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.ticket.id).toBe(ticket.id);
  });

  it("200s for the assigned technician", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    const res = await GET(
      req(`/api/tickets/${ticket.id}`, { headers: { cookie: cookieHeader(techId) } }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(200);
  });
});

describe("PATCH /api/tickets/:id", () => {
  beforeEach(resetTestDb);

  it("401s without a session", async () => {
    const { ticket } = await makeAssignedTicket();
    const res = await PATCH(
      req(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body: "hi" }),
      }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(401);
  });

  it("404s for a user who isn't the requester or assigned tech", async () => {
    const { ticket, strangerId } = await makeAssignedTicket();
    const res = await PATCH(
      req(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json", cookie: cookieHeader(strangerId) },
        body: JSON.stringify({ body: "trying to butt in" }),
      }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(404);

    const replies = await pool.query(`SELECT * FROM ticket_replies WHERE ticket_id = $1`, [ticket.id]);
    expect(replies.rows).toHaveLength(0);
  });

  it("lets the requester reply and attributes it to them, not a client-supplied authorId", async () => {
    const { ticket, requesterId } = await makeAssignedTicket();
    const impersonatedId = await createTestUser();

    const res = await PATCH(
      req(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json", cookie: cookieHeader(requesterId) },
        body: JSON.stringify({ authorId: impersonatedId, body: "Reseated the cable" }),
      }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(200);

    const replies = await pool.query(`SELECT * FROM ticket_replies WHERE ticket_id = $1`, [ticket.id]);
    expect(replies.rows).toHaveLength(1);
    expect(replies.rows[0].author_id).toBe(requesterId);
  });

  it("lets the assigned tech change status", async () => {
    const { ticket, techId } = await makeAssignedTicket();
    const res = await PATCH(
      req(`/api/tickets/${ticket.id}`, {
        method: "PATCH",
        headers: { "content-type": "application/json", cookie: cookieHeader(techId) },
        body: JSON.stringify({ status: "resolved" }),
      }),
      paramsFor(ticket.id)
    );
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.ticket.status).toBe("resolved");
    expect(data.ticket.resolved_by_id).toBe(techId);
  });
});

afterAll(async () => {
  await pool.end();
});

import { describe, it, expect, beforeEach, afterAll } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "./route";
import { pool } from "@/lib/db";
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

describe("GET /api/tickets", () => {
  beforeEach(resetTestDb);

  it("401s without a session", async () => {
    const res = await GET(req("/api/tickets"));
    expect(res.status).toBe(401);
  });

  it("returns only the session user's own tickets by default", async () => {
    const teamId = await createTestTeam();
    const userA = await createTestUser();
    const userB = await createTestUser();
    await addToTeam(teamId, userA);

    await POST(
      req("/api/tickets", {
        method: "POST",
        headers: { "content-type": "application/json", cookie: cookieHeader(userA) },
        body: JSON.stringify({
          subject: "A's ticket",
          description: "...",
          submissionChannel: "web",
          teamId,
        }),
      })
    );

    const resA = await GET(req("/api/tickets", { headers: { cookie: cookieHeader(userA) } }));
    const dataA = await resA.json();
    expect(dataA.tickets).toHaveLength(1);
    expect(dataA.tickets[0].subject).toBe("A's ticket");

    const resB = await GET(req("/api/tickets", { headers: { cookie: cookieHeader(userB) } }));
    const dataB = await resB.json();
    expect(dataB.tickets).toHaveLength(0);
  });

  it("returns tickets assigned to the session user when role=technician", async () => {
    const teamId = await createTestTeam();
    const requesterId = await createTestUser();
    const techId = await createTestUser({ isTechnician: true });
    await addToTeam(teamId, techId);

    await POST(
      req("/api/tickets", {
        method: "POST",
        headers: { "content-type": "application/json", cookie: cookieHeader(requesterId) },
        body: JSON.stringify({
          subject: "Needs a tech",
          description: "...",
          submissionChannel: "web",
          teamId,
        }),
      })
    );

    const res = await GET(
      req("/api/tickets?role=technician", { headers: { cookie: cookieHeader(techId) } })
    );
    const data = await res.json();
    expect(data.tickets).toHaveLength(1);
    expect(data.tickets[0].assigned_tech_id).toBe(techId);
  });
});

describe("POST /api/tickets", () => {
  beforeEach(resetTestDb);

  it("401s without a session", async () => {
    const res = await POST(
      req("/api/tickets", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ subject: "x", description: "y", submissionChannel: "web", teamId: "z" }),
      })
    );
    expect(res.status).toBe(401);
  });

  it("400s when required fields are missing", async () => {
    const userId = await createTestUser();
    const res = await POST(
      req("/api/tickets", {
        method: "POST",
        headers: { "content-type": "application/json", cookie: cookieHeader(userId) },
        body: JSON.stringify({ subject: "Missing stuff" }),
      })
    );
    expect(res.status).toBe(400);
  });

  it("ignores a client-supplied requesterId and files the ticket as the session user", async () => {
    const teamId = await createTestTeam();
    const realUserId = await createTestUser();
    const impersonatedId = await createTestUser();
    await addToTeam(teamId, realUserId);

    const res = await POST(
      req("/api/tickets", {
        method: "POST",
        headers: { "content-type": "application/json", cookie: cookieHeader(realUserId) },
        body: JSON.stringify({
          requesterId: impersonatedId,
          subject: "Trying to impersonate",
          description: "...",
          submissionChannel: "web",
          teamId,
        }),
      })
    );

    expect(res.status).toBe(201);
    const data = await res.json();
    expect(data.ticket.requester_id).toBe(realUserId);
  });
});

afterAll(async () => {
  await pool.end();
});

import { describe, it, expect } from "vitest";
import { calculateDueAt, isOverdue } from "./sla";

describe("calculateDueAt", () => {
  it("adds the critical SLA window in hours", () => {
    const from = new Date("2026-01-01T00:00:00Z");
    expect(calculateDueAt("critical", from).toISOString()).toBe("2026-01-01T04:00:00.000Z");
  });

  it("falls back to the normal window for an unknown priority", () => {
    const from = new Date("2026-01-01T00:00:00Z");
    expect(calculateDueAt("unknown", from).toISOString()).toBe(
      calculateDueAt("normal", from).toISOString()
    );
  });
});

describe("isOverdue", () => {
  it("is true for a past due date on an open ticket", () => {
    expect(isOverdue({ due_at: new Date(Date.now() - 1000), status: "open" })).toBe(true);
  });

  it("is false for a future due date", () => {
    expect(isOverdue({ due_at: new Date(Date.now() + 100000), status: "open" })).toBe(false);
  });

  it("is false once the ticket is resolved, even if past due", () => {
    expect(isOverdue({ due_at: new Date(Date.now() - 1000), status: "resolved" })).toBe(false);
  });

  it("is false when there is no due date", () => {
    expect(isOverdue({ due_at: null, status: "open" })).toBe(false);
  });
});

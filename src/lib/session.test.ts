import { describe, it, expect, vi } from "vitest";
import { createSessionCookieValue, verifySessionCookieValue } from "./session";

describe("session cookie sign/verify", () => {
  it("round-trips a valid cookie back to the same userId", () => {
    const cookie = createSessionCookieValue("user-123");
    expect(verifySessionCookieValue(cookie)).toBe("user-123");
  });

  it("rejects a tampered userId even with the original signature", () => {
    const cookie = createSessionCookieValue("user-123");
    const [, expiresAt, signature] = cookie.split(".");
    const tampered = `attacker-controlled-id.${expiresAt}.${signature}`;
    expect(verifySessionCookieValue(tampered)).toBeNull();
  });

  it("rejects a tampered signature", () => {
    const cookie = createSessionCookieValue("user-123");
    const [userId, expiresAt] = cookie.split(".");
    const tampered = `${userId}.${expiresAt}.0000000000000000000000000000000000000000000000000000000000000000`;
    expect(verifySessionCookieValue(tampered)).toBeNull();
  });

  it("rejects malformed values", () => {
    expect(verifySessionCookieValue(null)).toBeNull();
    expect(verifySessionCookieValue(undefined)).toBeNull();
    expect(verifySessionCookieValue("")).toBeNull();
    expect(verifySessionCookieValue("not-enough-parts")).toBeNull();
    expect(verifySessionCookieValue("a.b.c.d")).toBeNull();
  });

  it("rejects an expired cookie", () => {
    vi.useFakeTimers();
    try {
      const cookie = createSessionCookieValue("user-123");
      vi.advanceTimersByTime(1000 * 60 * 60 * 24 * 8); // 8 days, past the 7-day TTL
      expect(verifySessionCookieValue(cookie)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

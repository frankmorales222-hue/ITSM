import { describe, it, expect, afterAll } from "vitest";
import crypto from "crypto";
import { stashOidcState, takeOidcState } from "./oidc";
import { redis } from "./redis";

// The rest of oidc.ts (discovery, the actual authorization code exchange)
// needs a live OIDC provider to test meaningfully — that was verified
// manually against a local mock provider rather than being part of this
// suite, since Azure AD isn't configured by default (see README).
describe("OIDC state stash/take", () => {
  afterAll(async () => {
    await redis.quit();
  });

  it("round-trips codeVerifier and nonce", async () => {
    const state = crypto.randomUUID();
    await stashOidcState(state, { codeVerifier: "verifier-123", nonce: "nonce-456" });
    expect(await takeOidcState(state)).toEqual({
      codeVerifier: "verifier-123",
      nonce: "nonce-456",
    });
  });

  it("is single-use — a second take returns null", async () => {
    const state = crypto.randomUUID();
    await stashOidcState(state, { codeVerifier: "v", nonce: "n" });
    await takeOidcState(state);
    expect(await takeOidcState(state)).toBeNull();
  });

  it("returns null for a state that was never stashed", async () => {
    expect(await takeOidcState(crypto.randomUUID())).toBeNull();
  });
});

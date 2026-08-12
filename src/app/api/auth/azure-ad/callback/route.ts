import { NextRequest, NextResponse } from "next/server";
import * as client from "openid-client";
import { pool } from "@/lib/db";
import { getAzureAdConfig } from "@/lib/admin-settings";
import { discoverAzureAd, takeOidcState } from "@/lib/oidc";
import {
  createSessionCookieValue,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
} from "@/lib/session";

function firstString(...values: unknown[]): string | null {
  for (const v of values) {
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

// GET /api/auth/azure-ad/callback — completes the OIDC flow. On success,
// looks up the user by the ID token's email claim, auto-provisioning one
// on first login: Azure AD *is* the "actual directory" earlier parts of
// this app deferred to (see README) — there's no reason to also require
// someone to have been seeded here first.
export async function GET(req: NextRequest) {
  const failureRedirect = NextResponse.redirect(new URL("/login?error=sso_failed", req.url));

  const state = req.nextUrl.searchParams.get("state");
  if (!state) return failureRedirect;

  const stored = await takeOidcState(state);
  if (!stored) return failureRedirect;

  const azureAd = await getAzureAdConfig();
  if (!azureAd) return failureRedirect;

  try {
    const config = await discoverAzureAd(azureAd.tenantId, azureAd.clientId, azureAd.clientSecret);

    // req.nextUrl is a NextURL, not a plain URL — openid-client does a
    // strict `instanceof URL` check that NextURL fails.
    const tokens = await client.authorizationCodeGrant(config, new URL(req.url), {
      pkceCodeVerifier: stored.codeVerifier,
      expectedState: state,
      expectedNonce: stored.nonce,
    });

    const claims = tokens.claims();
    const email = firstString(claims?.email, claims?.preferred_username)?.toLowerCase();
    if (!email) return failureRedirect;
    const displayName = firstString(claims?.name) ?? email;

    const existing = await pool.query(
      `SELECT id FROM users WHERE lower(email) = $1 AND is_active = true`,
      [email]
    );
    let userId: string = existing.rows[0]?.id;
    if (!userId) {
      const inserted = await pool.query(
        `INSERT INTO users (display_name, email) VALUES ($1, $2) RETURNING id`,
        [displayName, email]
      );
      userId = inserted.rows[0].id;
    }

    const res = NextResponse.redirect(new URL("/tickets", req.url));
    res.cookies.set(SESSION_COOKIE_NAME, createSessionCookieValue(userId), {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: SESSION_MAX_AGE_SECONDS,
      path: "/",
    });
    return res;
  } catch (err) {
    console.error("Azure AD callback failed", err);
    return failureRedirect;
  }
}

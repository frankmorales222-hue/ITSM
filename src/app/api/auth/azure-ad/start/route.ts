import { NextRequest, NextResponse } from "next/server";
import * as client from "openid-client";
import { getAzureAdConfig } from "@/lib/admin-settings";
import { discoverAzureAd, stashOidcState } from "@/lib/oidc";

// GET /api/auth/azure-ad/start — kicks off the OIDC authorization code
// flow (with PKCE) and redirects to Microsoft's login page.
export async function GET(req: NextRequest) {
  const azureAd = await getAzureAdConfig();
  if (!azureAd) {
    return NextResponse.json({ error: "Azure AD is not configured" }, { status: 404 });
  }

  const config = await discoverAzureAd(azureAd.tenantId, azureAd.clientId, azureAd.clientSecret);

  const codeVerifier = client.randomPKCECodeVerifier();
  const codeChallenge = await client.calculatePKCECodeChallenge(codeVerifier);
  const state = client.randomState();
  const nonce = client.randomNonce();

  await stashOidcState(state, { codeVerifier, nonce });

  const redirectUri = new URL("/api/auth/azure-ad/callback", req.nextUrl.origin).toString();

  const authorizationUrl = client.buildAuthorizationUrl(config, {
    redirect_uri: redirectUri,
    scope: "openid profile email",
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    state,
    nonce,
  });

  return NextResponse.redirect(authorizationUrl);
}

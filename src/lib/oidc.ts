import * as client from "openid-client";
import { redis } from "./redis";

// No caching of the discovered Configuration — discovery is a network
// call, but it only happens when someone actually clicks "Sign in with
// Microsoft", and caching risks serving a stale client secret after an
// admin rotates it in /admin.
//
// The authority host is overridable (default: public Azure AD) rather
// than hardcoded — Azure has sovereign-cloud variants on different
// domains (US Gov: login.microsoftonline.us, China:
// login.chinacloudapi.cn), and the same override is what points this at
// a local test OIDC provider in development.
export async function discoverAzureAd(
  tenantId: string,
  clientId: string,
  clientSecret: string
): Promise<client.Configuration> {
  const authorityHost = process.env.AZURE_AD_AUTHORITY_HOST ?? "https://login.microsoftonline.com";
  // openid-client refuses plain HTTP by default (correct — never allow
  // that against a real Azure tenant). The only legitimate reason
  // AZURE_AD_AUTHORITY_HOST would ever be http:// is a local test
  // provider, so scope the opt-out to exactly that case.
  const isInsecureOverride = authorityHost.startsWith("http://");
  return client.discovery(
    new URL(`${authorityHost}/${tenantId}/v2.0`),
    clientId,
    clientSecret,
    undefined,
    isInsecureOverride ? { execute: [client.allowInsecureRequests] } : undefined
  );
}

// PKCE verifier + nonce have to survive the redirect to Microsoft and
// back; keyed by the state value itself, since that's the one thing
// guaranteed to come back unchanged on the callback. Single-use, short
// TTL — this only needs to live for the duration of one login attempt.
const OIDC_STATE_TTL_SECONDS = 600;

export interface OidcState {
  codeVerifier: string;
  nonce: string;
}

export async function stashOidcState(state: string, data: OidcState): Promise<void> {
  await redis.set(`oidcState:${state}`, JSON.stringify(data), "EX", OIDC_STATE_TTL_SECONDS);
}

export async function takeOidcState(state: string): Promise<OidcState | null> {
  const key = `oidcState:${state}`;
  const raw = await redis.get(key);
  if (!raw) return null;
  await redis.del(key);
  return JSON.parse(raw);
}

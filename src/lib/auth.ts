import { cookies } from "next/headers";
import { NextRequest } from "next/server";
import { SESSION_COOKIE_NAME, verifySessionCookieValue } from "./session";

// Server Components / Server Actions read cookies via next/headers.
export async function getSessionUserId(): Promise<string | null> {
  const store = await cookies();
  return verifySessionCookieValue(store.get(SESSION_COOKIE_NAME)?.value);
}

// Route Handlers read cookies off the incoming request instead.
export function getSessionUserIdFromRequest(req: NextRequest): string | null {
  return verifySessionCookieValue(req.cookies.get(SESSION_COOKIE_NAME)?.value);
}

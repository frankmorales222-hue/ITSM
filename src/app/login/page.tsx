// Phase-1 stand-in for real auth: no passwords exist in the schema yet, so
// this issues a signed session cookie after confirming the email belongs to
// an active seeded user. That's weaker than password/SSO auth, but it's a
// real improvement over what it replaces — routes no longer trust a raw
// userId a client can type into a query string or request body; they trust
// only a cookie the server signed. Swap this for real credential checking
// (or SSO) before this touches real employee data.

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import {
  createSessionCookieValue,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
} from "@/lib/session";

async function login(formData: FormData) {
  "use server";

  const email = String(formData.get("email") ?? "")
    .trim()
    .toLowerCase();

  const result = await pool.query(
    `SELECT id FROM users WHERE lower(email) = $1 AND is_active = true`,
    [email]
  );
  const user = result.rows[0];

  if (!user) {
    redirect("/login?error=1");
  }

  const store = await cookies();
  store.set(SESSION_COOKIE_NAME, createSessionCookieValue(user.id), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
  });

  redirect("/tickets");
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <main style={{ padding: 24, fontFamily: "sans-serif", maxWidth: 360 }}>
      <h1>Log in</h1>
      <p style={{ color: "#666" }}>
        Enter the email of a seeded user. There's no password yet — see the
        comment at the top of this file before pointing this at real data.
      </p>
      {error && <p style={{ color: "crimson" }}>No active user with that email.</p>}
      <form action={login}>
        <label htmlFor="email">Email</label>
        <br />
        <input id="email" name="email" type="email" required style={{ width: "100%" }} />
        <button type="submit" style={{ marginTop: 12 }}>
          Log in
        </button>
      </form>
    </main>
  );
}

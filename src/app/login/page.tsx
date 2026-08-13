// Real credential login: email + password, checked against users.password_hash
// (scrypt, see src/lib/password.ts). A user with no password set yet gets
// one via a technician-issued link — see src/app/set-password/page.tsx.

import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { verifyPassword } from "@/lib/password";
import { isRateLimited } from "@/lib/rate-limit";
import { getAzureAdConfig } from "@/lib/admin-settings";
import {
  createSessionCookieValue,
  SESSION_COOKIE_NAME,
  SESSION_MAX_AGE_SECONDS,
} from "@/lib/session";

const ERROR_MESSAGES: Record<string, string> = {
  invalid: "Invalid email or password.",
  rate_limited: "Too many attempts. Try again in a minute.",
  sso_failed: "Microsoft sign-in didn't complete. Try again.",
};

async function login(formData: FormData) {
  "use server";

  const email = String(formData.get("email") ?? "")
    .trim()
    .toLowerCase();
  const password = String(formData.get("password") ?? "");

  const hdrs = await headers();
  const ip = hdrs.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";

  const [emailLimited, ipLimited] = await Promise.all([
    isRateLimited(`email:${email}`),
    isRateLimited(`ip:${ip}`),
  ]);
  if (emailLimited || ipLimited) {
    redirect("/login?error=rate_limited");
  }

  const result = await pool.query(
    `SELECT id, password_hash FROM users WHERE lower(email) = $1 AND is_active = true`,
    [email]
  );
  const user = result.rows[0];

  const valid = user?.password_hash && (await verifyPassword(password, user.password_hash));
  if (!valid) {
    redirect("/login?error=invalid");
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
  searchParams: Promise<{ error?: string; setup?: string }>;
}) {
  const { error, setup } = await searchParams;
  const errorMessage = error ? ERROR_MESSAGES[error] ?? ERROR_MESSAGES.invalid : null;
  const azureAdConfigured = (await getAzureAdConfig()) !== null;

  return (
    <main>
      <div className="card" style={{ maxWidth: 360, margin: "40px auto" }}>
        <h1>Log in</h1>
        {setup === "success" && <p>Password set. You can log in now.</p>}
        {errorMessage && <p className="error">{errorMessage}</p>}
        <form action={login}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" required />
          </div>
          <button type="submit">Log in</button>
        </form>
        <p className="muted" style={{ marginTop: 8 }}>
          <a href="/forgot-password">Forgot password?</a>
        </p>
        {azureAdConfigured && (
          <>
            <p className="muted" style={{ margin: "16px 0 8px", textAlign: "center" }}>
              or
            </p>
            <a href="/api/auth/azure-ad/start">
              <button type="button" className="secondary" style={{ width: "100%" }}>
                Sign in with Microsoft
              </button>
            </a>
          </>
        )}
      </div>
    </main>
  );
}

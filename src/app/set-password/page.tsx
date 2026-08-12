// Public route, gated by a technician-issued token instead of a session —
// this is how a user gets their first session. See src/lib/password-setup.ts
// for why this is technician-initiated rather than self-requested.

import { redirect } from "next/navigation";
import { pool } from "@/lib/db";
import { hashPassword } from "@/lib/password";
import { consumeSetupToken, clearSetupToken } from "@/lib/password-setup";

async function setPassword(formData: FormData) {
  "use server";

  const token = String(formData.get("token") ?? "");
  const password = String(formData.get("password") ?? "");
  const confirm = String(formData.get("confirm") ?? "");

  if (password.length < 8) {
    redirect(`/set-password?token=${token}&error=too_short`);
  }
  if (password !== confirm) {
    redirect(`/set-password?token=${token}&error=mismatch`);
  }

  const userId = await consumeSetupToken(token);
  if (!userId) {
    redirect(`/set-password?token=${token}&error=invalid`);
  }

  const hash = await hashPassword(password);
  await pool.query(`UPDATE users SET password_hash = $1 WHERE id = $2`, [hash, userId]);
  await clearSetupToken(userId);

  redirect("/login?setup=success");
}

const ERROR_MESSAGES: Record<string, string> = {
  too_short: "Password must be at least 8 characters.",
  mismatch: "Passwords don't match.",
  invalid: "This link is invalid or has expired. Ask a technician for a new one.",
};

export default async function SetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string; error?: string }>;
}) {
  const { token, error } = await searchParams;

  if (!token) {
    return (
      <main>
        <div className="card" style={{ maxWidth: 360, margin: "40px auto" }}>
          <h1>Set your password</h1>
          <p className="error">Missing setup link. Ask a technician for one.</p>
        </div>
      </main>
    );
  }

  const errorMessage = error ? ERROR_MESSAGES[error] ?? ERROR_MESSAGES.invalid : null;

  return (
    <main>
      <div className="card" style={{ maxWidth: 360, margin: "40px auto" }}>
        <h1>Set your password</h1>
        {errorMessage && <p className="error">{errorMessage}</p>}
        <form action={setPassword}>
          <input type="hidden" name="token" value={token} />
          <div className="field">
            <label htmlFor="password">New password</label>
            <input id="password" name="password" type="password" required minLength={8} />
          </div>
          <div className="field">
            <label htmlFor="confirm">Confirm password</label>
            <input id="confirm" name="confirm" type="password" required minLength={8} />
          </div>
          <button type="submit">Set password</button>
        </form>
      </div>
    </main>
  );
}

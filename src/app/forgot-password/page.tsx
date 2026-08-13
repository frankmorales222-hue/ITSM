// Self-service password reset — safe now that real outbound email exists
// (src/lib/mailer.ts): the reset link always goes to the address already
// on file for the account, never one supplied fresh in this form, so
// receiving it proves ownership of that mailbox. See src/lib/password-setup.ts
// for why the technician-issued flow (for users with no password yet)
// exists separately — this reuses the same token mechanism, just a
// different way to get the token to its owner.

import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { pool } from "@/lib/db";
import { isRateLimited } from "@/lib/rate-limit";
import { createSetupToken } from "@/lib/password-setup";
import { sendMail } from "@/lib/mailer";

async function requestReset(formData: FormData) {
  "use server";

  const email = String(formData.get("email") ?? "")
    .trim()
    .toLowerCase();

  const hdrs = await headers();
  const ip = hdrs.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";

  const [emailLimited, ipLimited] = await Promise.all([
    isRateLimited(`password-reset:email:${email}`, { windowSeconds: 900, maxAttempts: 3 }),
    isRateLimited(`password-reset:ip:${ip}`, { windowSeconds: 900, maxAttempts: 10 }),
  ]);

  if (!emailLimited && !ipLimited && email) {
    const result = await pool.query(
      `SELECT id, display_name, email FROM users WHERE lower(email) = $1 AND is_active = true`,
      [email]
    );
    const user = result.rows[0];

    // Only the matched-account path does a token + email round trip, so
    // response timing isn't perfectly constant between "account exists"
    // and "it doesn't" — a known, accepted tradeoff here rather than
    // padding every request to match the slowest case.
    if (user) {
      const token = await createSetupToken(user.id);
      const resetUrl = `${process.env.NEXT_PUBLIC_APP_URL}/set-password?token=${token}`;
      await sendMail({
        to: user.email,
        subject: "Reset your IT Support password",
        text: `Hi ${user.display_name},\n\nSomeone requested a password reset for your IT Support account. If this was you, set a new password here (this link expires in 24 hours and can only be used once):\n\n${resetUrl}\n\nIf you didn't request this, you can safely ignore this email.`,
      });
    }
  }

  // Same redirect regardless of whether the email matched, was rate
  // limited, or sending failed — the response must never reveal whether
  // an account exists for that address.
  redirect("/forgot-password?sent=1");
}

export default async function ForgotPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ sent?: string }>;
}) {
  const { sent } = await searchParams;

  return (
    <main>
      <div className="card" style={{ maxWidth: 360, margin: "40px auto" }}>
        <h1>Reset your password</h1>
        {sent ? (
          <p>
            If that email is registered, we&apos;ve sent a link to reset your password. It expires
            in 24 hours.
          </p>
        ) : (
          <>
            <p className="muted">
              Enter your work email and, if an account exists, we&apos;ll send a reset link to it.
            </p>
            <form action={requestReset}>
              <div className="field">
                <label htmlFor="email">Email</label>
                <input id="email" name="email" type="email" required />
              </div>
              <button type="submit">Send reset link</button>
            </form>
          </>
        )}
        <p className="muted" style={{ marginTop: 16 }}>
          <a href="/login">Back to login</a>
        </p>
      </div>
    </main>
  );
}

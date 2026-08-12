// Technician-only: generate a one-time password-setup link for a user who
// doesn't have a password yet. The link itself has to carry the token (any
// bearer-link password-reset flow works this way) but getting the token
// from the server action back to this screen deliberately avoids a URL
// round-trip — see src/lib/password-setup.ts.

import { redirect, notFound } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import {
  createSetupToken,
  stashRevealToken,
  takeRevealToken,
  usersWithoutPassword,
} from "@/lib/password-setup";

async function generateLink(formData: FormData) {
  "use server";

  const technicianId = await getSessionUserId();
  if (!technicianId || !(await isTechnician(technicianId))) {
    redirect("/login");
  }

  const targetUserId = String(formData.get("userId") ?? "");
  if (!targetUserId) {
    redirect("/technician/users");
  }

  const token = await createSetupToken(targetUserId);
  await stashRevealToken(technicianId, targetUserId, token);
  redirect("/technician/users");
}

export default async function TechnicianUsersPage() {
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }
  if (!(await isTechnician(sessionUserId))) {
    notFound();
  }

  const [users, reveal] = await Promise.all([
    usersWithoutPassword(),
    takeRevealToken(sessionUserId),
  ]);
  const revealedUser = reveal ? users.find((u) => u.id === reveal.targetUserId) : null;
  const setupUrl = reveal
    ? `${process.env.NEXT_PUBLIC_APP_URL}/set-password?token=${reveal.token}`
    : null;

  return (
    <main>
      <nav className="nav">
        <a href="/technician">&larr; Technician Queue</a>
      </nav>

      <h1>Users without a password</h1>

      {setupUrl && (
        <div className="card" style={{ borderColor: "var(--color-primary)" }}>
          <strong>Setup link for {revealedUser?.display_name ?? "this user"}</strong>
          <p className="muted">
            Shown once — copy it now and send it to them directly (Slack, in person,
            etc). It expires in 24 hours.
          </p>
          <p style={{ wordBreak: "break-all" }}>
            <code>{setupUrl}</code>
          </p>
        </div>
      )}

      <div className="card">
        {users.length === 0 && <p className="muted">Everyone active has a password set.</p>}
        {users.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u: any) => (
                <tr key={u.id}>
                  <td>{u.display_name}</td>
                  <td>{u.email}</td>
                  <td>
                    <form action={generateLink} className="form-inline">
                      <input type="hidden" name="userId" value={u.id} />
                      <button type="submit" className="secondary">
                        {u.has_pending_link ? "Regenerate link" : "Generate link"}
                      </button>
                    </form>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}

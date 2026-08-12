// Technician-only integration config: Azure AD (SSO) and IMAP (email
// intake), stored encrypted (src/lib/admin-settings.ts) instead of .env
// so they can be set after deploy without shell access. Secrets are
// write-only here — once saved, the form only ever shows "configured",
// never the value back.

import { redirect, notFound } from "next/navigation";
import { getSessionUserId, isTechnician } from "@/lib/auth";
import {
  getAzureAdConfig,
  setAzureAdConfig,
  clearAzureAdConfig,
  getImapConfig,
  setImapConfig,
  clearImapConfig,
} from "@/lib/admin-settings";

async function requireTechnician(): Promise<string> {
  const userId = await getSessionUserId();
  if (!userId || !(await isTechnician(userId))) {
    redirect("/login");
  }
  return userId;
}

async function saveAzureAd(formData: FormData) {
  "use server";
  const userId = await requireTechnician();

  const tenantId = String(formData.get("tenantId") ?? "").trim();
  const clientId = String(formData.get("clientId") ?? "").trim();
  const clientSecret = String(formData.get("clientSecret") ?? "").trim();

  if (tenantId && clientId && clientSecret) {
    await setAzureAdConfig({ tenantId, clientId, clientSecret }, userId);
  }
  redirect("/admin");
}

async function clearAzureAd() {
  "use server";
  await requireTechnician();
  await clearAzureAdConfig();
  redirect("/admin");
}

async function saveImap(formData: FormData) {
  "use server";
  const userId = await requireTechnician();

  const host = String(formData.get("host") ?? "").trim();
  const port = Number(formData.get("port") ?? 993);
  const user = String(formData.get("user") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (host && port && user && password) {
    await setImapConfig({ host, port, user, password }, userId);
  }
  redirect("/admin");
}

async function clearImap() {
  "use server";
  await requireTechnician();
  await clearImapConfig();
  redirect("/admin");
}

export default async function AdminPage() {
  const sessionUserId = await getSessionUserId();
  if (!sessionUserId) {
    redirect("/login");
  }
  if (!(await isTechnician(sessionUserId))) {
    notFound();
  }

  const [azureAd, imap] = await Promise.all([getAzureAdConfig(), getImapConfig()]);

  return (
    <main>
      <nav className="nav">
        <a href="/technician">&larr; Technician Queue</a>
      </nav>

      <h1>Admin</h1>
      <p className="muted">
        Integration config, stored encrypted. Secrets are write-only — saved values
        never display back here, only whether something's configured.
      </p>

      <div className="card">
        <h2>Single sign-on (Azure AD)</h2>
        <p>
          Status:{" "}
          <span className="badge">{azureAd ? "configured" : "not configured"}</span>
        </p>
        {azureAd && (
          <p className="muted">
            Tenant <code>{azureAd.tenantId}</code>, client <code>{azureAd.clientId}</code>.
            Saving again replaces all three values.
          </p>
        )}
        <form action={saveAzureAd}>
          <div className="field">
            <label htmlFor="tenantId">Tenant ID</label>
            <input id="tenantId" name="tenantId" required />
          </div>
          <div className="field">
            <label htmlFor="clientId">Client ID</label>
            <input id="clientId" name="clientId" required />
          </div>
          <div className="field">
            <label htmlFor="clientSecret">Client secret</label>
            <input id="clientSecret" name="clientSecret" type="password" required />
          </div>
          <button type="submit">Save</button>
        </form>
        {azureAd && (
          <form action={clearAzureAd} style={{ marginTop: 8 }}>
            <button type="submit" className="secondary">
              Clear
            </button>
          </form>
        )}
      </div>

      <div className="card">
        <h2>Email intake (IMAP)</h2>
        <p>
          Status: <span className="badge">{imap ? "configured" : "not configured"}</span>
        </p>
        {imap && (
          <p className="muted">
            <code>
              {imap.user}@{imap.host}:{imap.port}
            </code>
            . Saving again replaces all four values.
          </p>
        )}
        <form action={saveImap}>
          <div className="field">
            <label htmlFor="host">IMAP host</label>
            <input id="host" name="host" required />
          </div>
          <div className="field">
            <label htmlFor="port">Port</label>
            <input id="port" name="port" type="number" defaultValue={993} required />
          </div>
          <div className="field">
            <label htmlFor="user">Username</label>
            <input id="user" name="user" required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" name="password" type="password" required />
          </div>
          <button type="submit">Save</button>
        </form>
        {imap && (
          <form action={clearImap} style={{ marginTop: 8 }}>
            <button type="submit" className="secondary">
              Clear
            </button>
          </form>
        )}
      </div>
    </main>
  );
}

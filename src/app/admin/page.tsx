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
  getSmtpConfig,
  setSmtpConfig,
  clearSmtpConfig,
} from "@/lib/admin-settings";
import Nav from "@/components/Nav";
import ConfirmSubmitButton from "@/components/ConfirmSubmitButton";

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

async function saveSmtp(formData: FormData) {
  "use server";
  const userId = await requireTechnician();

  const host = String(formData.get("host") ?? "").trim();
  const port = Number(formData.get("port") ?? 587);
  const user = String(formData.get("user") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const fromAddress = String(formData.get("fromAddress") ?? "").trim();
  const secure = formData.get("secure") === "on";

  if (host && port && fromAddress) {
    await setSmtpConfig({ host, port, user, password, fromAddress, secure }, userId);
  }
  redirect("/admin");
}

async function clearSmtp() {
  "use server";
  await requireTechnician();
  await clearSmtpConfig();
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

  const [azureAd, imap, smtp] = await Promise.all([getAzureAdConfig(), getImapConfig(), getSmtpConfig()]);

  return (
    <main>
      <Nav userId={sessionUserId} />

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
            <ConfirmSubmitButton
              className="secondary"
              message="Clear the Azure AD SSO configuration? Login via SSO will stop working until it's reconfigured."
            >
              Clear
            </ConfirmSubmitButton>
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
            <ConfirmSubmitButton
              className="secondary"
              message="Clear the IMAP configuration? Email intake will stop working until it's reconfigured."
            >
              Clear
            </ConfirmSubmitButton>
          </form>
        )}
      </div>

      <div className="card">
        <h2>Outbound email (SMTP)</h2>
        <p>
          Status: <span className="badge">{smtp ? "configured" : "not configured"}</span>
        </p>
        {smtp && (
          <p className="muted">
            <code>
              {smtp.fromAddress} via {smtp.host}:{smtp.port}
              {smtp.secure ? " (TLS)" : ""}
            </code>
            . Saving again replaces all values.
          </p>
        )}
        <form action={saveSmtp}>
          <div className="field">
            <label htmlFor="smtpHost">SMTP host</label>
            <input id="smtpHost" name="host" required />
          </div>
          <div className="field">
            <label htmlFor="smtpPort">Port</label>
            <input id="smtpPort" name="port" type="number" defaultValue={587} required />
          </div>
          <div className="field">
            <label htmlFor="smtpFromAddress">From address</label>
            <input id="smtpFromAddress" name="fromAddress" type="email" required />
          </div>
          <div className="field">
            <label htmlFor="smtpUser">Username (optional)</label>
            <input id="smtpUser" name="user" />
          </div>
          <div className="field">
            <label htmlFor="smtpPassword">Password (optional)</label>
            <input id="smtpPassword" name="password" type="password" />
          </div>
          <div className="field">
            <label htmlFor="smtpSecure">
              <input id="smtpSecure" name="secure" type="checkbox" style={{ width: "auto" }} /> Use TLS
            </label>
          </div>
          <button type="submit">Save</button>
        </form>
        {smtp && (
          <form action={clearSmtp} style={{ marginTop: 8 }}>
            <ConfirmSubmitButton
              className="secondary"
              message="Clear the SMTP configuration? Outbound email notifications will stop going out until it's reconfigured."
            >
              Clear
            </ConfirmSubmitButton>
          </form>
        )}
      </div>
    </main>
  );
}

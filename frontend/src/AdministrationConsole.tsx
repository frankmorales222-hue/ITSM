import {
  Component,
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";
import { api } from "./api";
import "./administration-console.css";

type Props = { bootstrap: any; onNavigate: (page: string) => void };
type Item = {
  id?: number;
  name?: string;
  active?: boolean;
  version?: number;
  [key: string]: any;
};
const roleKeys = [
  "end_user",
  "technician",
  "team_lead",
  "manager",
  "admin",
  "auditor",
];
const emptyUser = {
  username: "",
  email: "",
  display_name: "",
  temporary_password: "",
  role: "end_user",
  team_id: null,
  alternate_email: "",
  employee_number: "",
  phone: "",
  job_title: "",
  department_name: "",
  location_name: "",
  manager_user_id: null,
  timezone: "America/New_York",
  preferred_language: "en",
  notification_preferences: { email: true },
  auth_source: "Local",
  team_ids: [],
  group_ids: [],
  role_definition_ids: [],
  availability: "Available",
  active: true,
};
const permissionAreas = [
  "tickets",
  "assets",
  "users",
  "teams_and_queues",
  "forms",
  "approvals",
  "reports",
  "integrations",
  "administration",
  "audit",
];
const permissionActions = [
  "view_own",
  "view_team",
  "view_all",
  "create",
  "edit",
  "assign",
  "approve",
  "export",
  "configure",
  "administer",
];
const providerFields: any = {
  "Microsoft Entra ID": [
    "sync_scope",
    "included_groups",
    "deactivation_policy",
    "sync_schedule",
  ],
  "Active Directory / LDAP": [
    "server",
    "port",
    "tls_mode",
    "base_dn",
    "bind_dn",
    "user_search_base",
    "user_filter",
    "group_search_base",
    "group_filter",
    "unique_id_attribute",
    "email_attribute",
    "sync_schedule",
  ],
  LDAP: [
    "server",
    "port",
    "tls_mode",
    "base_dn",
    "bind_dn",
    "user_search_base",
    "user_filter",
    "group_search_base",
    "group_filter",
    "unique_id_attribute",
    "email_attribute",
    "sync_schedule",
  ],
  "SCIM 2.0": [
    "base_url",
    "auth_method",
    "users_path",
    "groups_path",
    "matching_attribute",
    "scope_filter",
    "attribute_mappings",
  ],
  "Microsoft 365": [
    "mailbox",
    "sender_name",
    "reply_to",
    "polling_interval",
    "attachment_limit_mb",
  ],
  "Google Workspace": [
    "client_id",
    "mailbox",
    "sender_name",
    "reply_to",
    "delivery_mode",
    "polling_interval",
    "pubsub_topic",
  ],
  "Generic SMTP / IMAP": [
    "smtp_host",
    "smtp_port",
    "smtp_tls",
    "imap_host",
    "imap_port",
    "imap_tls",
    "username",
    "from_address",
    "reply_to",
    "inbound_folder",
    "processed_folder",
    "polling_interval",
  ],
  "Generic SMTP/IMAP": [
    "smtp_host",
    "smtp_port",
    "smtp_tls",
    "imap_host",
    "imap_port",
    "imap_tls",
    "username",
    "from_address",
    "reply_to",
    "inbound_folder",
    "processed_folder",
    "polling_interval",
  ],
  RingCentral: [
    "ticket_creation_policy",
    "caller_match",
    "retention_days",
    "call_queue_ids",
    "did_queue_mappings",
    "extension_mappings",
  ],
};
const providerSecrets: any = {
  "Microsoft Entra ID": [],
  "Microsoft 365": [],
  RingCentral: [],
  "Active Directory / LDAP": ["bind_password"],
  LDAP: ["bind_password"],
  "SCIM 2.0": ["bearer_token", "oauth_client_secret"],
  "Google Workspace": ["client_secret", "service_account_json"],
  "Generic SMTP / IMAP": ["password"],
  "Generic SMTP/IMAP": ["password"],
};
const guidedProviders = ["Microsoft Entra ID", "Microsoft 365", "RingCentral"];

class AdminErrorBoundary extends Component<
  { children: ReactNode },
  { error: string }
> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  render() {
    return this.state.error ? (
      <div className="admin-failure">
        <h3>This section could not be displayed</h3>
        <p>{this.state.error}</p>
        <button onClick={() => location.reload()}>Reload Administration</button>
      </div>
    ) : (
      this.props.children
    );
  }
}
function Status({ active, label }: { active: boolean; label?: string }) {
  return (
    <span className={`console-status ${active ? "ok" : "off"}`}>
      {label || (active ? "Active" : "Inactive")}
    </span>
  );
}
function Toggle({
  value,
  onChange,
  label,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="console-toggle">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span />
      <b>{label}</b>
    </label>
  );
}
function Field({
  label,
  children,
  help,
  wide = false,
}: {
  label: string;
  children: ReactNode;
  help?: string;
  wide?: boolean;
}) {
  return (
    <label className={wide ? "wide" : ""}>
      <b>{label}</b>
      {children}
      {help && <small>{help}</small>}
    </label>
  );
}
function JsonEditor({
  value,
  onChange,
  rows = 5,
}: {
  value: any;
  onChange: (value: any) => void;
  rows?: number;
}) {
  const [text, setText] = useState(() => JSON.stringify(value || {}, null, 2)),
    [error, setError] = useState("");
  useEffect(() => setText(JSON.stringify(value || {}, null, 2)), [value]);
  function commit() {
    try {
      onChange(JSON.parse(text));
      setError("");
    } catch {
      setError("Enter valid JSON before saving.");
    }
  }
  return (
    <>
      <textarea
        rows={rows}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
      />
      {error && <small className="field-error">{error}</small>}
    </>
  );
}
function Modal({
  title,
  onClose,
  onSave,
  children,
  busy = false,
  danger,
}: {
  title: string;
  onClose: () => void;
  onSave?: (e: FormEvent) => void | Promise<void>;
  children: ReactNode;
  busy?: boolean;
  danger?: ReactNode;
}) {
  const [dirty, setDirty] = useState(false),
    [submitting, setSubmitting] = useState(false);
  function close() {
    if (dirty && onSave && !confirm("Discard your unsaved changes?")) return;
    onClose();
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!onSave || submitting || busy) return;
    setSubmitting(true);
    try {
      await onSave(e);
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <div className="console-modal-layer">
      <form
        className="console-modal"
        onSubmit={submit}
        onInput={() => setDirty(true)}
      >
        <header>
          <div>
            <p className="eyebrow">Administration editor</p>
            <h3>{title}</h3>
          </div>
          <button type="button" onClick={close} aria-label="Close editor">
            ×
          </button>
        </header>
        <div className="console-form">{children}</div>
        <footer>
          {danger}
          <span />
          <button type="button" onClick={close}>
            Cancel
          </button>
          {onSave && (
            <button className="primary" disabled={busy || submitting}>
              {busy || submitting ? "Saving…" : "Save changes"}
            </button>
          )}
        </footer>
      </form>
    </div>
  );
}
function Notice({
  type = "error",
  children,
}: {
  type?: string;
  children: ReactNode;
}) {
  return <div className={`console-notice ${type}`}>{children}</div>;
}

const navGroups = [
  [
    "People & access",
    [
      ["tech-users", "Tech users"],
      ["users", "All users"],
      ["groups", "Groups & group types"],
      ["roles", "Roles & permissions"],
    ],
  ],
  [
    "Service management",
    [
      ["teams", "Teams"],
      ["categories", "Categories"],
      ["queues", "Queues"],
      ["routing", "Routing rules"],
      ["incident-settings", "Incident forms & SLA"],
      ["forms", "Request forms"],
    ],
  ],
  [
    "Automation",
    [
      ["automation-center", "Automation Center"],
      ["announcements", "Announcements"],
      ["notifications", "Notifications & events"],
      ["smart-self-service", "Smart self-service"],
      ["workflows", "Approval workflows"],
    ],
  ],
  [
    "Integrations",
    [
      ["directory", "Directory & identity"],
      ["email", "Email"],
      ["telephony", "Telephony"],
    ],
  ],
  [
    "Security & system",
    [
      ["audit", "Audit log"],
      ["general", "General settings"],
      ["help-desk", "Help Desk Settings"],
      ["appearance", "Appearance"],
      ["https-certificate", "HTTPS certificate"],
      ["health", "Application health"],
      ["system-updates", "System updates"],
    ],
  ],
] as any;
const descriptions: any = {
  users: "Create, edit, secure, and deactivate user accounts.",
  groups:
    "Organize people for support, approvals, security, notifications, and reporting.",
  roles:
    "Protected ITIL-aligned roles provide standard least-privilege service-desk permissions.",
  teams:
    "Service-delivery units, technicians, regions, skills, capacity, and queue participation.",
  categories:
    "Maintain the category → subcategory → item hierarchy used by forms and routing.",
  queues:
    "Work buckets that define eligible teams and how technicians receive assignments.",
  routing:
    "Ordered conditions route tickets to queues, teams, workflows, and service policies.",
  "incident-settings":
    "Configure incident classification, impact and urgency priority, and response and resolution targets.",
  forms: "Build, test, save, and publish service request forms.",
  "automation-center": "Enable and configure service-desk automation one policy at a time. Every policy starts disabled.",
  announcements: "Publish clear service announcements to the portal, with optional endpoint-agent delivery when enabled.",
  notifications: "Editable event-driven customer and internal communications.",
  "smart-self-service":
    "Offer requesters approved solutions from resolved work while preserving technician escalation and audit history.",
  workflows:
    "Design approval steps for changes, access, purchases, and custom forms.",
  directory:
    "Configure provisioning and identity connections with provider-specific fields.",
  email:
    "Configure inbound ticket creation, outbound notifications, and message threading.",
  telephony:
    "Configure RingCentral and provider-neutral call-to-ticket behavior.",
  audit: "Review append-only administrative and security activity.",
  general: "Organization identity, support contacts, and defaults.",
  "help-desk":
    "Configure ticket behavior, agent workflow, customer access, security, and attachment limits.",
  appearance: "Choose the visual theme for this browser. Theme changes affect colors and styling only.",
  "https-certificate": "Install and verify the organization-issued HTTPS certificate used by Northstar Desk.",
  health: "Database, worker, migration, mailbox, and backup status.",
  "system-updates":
    "Upload signed offline releases, prevent downgrades, create a verified backup, and review installation history.",
};

export default function AdministrationConsole({
  bootstrap,
  onNavigate,
}: Props) {
  const [section, setSection] = useState("tech-users"),
    [find, setFind] = useState("");
  const visible = navGroups
    .map((g: any) => [
      g[0],
      g[1].filter((x: any) =>
        `${x[1]} ${descriptions[x[0]]}`
          .toLowerCase()
          .includes(find.toLowerCase()),
      ),
    ])
    .filter((g: any) => g[1].length);
  return (
    <div className="admin-console">
      <aside>
        <button
          className="console-brand"
          onClick={() => setSection("tech-users")}
        >
          <span>⚙</span>
          <div>
            <strong>Help Desk Settings</strong>
            <small>Administration center</small>
          </div>
        </button>
        <label className="console-search">
          <span>⌕</span>
          <input
            value={find}
            onChange={(e) => setFind(e.target.value)}
            placeholder="Find a setting…"
          />
        </label>
        <nav>
          {visible.map((g: any) => (
            <section key={g[0]}>
              <h3>{g[0]}</h3>
              {g[1].map((x: any) => (
                <button
                  className={section === x[0] ? "active" : ""}
                  key={x[0]}
                  onClick={() => setSection(x[0])}
                >
                  <span>{x[1]}</span>
                  <b>›</b>
                </button>
              ))}
            </section>
          ))}
        </nav>
      </aside>
      <main>
        <header className="console-header">
          <div>
            <p className="eyebrow">Administration</p>
            <h2>
              {
                navGroups
                  .flatMap((x: any) => x[1])
                  .find((x: any) => x[0] === section)?.[1]
              }
            </h2>
            <p>{descriptions[section]}</p>
          </div>
          <Status active label="System online" />
        </header>
        <AdminErrorBoundary key={section}>
          {section === "tech-users" ? (
            <TechUsers />
          ) : section === "users" ? (
            <Users />
          ) : section === "groups" ? (
            <Groups />
          ) : section === "roles" ? (
            <Roles />
          ) : section === "teams" ? (
            <Teams />
          ) : section === "categories" ? (
            <Categories />
          ) : section === "queues" ? (
            <Queues />
          ) : section === "routing" ? (
            <Routing />
          ) : section === "incident-settings" ? (
            <IncidentSettings onOpenStudio={() => onNavigate("studio")} />
          ) : section === "automation-center" ? (
            <AutomationCenter />
          ) : section === "announcements" ? (
            <AnnouncementsAdmin />
          ) : section === "notifications" ? (
            <Notifications />
          ) : section === "smart-self-service" ? (
            <SmartSelfService />
          ) : ["directory", "email", "telephony"].includes(section) ? (
            <Integrations kind={section} />
          ) : section === "forms" ? (
            <Jump
              title="Request Form Studio"
              text="Build live, testable forms; save drafts and templates; publish only when ready."
              action="Open Form Studio"
              onClick={() => onNavigate("studio")}
            />
          ) : section === "workflows" ? (
            <Jump
              title="Approval workflow designer"
              text="Create approval chains for change management and any published request form."
              action="Open workflow designer"
              onClick={() => onNavigate("studio")}
            />
          ) : section === "general" ? (
            <General />
          ) : section === "help-desk" ? (
            <HelpDeskSettings />
          ) : section === "appearance" ? (
            <Appearance />
          ) : section === "https-certificate" ? (
            <HttpsCertificate />
          ) : section === "system-updates" ? (
            <SystemUpdates />
          ) : (
            <ReadOnly kind={section} />
          )}
        </AdminErrorBoundary>
      </main>
    </div>
  );
}

type SmartSettings = {
  enabled: boolean;
  mode: "suggest_to_tech" | "auto_send";
  confidence_threshold: number;
  waiting_hours: number;
  safe_categories: string[];
  excluded_categories: string[];
};
type KnowledgeArticle = {
  id: number;
  title: string;
  summary: string;
  steps: string[];
  category: string;
  status: "draft" | "published" | "archived";
  tags?: string[];
  risk_level?: "low" | "medium" | "high";
  auto_send_allowed?: boolean;
  version?: number;
  successful_uses?: number;
  total_uses?: number;
};

function SmartSelfService() {
  const resource = useLoad("/admin/smart-self-service");
  const [settings, setSettings] = useState<SmartSettings | null>(null);
  const [editing, setEditing] = useState<Partial<KnowledgeArticle> | null>(null);
  const [stepText, setStepText] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!resource.data) return;
    const value = resource.data.settings || resource.data;
    setSettings({
      enabled: value.enabled === true,
      mode: value.mode === "auto_send" ? "auto_send" : "suggest_to_tech",
      confidence_threshold: Number(value.confidence_threshold ?? 85),
      waiting_hours: Number(value.waiting_hours ?? 24),
      safe_categories: Array.isArray(value.safe_categories) ? value.safe_categories : [],
      excluded_categories: Array.isArray(value.excluded_categories)
        ? value.excluded_categories : ["Security", "Privileged access", "Major incident"],
    });
  }, [resource.data]);
  const articles: KnowledgeArticle[] = Array.isArray(resource.data?.articles) ? resource.data.articles : [];
  async function saveSettings() {
    if (!settings || busy) return;
    setBusy(true); setMessage("");
    try {
      await api("/admin/smart-self-service", { method: "PUT", body: JSON.stringify(settings) });
      setMessage(settings.enabled ? "Smart Self-Service settings saved." : "Smart Self-Service remains disabled.");
      resource.load();
    } catch (error: any) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  function openArticle(article?: KnowledgeArticle) {
    const value: Partial<KnowledgeArticle> = article ? { ...article } : {
      title: "", summary: "", steps: [], category: "General", status: "draft",
      tags: [], risk_level: "low", auto_send_allowed: false,
    };
    setEditing(value); setStepText((value.steps || []).join("\n")); setMessage("");
  }
  async function saveArticle() {
    if (!editing || busy) return;
    const payload = {
      title: (editing.title || "").trim(), summary: (editing.summary || "").trim(),
      category: editing.category || "General",
      steps: stepText.split("\n").map((step) => step.trim()).filter(Boolean),
      status: editing.status === "archived" ? "archived" : "draft",
      tags: editing.tags || [], risk_level: editing.risk_level || "low",
      auto_send_allowed: editing.risk_level === "low" && Boolean(editing.auto_send_allowed),
    };
    if (!payload.title || !payload.summary || !payload.steps.length) {
      setMessage("Enter a title, summary, and at least one troubleshooting step."); return;
    }
    setBusy(true); setMessage("");
    try {
      await api(editing.id ? `/admin/smart-self-service/articles/${editing.id}` : "/admin/smart-self-service/articles", {
        method: editing.id ? "PATCH" : "POST", body: JSON.stringify(payload),
      });
      setEditing(null); resource.load();
    } catch (error: any) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  async function articleAction(article: KnowledgeArticle, action: "publish" | "archive") {
    if (!confirm(`${action === "publish" ? "Publish" : "Archive"} "${article.title}"?`)) return;
    setBusy(true); setMessage("");
    try {
      await api(action === "publish" ? `/admin/smart-self-service/articles/${article.id}/publish` : `/admin/smart-self-service/articles/${article.id}`, {
        method: action === "publish" ? "POST" : "DELETE",
      });
      resource.load();
    } catch (error: any) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  if (resource.error) return <Notice>{resource.error} <button onClick={resource.load}>Retry</button></Notice>;
  if (resource.loading || !settings) return <div className="loading">Loading Smart Self-Service...</div>;
  return <Panel title="Approved knowledge assistance" text="Suggestions use only published, tenant-owned knowledge. Tickets remain available for technician help." action={<Status active={settings.enabled} label={settings.enabled ? "Enabled" : "Disabled by default"} />}>
    {message && !editing && <Notice type={message.includes("saved") || message.includes("disabled") ? "success" : "error"}>{message}</Notice>}
    <div className="smart-service-settings">
      <div className="smart-service-master"><div><strong>Smart Self-Service</strong><p>Turn this on only after your first articles have been reviewed and published.</p></div><Toggle value={settings.enabled} onChange={(enabled) => setSettings({ ...settings, enabled })} label={settings.enabled ? "Enabled" : "Disabled"} /></div>
      <div className="console-form-grid">
        <Field label="Delivery mode" help="Start with technician suggestions; automatic email uses the same approved articles."><select value={settings.mode} onChange={(event) => setSettings({ ...settings, mode: event.target.value as SmartSettings["mode"] })}><option value="suggest_to_tech">Suggest to technician</option><option value="auto_send">Automatically email requester</option></select></Field>
        <Field label="Minimum confidence" help="Only matches at or above this percentage may be offered."><input type="number" min="1" max="100" step="1" value={settings.confidence_threshold} onChange={(event) => setSettings({ ...settings, confidence_threshold: Number(event.target.value) })} /></Field>
        <Field label="Requester response window" help="Hours before this ticket returns to normal queue attention."><input type="number" min="1" max="168" value={settings.waiting_hours} onChange={(event) => setSettings({ ...settings, waiting_hours: Number(event.target.value) })} /></Field>
        <Field label="Eligible categories" help="Comma-separated low-risk categories. Empty means none are eligible."><input value={settings.safe_categories.join(", ")} onChange={(event) => setSettings({ ...settings, safe_categories: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} placeholder="Software, Hardware, General" /></Field>
        <Field label="Always excluded" help="Security-sensitive categories never receive automatic instructions." wide><input value={settings.excluded_categories.join(", ")} onChange={(event) => setSettings({ ...settings, excluded_categories: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></Field>
      </div>
      <div className="smart-service-actions"><button className="primary" disabled={busy} onClick={saveSettings}>{busy ? "Saving..." : "Save settings"}</button></div>
    </div>
    <div className="smart-knowledge-header"><div><h3>Knowledge articles</h3><p>Drafts must be reviewed and published before they can be suggested.</p></div><button className="primary" onClick={() => openArticle()}>New article</button></div>
    <div className="smart-knowledge-list">{articles.length ? articles.map((article) => <article key={article.id}><div><div className="smart-article-title"><strong>{article.title}</strong><Status active={article.status === "published"} label={article.status} /></div><p>{article.summary}</p><small>{article.category} - Version {article.version || 1} - {article.successful_uses || 0} successful of {article.total_uses || 0} uses</small></div><div><button onClick={() => openArticle(article)}>Edit</button>{article.status !== "published" && <button onClick={() => articleAction(article, "publish")}>Publish</button>}{article.status !== "archived" && <button onClick={() => articleAction(article, "archive")}>Archive</button>}</div></article>) : <div className="empty"><p>No knowledge articles have been created.</p></div>}</div>
    {editing && <Modal title={editing.id ? "Edit knowledge article" : "Create knowledge article"} onClose={() => setEditing(null)} onSave={saveArticle} busy={busy}>
      {message && <Notice>{message}</Notice>}
      {editing.status === "published" && <Notice>Saving changes creates a draft that must be reviewed and published again.</Notice>}
      <Field label="Article title"><input required value={editing.title || ""} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /></Field>
      <Field label="Category"><input required value={editing.category || ""} onChange={(event) => setEditing({ ...editing, category: event.target.value })} /></Field>
      <Field label="Search tags" help="Comma-separated words requesters may use, such as Excel, frozen, spreadsheet."><input value={(editing.tags || []).join(", ")} onChange={(event) => setEditing({ ...editing, tags: event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean) })} /></Field>
      <Field label="Risk level" help="Only low-risk articles can be approved for automatic sending."><select value={editing.risk_level || "low"} onChange={(event) => setEditing({ ...editing, risk_level: event.target.value as KnowledgeArticle["risk_level"], auto_send_allowed: event.target.value === "low" ? editing.auto_send_allowed : false })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></Field>
      <Field label="Requester summary" wide><textarea required rows={3} value={editing.summary || ""} onChange={(event) => setEditing({ ...editing, summary: event.target.value })} /></Field>
      <Field label="Troubleshooting steps" help="Enter one safe, requester-facing step per line." wide><textarea required rows={8} value={stepText} onChange={(event) => setStepText(event.target.value)} /></Field>
      <Field label="Automatic delivery approval" help="When automatic delivery mode is enabled, this reviewed low-risk article may be emailed without technician review." wide><label className="console-check"><input type="checkbox" checked={Boolean(editing.auto_send_allowed)} disabled={editing.risk_level !== "low"} onChange={(event) => setEditing({ ...editing, auto_send_allowed: event.target.checked })} /> Allow this low-risk article to be sent automatically after publication</label></Field>
    </Modal>}
  </Panel>;
}

function Appearance() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem("northstar-theme");
    return saved === "infinx-modern" || saved === "dark-mode" ? saved : "northstar-original";
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("northstar-theme", theme);
  }, [theme]);
  const choices = [
    ["northstar-original", "Northstar Original", "Current Northstar colors", "#174b43"],
    ["infinx-modern", "Modern Look", "Clean light workspace", "#0369a1"],
    ["dark-mode", "Dark Mode", "Low-light workspace", "#11cfc9"],
  ];
  return (
    <Panel title="Appearance" text="Choose the visual theme for this browser. Changes affect colors and styling only." action={null}>
      <div className="theme-picker-options">
        {choices.map(([value, label, description, swatch]) => (
          <button type="button" key={value} className={theme === value ? "active" : ""} onClick={() => setTheme(value)} aria-pressed={theme === value}>
            <span className="theme-swatch" style={{ "--theme-swatch": swatch } as any} />
            <strong>{label}</strong>
            <small>{description}</small>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function HttpsCertificate() {
  const resource = useLoad("/admin/https-certificate");
  const [mode, setMode] = useState<"pem" | "pfx">("pem");
  const [certificate, setCertificate] = useState<File | null>(null);
  const [privateKey, setPrivateKey] = useState<File | null>(null);
  const [intermediateChain, setIntermediateChain] = useState<File | null>(null);
  const [pfx, setPfx] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function install() {
    if ((mode === "pem" && (!certificate || !privateKey)) || (mode === "pfx" && !pfx)) return;
    if (!confirm("Northstar will validate this certificate, retain a backup of the existing HTTPS configuration, and restart only the HTTPS service. Continue?")) return;
    setBusy(true); setMessage("");
    try {
      const body = new FormData();
      if (mode === "pem") {
        body.append("certificate", certificate!);
        body.append("private_key", privateKey!);
        if (intermediateChain) body.append("intermediate_chain", intermediateChain);
      }
      else body.append("pfx", pfx!);
      if (password) body.append("password", password);
      const result = await api("/admin/https-certificate/install", { method: "POST", body });
      setMessage(result.status); setCertificate(null); setPrivateKey(null); setIntermediateChain(null); setPfx(null); setPassword("");
      window.setTimeout(resource.load, 3500);
    } catch (e: any) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  if (resource.error) return <Notice>{resource.error} <button onClick={resource.load}>Retry</button></Notice>;
  if (!resource.data) return <div className="loading">Loading certificate status…</div>;
  const data = resource.data;
  return <Panel title="HTTPS certificate" text="Install an organization-issued certificate without opening server configuration files. Northstar validates the certificate before replacing the active HTTPS setting." action={<Status active={data.mode === "custom" && !data.restart_failed} label={data.mode === "custom" ? "Custom certificate" : "Internal certificate"} />}>
    <div className="certificate-summary"><strong>{data.hostname || "Northstar website"}</strong><span>{data.status}</span>{data.subject && <small>Issued to: {data.subject} · Expires: {new Date(data.expires_at).toLocaleString()}</small>}</div>
    {message && <div className={`console-notice ${message.toLowerCase().includes("validated") || message.toLowerCase().includes("restarted") ? "success" : "error"}`}>{message}</div>}
    <div className="certificate-mode"><button className={mode === "pem" ? "active" : ""} onClick={() => setMode("pem")}>Certificate and private key</button><button className={mode === "pfx" ? "active" : ""} onClick={() => setMode("pfx")}>PFX package</button></div>
    {mode === "pem" ? <div className="certificate-fields"><label>Server certificate<input type="file" accept=".pem,.cer,.crt" onChange={e => setCertificate(e.target.files?.[0] || null)} /><small>Select the website certificate issued for this server name.</small></label><label>Private key<input type="file" accept=".pem,.key,.txt" onChange={e => setPrivateKey(e.target.files?.[0] || null)} /><small>Select the private key created with the certificate request.</small></label><label className="certificate-chain">Intermediate certificate chain <em>(recommended)</em><input type="file" accept=".p7b,.p7c,.pem,.cer,.crt" onChange={e => setIntermediateChain(e.target.files?.[0] || null)} /><small>Upload the GoDaddy .p7b or PEM intermediate chain. Northstar assembles the full chain safely.</small></label></div> : <div className="certificate-fields"><label>PFX package<input type="file" accept=".pfx,.p12" onChange={e => setPfx(e.target.files?.[0] || null)} /></label></div>}
    <label className="certificate-password">Password, if the private key or PFX is protected<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" /><small>The password is used only to read the uploaded file and is never saved.</small></label>
    <div className="certificate-actions"><small>Northstar checks that the key matches the certificate, it is valid for this website name, and the HTTPS service accepts it. Your previous configuration is preserved before anything changes.</small><button className="primary" disabled={busy || (mode === "pem" ? !certificate || !privateKey : !pfx)} onClick={install}>{busy ? "Validating certificate…" : "Validate and install certificate"}</button></div>
  </Panel>;
}

function SystemUpdates() {
  const resource = useLoad("/admin/system-updates");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function upload() {
    if (!file) return;
    setBusy(true); setMessage("");
    try {
      const body = new FormData(); body.append("package", file);
      const result = await api("/admin/system-updates/upload", { method: "POST", body });
      setMessage(`Version ${result.version} passed signature and integrity validation.`);
      setFile(null); resource.load();
    } catch (e: any) { setMessage(e.message); }
    finally { setBusy(false); }
  }
  async function install(item: any) {
    const confirmation = prompt(`This creates a database backup, places the service in maintenance mode, and restarts the server.\n\nEnter ${item.version} to continue:`);
    if (confirmation !== item.version) return;
    setBusy(true); setMessage("");
    try {
      const result = await api(`/admin/system-updates/${item.id}/install`, { method: "POST", body: JSON.stringify({ confirm_version: confirmation }) });
      setMessage(result.message); resource.load();
    } catch (e: any) { setMessage(e.message); setBusy(false); }
  }
  if (resource.error) return <Notice>{resource.error} <button onClick={resource.load}>Retry</button></Notice>;
  if (!resource.data) return <div className="loading">Loading update history…</div>;
  const data = resource.data;
  return <Panel title="Signed offline updates" text={descriptions["system-updates"]} action={<Status active={data.verification_configured} label={data.verification_configured ? `Trust key ${data.verification_key_fingerprint}` : "Signing key required"} />}>
    <div className="update-current"><div><small>Installed version</small><strong>{data.current_version}</strong></div><p>Only a cryptographically signed version newer than this installation will be accepted. Previously recorded versions and package IDs cannot be reused.</p></div>
    {!data.verification_configured && <Notice>{data.configuration_error || "Configure ITSM_UPDATE_PUBLIC_KEY with the release-signing public key before uploading updates."}</Notice>}
    {message && <div className={`console-notice ${message.toLowerCase().includes("pass") || message.toLowerCase().includes("scheduled") ? "success" : "error"}`}>{message}</div>}
    <div className="update-upload">
      <label><span>Northstar update package</span><input type="file" accept=".nsupdate" disabled={!data.verification_configured || busy} onChange={e => setFile(e.target.files?.[0] || null)} /><small>Choose the signed .nsupdate file supplied for this release. Source-code archives and ordinary ZIP files are rejected.</small></label>
      <button className="primary" disabled={!file || busy || !data.verification_configured} onClick={upload}>{busy ? "Validating…" : "Upload and validate"}</button>
    </div>
    <div className="update-history">
      <h3>Version history</h3>
      {data.updates.length ? data.updates.map((item: any) => <article key={item.id}>
        <div><strong>Version {item.version}</strong><Status active={item.status === "Installed" || item.status === "Validated"} label={item.status} /><p>{item.release_notes || "No release notes supplied."}</p><small>Publisher: {item.publisher || "Unknown"} · Uploaded {new Date(item.created_at).toLocaleString()} · SHA-256 {item.package_sha256.slice(0, 12)}…</small>{item.backup_path && <small>Verified backup: {item.backup_path}</small>}{item.message && <small>{item.message}</small>}</div>
        {(["Validated", "Failed"].includes(item.status) && item.version !== data.current_version) && <button className="primary" disabled={busy} onClick={() => install(item)}>Install update</button>}
      </article>) : <div className="empty"><p>No update packages have been uploaded.</p></div>}
    </div>
  </Panel>;
}

function useLoad(path: string) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const load = () => {
    setLoading(true);
    setError("");
    api(path)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    load();
  }, [path]);
  return { data, setData, error, loading, load };
}
function Panel({
  title,
  text,
  action,
  children,
}: {
  title: string;
  text: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="console-panel">
      <div className="console-toolbar">
        <div>
          <h3>{title}</h3>
          <p>{text}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function IncidentSettings({ onOpenStudio }: { onOpenStudio: () => void }) {
  const resource = useLoad("/admin/incident-settings"),
    [draft, setDraft] = useState<any>(null),
    [tab, setTab] = useState("classification"),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (resource.data) setDraft(JSON.parse(JSON.stringify(resource.data)));
  }, [resource.data]);
  if (resource.loading || !draft)
    return <div className="loading">Loading incident configuration…</div>;
  const taxonomy = draft.taxonomy || {},
    kinds = [
      ["request_types", "Request types"],
      ["modes", "Modes / sources"],
      ["levels", "Support levels"],
      ["statuses", "Statuses"],
    ];
  const impacts = (taxonomy.impacts || []).filter(
      (x: any) => x.active !== false,
    ),
    urgencies = (taxonomy.urgencies || []).filter(
      (x: any) => x.active !== false,
    ),
    priorities = (taxonomy.priorities || []).filter(
      (x: any) => x.active !== false,
    );
  function changeOption(kind: string, index: number, key: string, value: any) {
    setDraft({
      ...draft,
      taxonomy: {
        ...taxonomy,
        [kind]: taxonomy[kind].map((item: any, i: number) =>
          i === index ? { ...item, [key]: value } : item,
        ),
      },
    });
  }
  function addOption(kind: string) {
    setDraft({
      ...draft,
      taxonomy: {
        ...taxonomy,
        [kind]: [
          ...(taxonomy[kind] || []),
          {
            key: `custom_${Date.now()}`,
            name: "New option",
            active: true,
            ...(kind === "statuses"
              ? {
                  description: "",
                  color: "#397da1",
                  lifecycle: "active",
                  sla_runs: true,
                  order: ((taxonomy[kind] || []).length + 1) * 10,
                }
              : {}),
          },
        ],
      },
    });
  }
  function updatePolicy(index: number, key: string, value: any) {
    setDraft({
      ...draft,
      sla: {
        ...draft.sla,
        policies: draft.sla.policies.map((item: any, i: number) =>
          i === index ? { ...item, [key]: value } : item,
        ),
      },
    });
  }
  async function save() {
    setError("");
    setMessage("");
    try {
      const result = await api("/admin/incident-settings", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setDraft(result);
      setMessage("Incident configuration saved and recorded in the audit log.");
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Incident forms, priority, and SLA"
      text="Configure classification, calculated priority, operational calendars, pauses, and escalations."
      action={
        <div>
          <button onClick={onOpenStudio}>Edit incident layout</button>
          <button className="primary" onClick={save}>
            Save configuration
          </button>
        </div>
      }
    >
      {message && <Notice type="success">{message}</Notice>}
      {(error || resource.error) && <Notice>{error || resource.error}</Notice>}
      <div className="console-tabs">
        <button
          className={tab === "classification" ? "active" : ""}
          onClick={() => setTab("classification")}
        >
          Classification
        </button>
        <button
          className={tab === "matrix" ? "active" : ""}
          onClick={() => setTab("matrix")}
        >
          Priority matrix
        </button>
        <button
          className={tab === "sla" ? "active" : ""}
          onClick={() => setTab("sla")}
        >
          SLA and calendars
        </button>
      </div>
      {tab === "classification" && (
        <div className="incident-config-groups">
          {kinds.map(([kind, title]) => (
            <section key={kind}>
              <header>
                <div>
                  <h4>{title}</h4>
                  <small>Stable keys are retained when labels change.</small>
                </div>
                <button onClick={() => addOption(kind)}>Add option</button>
              </header>
              {(taxonomy[kind] || []).map((item: any, index: number) => (
                <article key={item.key}>
                  <input
                    aria-label={`${title} name`}
                    value={item.name}
                    onChange={(e) =>
                      changeOption(kind, index, "name", e.target.value)
                    }
                  />
                  {kind === "statuses" && (
                    <>
                      <input
                        value={item.description || ""}
                        onChange={(e) =>
                          changeOption(
                            kind,
                            index,
                            "description",
                            e.target.value,
                          )
                        }
                        placeholder="Description"
                      />
                      <input
                        type="color"
                        value={item.color || "#397da1"}
                        onChange={(e) =>
                          changeOption(kind, index, "color", e.target.value)
                        }
                      />
                      <select
                        value={item.lifecycle || "active"}
                        onChange={(e) =>
                          changeOption(kind, index, "lifecycle", e.target.value)
                        }
                      >
                        {["active", "paused", "resolved", "closed"].map(
                          (value) => (
                            <option key={value}>{value}</option>
                          ),
                        )}
                      </select>
                      <label>
                        <input
                          type="checkbox"
                          checked={item.sla_runs !== false}
                          onChange={(e) =>
                            changeOption(
                              kind,
                              index,
                              "sla_runs",
                              e.target.checked,
                            )
                          }
                        />{" "}
                        SLA runs
                      </label>
                    </>
                  )}
                  <label>
                    <input
                      type="checkbox"
                      checked={item.active !== false}
                      onChange={(e) =>
                        changeOption(kind, index, "active", e.target.checked)
                      }
                    />{" "}
                    Active
                  </label>
                </article>
              ))}
            </section>
          ))}
        </div>
      )}
      {tab === "matrix" && (
        <div className="priority-matrix">
          <table>
            <thead>
              <tr>
                <th>Impact ↓ / Urgency →</th>
                {urgencies.map((urgency: any) => (
                  <th key={urgency.key}>{urgency.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {impacts.map((impact: any) => (
                <tr key={impact.key}>
                  <th>{impact.name}</th>
                  {urgencies.map((urgency: any) => {
                    const key = `${impact.name}|${urgency.name}`;
                    return (
                      <td key={urgency.key}>
                        <select
                          value={draft.priority_matrix.cells[key] || ""}
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              priority_matrix: {
                                ...draft.priority_matrix,
                                cells: {
                                  ...draft.priority_matrix.cells,
                                  [key]: e.target.value,
                                },
                              },
                            })
                          }
                        >
                          <option value="">Choose priority</option>
                          {priorities.map((priority: any) => (
                            <option key={priority.key}>{priority.name}</option>
                          ))}
                        </select>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Every active impact and urgency combination requires a priority.
          </p>
        </div>
      )}
      {tab === "sla" && (
        <div className="sla-admin-grid">
          <section className="sla-calendar-editor">
            <h4>Operational-hours calendars</h4>
            <p>
              Calendars use IANA time zones, working days, opening and closing
              times, and ISO holiday dates.
            </p>
            <JsonEditor
              rows={12}
              value={draft.sla.calendars || []}
              onChange={(value) =>
                setDraft({ ...draft, sla: { ...draft.sla, calendars: value } })
              }
            />
          </section>
          <div className="sla-policy-list">
            {(draft.sla.policies || []).map((policy: any, index: number) => (
              <article key={policy.key}>
                <header>
                  <div>
                    <strong>{policy.name}</strong>
                    <small>{policy.priority} priority</small>
                  </div>
                  <Toggle
                    label="Active"
                    value={policy.active !== false}
                    onChange={(value) => updatePolicy(index, "active", value)}
                  />
                </header>
                <label>
                  Response target (operational minutes)
                  <input
                    type="number"
                    min="1"
                    value={policy.response_minutes}
                    onChange={(e) =>
                      updatePolicy(index, "response_minutes", +e.target.value)
                    }
                  />
                </label>
                <label>
                  Resolution target (operational minutes)
                  <input
                    type="number"
                    min="1"
                    value={policy.resolution_minutes}
                    onChange={(e) =>
                      updatePolicy(index, "resolution_minutes", +e.target.value)
                    }
                  />
                </label>
                <label>
                  Calendar key
                  <input
                    value={policy.calendar || "24x7"}
                    onChange={(e) =>
                      updatePolicy(index, "calendar", e.target.value)
                    }
                  />
                </label>
                <label>
                  Pause statuses
                  <input
                    value={(policy.pause_statuses || []).join(", ")}
                    onChange={(e) =>
                      updatePolicy(
                        index,
                        "pause_statuses",
                        e.target.value
                          .split(",")
                          .map((value) => value.trim())
                          .filter(Boolean),
                      )
                    }
                  />
                </label>
                <label>
                  Escalations (JSON)
                  <JsonEditor
                    value={policy.escalations || []}
                    onChange={(value) =>
                      updatePolicy(index, "escalations", value)
                    }
                  />
                </label>
              </article>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function TechUsers() {
  const resource = useLoad("/admin/users"),
    teams = useLoad("/admin/teams");
  const [query, setQuery] = useState(""),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [editing, setEditing] = useState<any>(null),
    [resetting, setResetting] = useState<any>(null),
    [resetPassword, setResetPassword] = useState(""),
    [busy, setBusy] = useState(false);
  const staff = (resource.data || []).filter(
    (user: any) =>
      user.active &&
      ["technician", "team_lead", "manager", "admin"].includes(user.role) &&
      `${user.display_name} ${user.email} ${user.username} ${user.team || ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function startCreate() {
    setError("");
    setMessage("");
    setEditing({
      ...emptyUser,
      role: "technician",
      job_title: "Support Technician",
    });
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const teamIds = editing.team_id ? [editing.team_id] : [];
      const saved = await api("/admin/users", {
        method: "POST",
        body: JSON.stringify({ ...editing, team_ids: teamIds }),
      });
      setEditing(null);
      setMessage(
        `${saved.display_name} was created as a tech user and can now receive assigned work.`,
      );
      resource.load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(user: any) {
    setError("");
    try {
      await api(`/admin/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          availability:
            user.availability === "Available" ? "Unavailable" : "Available",
        }),
      });
      setMessage(`${user.display_name} assignment availability updated.`);
      resource.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  function startReset(user: any) {
    setError("");
    setMessage("");
    setResetPassword("");
    setResetting(user);
  }
  async function resetTechPassword(e: FormEvent) {
    e.preventDefault();
    if (!resetting) return;
    setBusy(true);
    setError("");
    try {
      await api(`/admin/users/${resetting.id}/reset-password`, {
        method: "POST",
        body: JSON.stringify({ temporary_password: resetPassword }),
      });
      setResetting(null);
      setResetPassword("");
      setMessage(
        `${resetting.display_name}'s password was reset. Active sessions were revoked and a password change is required at next sign-in.`,
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function deleteTech(user: any) {
    if (
      !confirm(
        `Delete ${user.display_name} from Tech users? Their sign-in and automatic assignment will be disabled. Existing tickets and audit history will be preserved.`,
      )
    )
      return;
    setError("");
    try {
      await api(`/admin/users/${user.id}`, { method: "DELETE" });
      setMessage(
        `${user.display_name} was removed from Tech users. Historical service records were preserved.`,
      );
      resource.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Tech users"
      text="Create and manage service-desk technicians, leads, managers, assignment eligibility, teams, and access."
      action={
        <div>
          <Status active label={`${staff.length} tech users`} />
          <button className="primary" onClick={startCreate}>
            Add tech user
          </button>
        </div>
      }
    >
      <div className="console-filters">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search technician by name, email, username, or team…"
        />
      </div>
      {message && <Notice type="success">{message}</Notice>}
      {(resource.error || teams.error || error) && (
        <Notice>{resource.error || teams.error || error}</Notice>
      )}
      {resource.loading ? (
        <div className="loading">Loading tech users…</div>
      ) : (
        <div className="console-table tech-user-table">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Username</th>
                <th>Role</th>
                <th>Team</th>
                <th>Availability</th>
                <th>Auto-assign</th>
                <th>MFA</th>
                <th>Access</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {staff.map((user: any) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.display_name}</strong>
                    <small>{user.job_title || "Service desk staff"}</small>
                  </td>
                  <td>{user.email}</td>
                  <td>{user.username}</td>
                  <td>{user.role.replaceAll("_", " ")}</td>
                  <td>{user.team || "Not assigned"}</td>
                  <td>{user.availability}</td>
                  <td>
                    <button
                      className={`assignment-switch ${user.availability === "Available" ? "on" : ""}`}
                      onClick={() => toggle(user)}
                      aria-label={`Toggle auto assignment for ${user.display_name}`}
                    >
                      <span />
                    </button>
                  </td>
                  <td>{user.mfa_enabled ? "Enabled" : "Not configured"}</td>
                  <td>
                    <Status active={user.active} />
                  </td>
                  <td>
                    <div className="tech-row-actions">
                      {user.auth_source === "Local" && (
                        <button type="button" onClick={() => startReset(user)}>
                          Reset password
                        </button>
                      )}
                      {user.role !== "admin" && (
                        <button
                          type="button"
                          className="danger"
                          onClick={() => deleteTech(user)}
                        >
                          Delete tech
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="report-guidance">
            Available technicians participate in round-robin and workload
            assignment. Use <strong>All users</strong> for advanced identity,
            security, and notification settings.
          </p>
        </div>
      )}
      {editing && (
        <Modal
          title="Create tech user"
          onClose={() => setEditing(null)}
          onSave={save}
          busy={busy}
        >
          <Field label="Display name">
            <input
              required
              autoFocus
              value={editing.display_name}
              onChange={(e) =>
                setEditing({ ...editing, display_name: e.target.value })
              }
            />
          </Field>
          <Field label="Username">
            <input
              required
              minLength={2}
              value={editing.username}
              onChange={(e) =>
                setEditing({ ...editing, username: e.target.value })
              }
            />
          </Field>
          <Field label="Primary email">
            <input
              required
              type="email"
              value={editing.email}
              onChange={(e) =>
                setEditing({ ...editing, email: e.target.value })
              }
            />
          </Field>
          <Field
            label="Temporary password"
            help="At least 12 characters with uppercase, lowercase, a number, and a symbol. The user must change it at first sign-in."
          >
            <input
              required
              type="password"
              minLength={12}
              value={editing.temporary_password}
              onChange={(e) =>
                setEditing({ ...editing, temporary_password: e.target.value })
              }
            />
          </Field>
          <Field
            label="Tech role"
            help="Technician is the standard role for service-desk agents."
          >
            <select
              value={editing.role}
              onChange={(e) => setEditing({ ...editing, role: e.target.value })}
            >
              {["technician", "team_lead", "manager", "admin"].map((role) => (
                <option value={role} key={role}>
                  {role.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Primary team"
            help="Controls service ownership and queue eligibility."
          >
            <select
              value={editing.team_id || ""}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  team_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No primary team yet</option>
              {(teams.data || [])
                .filter((team: any) => team.active !== false)
                .map((team: any) => (
                  <option value={team.id} key={team.id}>
                    {team.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Job title">
            <input
              value={editing.job_title}
              onChange={(e) =>
                setEditing({ ...editing, job_title: e.target.value })
              }
            />
          </Field>
          <Field label="Employee ID">
            <input
              value={editing.employee_number}
              onChange={(e) =>
                setEditing({ ...editing, employee_number: e.target.value })
              }
            />
          </Field>
          <Field label="Location / region">
            <input
              value={editing.location_name}
              onChange={(e) =>
                setEditing({ ...editing, location_name: e.target.value })
              }
            />
          </Field>
          <Field label="Telephone extension">
            <input
              value={editing.ringcentral_extension_number || ""}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  ringcentral_extension_number: e.target.value,
                })
              }
            />
          </Field>
          <div className="wide provider-status">
            <strong>Local sign-in account</strong>
            <p>
              The account is created active and available for assignment. Its
              temporary password must be changed at first sign-in.
            </p>
          </div>
        </Modal>
      )}
      {resetting && (
        <Modal
          title={`Reset ${resetting.display_name}'s password`}
          onClose={() => {
            setResetting(null);
            setResetPassword("");
          }}
          onSave={resetTechPassword}
          busy={busy}
        >
          <div className="wide provider-status">
            <strong>This is a security-sensitive action</strong>
            <p>
              Saving will revoke the technician's active sessions and require
              them to change this temporary password at their next sign-in.
            </p>
          </div>
          <Field
            label="New temporary password"
            wide
            help="At least 12 characters with uppercase, lowercase, a number, and a symbol."
          >
            <input
              required
              autoFocus
              type="password"
              minLength={12}
              value={resetPassword}
              onChange={(e) => setResetPassword(e.target.value)}
              autoComplete="new-password"
            />
          </Field>
        </Modal>
      )}
    </Panel>
  );
}

function Users() {
  const users = useLoad("/admin/users"),
    teams = useLoad("/admin/teams"),
    groups = useLoad("/admin/groups"),
    roles = useLoad("/admin/roles");
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [roleFilter, setRoleFilter] = useState("all"),
    [teamFilter, setTeamFilter] = useState("all"),
    [sourceFilter, setSourceFilter] = useState("all"),
    [availabilityFilter, setAvailabilityFilter] = useState("all"),
    [editing, setEditing] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [resetPassword, setResetPassword] = useState("");
  const rows = (users.data || []).filter(
    (x: any) =>
      `${x.display_name} ${x.email} ${x.username} ${x.employee_number} ${x.role} ${x.team || ""} ${x.auth_source} ${x.location_name}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (filter === "all" || (filter === "active" ? x.active : !x.active)) &&
      (roleFilter === "all" || x.role === roleFilter) &&
      (teamFilter === "all" || String(x.team_id || "none") === teamFilter) &&
      (sourceFilter === "all" || x.auth_source === sourceFilter) &&
      (availabilityFilter === "all" || x.availability === availabilityFilter),
  );
  async function open(row: any) {
    setError("");
    setEditing(row.id ? await api(`/admin/users/${row.id}`) : { ...emptyUser });
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const method = editing.id ? "PATCH" : "POST",
        path = editing.id ? `/admin/users/${editing.id}` : "/admin/users";
      const saved = await api(path, { method, body: JSON.stringify(editing) });
      setMessage(`${saved.display_name} saved.`);
      setEditing(null);
      users.load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function deactivate() {
    if (
      !editing.id ||
      !confirm(
        `Deactivate ${editing.display_name}? Sign-in will be disabled, sessions revoked, and historical records preserved.`,
      )
    )
      return;
    try {
      await api(`/admin/users/${editing.id}`, { method: "DELETE" });
      setEditing(null);
      users.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="User directory"
      text="Role controls permissions. Team controls service ownership. Source identifies the authoritative identity system."
      action={
        <button className="primary" onClick={() => open(emptyUser)}>
          Add user
        </button>
      }
    >
      <div className="console-filters">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, email, ID, role, team, source, or location…"
        />
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </select>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
        >
          <option value="all">All roles</option>
          {roleKeys.map((x) => (
            <option key={x} value={x}>
              {x.replaceAll("_", " ")}
            </option>
          ))}
        </select>
        <select
          value={teamFilter}
          onChange={(e) => setTeamFilter(e.target.value)}
        >
          <option value="all">All teams</option>
          <option value="none">No team</option>
          {(teams.data || []).map((x: any) => (
            <option key={x.id} value={String(x.id)}>
              {x.name}
            </option>
          ))}
        </select>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
        >
          <option value="all">All identity sources</option>
          {["Local", "Microsoft Entra ID", "LDAP", "SCIM"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <select
          value={availabilityFilter}
          onChange={(e) => setAvailabilityFilter(e.target.value)}
        >
          <option value="all">All availability</option>
          {["Available", "Busy", "Away", "On leave", "Unavailable"].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
      </div>
      {message && <Notice type="success">{message}</Notice>}
      {(users.error || error) && (
        <Notice>
          {users.error || error} <button onClick={users.load}>Retry</button>
        </Notice>
      )}
      {users.loading ? (
        <div className="loading">Loading users…</div>
      ) : (
        <div className="console-table">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Role / source</th>
                <th>Team / source</th>
                <th>Location</th>
                <th>Availability</th>
                <th>Access</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((x: any) => (
                <tr key={x.id} onClick={() => open(x)}>
                  <td>
                    <strong>{x.display_name}</strong>
                    <small>
                      {x.email} · {x.employee_number || "No employee ID"}
                    </small>
                  </td>
                  <td>
                    {x.role.replaceAll("_", " ")}
                    <small>{x.role_source}</small>
                  </td>
                  <td>
                    {x.team || "Not assigned"}
                    <small>{x.team_source}</small>
                  </td>
                  <td>{x.location_name || "—"}</td>
                  <td>{x.availability}</td>
                  <td>
                    <Status active={x.active} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && (
        <Modal
          title={editing.id ? `Edit ${editing.display_name}` : "Create user"}
          onClose={() => setEditing(null)}
          onSave={save}
          busy={busy}
          danger={
            editing.id && (
              <button type="button" className="danger" onClick={deactivate}>
                Deactivate user
              </button>
            )
          }
        >
          <Field label="Display name">
            <input
              required
              value={editing.display_name || ""}
              onChange={(e) =>
                setEditing({ ...editing, display_name: e.target.value })
              }
            />
          </Field>
          <Field label="Username">
            <input
              required
              disabled={!!editing.id}
              value={editing.username || ""}
              onChange={(e) =>
                setEditing({ ...editing, username: e.target.value })
              }
            />
          </Field>
          <Field label="Primary email">
            <input
              required
              type="email"
              value={editing.email || ""}
              onChange={(e) =>
                setEditing({ ...editing, email: e.target.value })
              }
            />
          </Field>
          <Field label="Alternate email">
            <input
              type="email"
              value={editing.alternate_email || ""}
              onChange={(e) =>
                setEditing({ ...editing, alternate_email: e.target.value })
              }
            />
          </Field>
          {!editing.id && (
            <Field
              label="Temporary password"
              help="12+ characters with uppercase, lowercase, number, and symbol."
            >
              <input
                required
                type="password"
                value={editing.temporary_password || ""}
                onChange={(e) =>
                  setEditing({ ...editing, temporary_password: e.target.value })
                }
              />
            </Field>
          )}
          <Field label="Employee ID">
            <input
              value={editing.employee_number || ""}
              onChange={(e) =>
                setEditing({ ...editing, employee_number: e.target.value })
              }
            />
          </Field>
          <Field label="Phone">
            <input
              value={editing.phone || ""}
              onChange={(e) =>
                setEditing({ ...editing, phone: e.target.value })
              }
            />
          </Field>
          <Field label="Job title">
            <input
              value={editing.job_title || ""}
              onChange={(e) =>
                setEditing({ ...editing, job_title: e.target.value })
              }
            />
          </Field>
          <Field label="Department">
            <input
              value={editing.department_name || ""}
              onChange={(e) =>
                setEditing({ ...editing, department_name: e.target.value })
              }
            />
          </Field>
          <Field label="Location / region">
            <input
              value={editing.location_name || ""}
              onChange={(e) =>
                setEditing({ ...editing, location_name: e.target.value })
              }
            />
          </Field>
          <Field label="Manager">
            <select
              value={editing.manager_user_id || ""}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  manager_user_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No manager</option>
              {(users.data || [])
                .filter((x: any) => x.id !== editing.id)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.display_name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="System role" help="Controls the base API permissions.">
            <select
              value={editing.role}
              onChange={(e) => setEditing({ ...editing, role: e.target.value })}
            >
              {roleKeys.map((x) => (
                <option key={x} value={x}>
                  {x.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Primary team"
            help="The service-delivery team used by default."
          >
            <select
              value={editing.team_id || ""}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  team_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No primary team</option>
              {(teams.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Additional roles">
            <SearchPicker
              options={roles.data || []}
              value={editing.role_definition_ids || []}
              onChange={(v) =>
                setEditing({ ...editing, role_definition_ids: v })
              }
            />
          </Field>
          <Field label="All teams">
            <SearchPicker
              options={teams.data || []}
              value={editing.team_ids || []}
              onChange={(v) => setEditing({ ...editing, team_ids: v })}
            />
          </Field>
          <Field label="Groups">
            <SearchPicker
              options={groups.data || []}
              value={editing.group_ids || []}
              onChange={(v) => setEditing({ ...editing, group_ids: v })}
            />
          </Field>
          <Field label="Identity source">
            <select
              value={editing.auth_source || "Local"}
              onChange={(e) =>
                setEditing({ ...editing, auth_source: e.target.value })
              }
            >
              {["Local", "Microsoft Entra ID", "LDAP", "SCIM"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <Field label="Time zone">
            <input
              value={editing.timezone || ""}
              onChange={(e) =>
                setEditing({ ...editing, timezone: e.target.value })
              }
            />
          </Field>
          <Field label="Language">
            <input
              value={editing.preferred_language || "en"}
              onChange={(e) =>
                setEditing({ ...editing, preferred_language: e.target.value })
              }
            />
          </Field>
          <Field label="Availability">
            <select
              value={editing.availability || "Available"}
              onChange={(e) =>
                setEditing({ ...editing, availability: e.target.value })
              }
            >
              {["Available", "Busy", "Away", "On leave", "Unavailable"].map(
                (x) => (
                  <option key={x}>{x}</option>
                ),
              )}
            </select>
          </Field>
          <Field label="Telephone extension">
            <input
              value={editing.ringcentral_extension_number || ""}
              onChange={(e) =>
                setEditing({
                  ...editing,
                  ringcentral_extension_number: e.target.value,
                })
              }
            />
          </Field>
          <Field
            label="Notification preferences"
            wide
            help="Organization-specific preferences stored with the user."
          >
            <JsonEditor
              value={editing.notification_preferences || {}}
              onChange={(value) =>
                setEditing({ ...editing, notification_preferences: value })
              }
            />
          </Field>
          <Toggle
            label="Force password change at next login"
            value={!!editing.must_change_password}
            onChange={(v) =>
              setEditing({ ...editing, must_change_password: v })
            }
          />
          <Toggle
            label="Account active"
            value={editing.active !== false}
            onChange={(v) => setEditing({ ...editing, active: v })}
          />
          {editing.id && (
            <div className="wide console-related">
              <strong>Related records</strong>
              <span>
                {editing.assigned_assets?.length || 0} assigned assets
              </span>
              <span>{editing.open_tickets?.length || 0} open tickets</span>
              <Field
                label="New temporary password"
                wide
                help="Local accounts only. Resetting revokes active sessions and forces a password change."
              >
                <input
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  placeholder="Enter a strong temporary password"
                />
              </Field>
              <button
                type="button"
                disabled={!resetPassword}
                onClick={async () => {
                  try {
                    await api(`/admin/users/${editing.id}/reset-password`, {
                      method: "POST",
                      body: JSON.stringify({
                        temporary_password: resetPassword,
                      }),
                    });
                    setResetPassword("");
                    setMessage(
                      "Password reset. The user must change it at next login.",
                    );
                  } catch (e: any) {
                    setError(e.message);
                  }
                }}
              >
                Reset local password
              </button>
              <button
                type="button"
                onClick={async () => {
                  try {
                    await api(
                      `/admin/users/${editing.id}/force-password-change`,
                      { method: "POST" },
                    );
                    setEditing({ ...editing, must_change_password: true });
                    setMessage("Password change required at next login.");
                  } catch (e: any) {
                    setError(e.message);
                  }
                }}
              >
                Force password change
              </button>
              <button
                type="button"
                onClick={async () => {
                  await api(`/admin/users/${editing.id}/revoke-sessions`, {
                    method: "POST",
                  });
                  setMessage("Active sessions revoked.");
                }}
              >
                Revoke active sessions
              </button>
            </div>
          )}
        </Modal>
      )}
    </Panel>
  );
}

function SearchPicker({
  options,
  value,
  onChange,
  placeholder = "Search by name or email…",
}: {
  options: any[];
  value: number[];
  onChange: (ids: number[]) => void;
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const selected = options.filter((x) => value.includes(x.id)),
    matches = options
      .filter(
        (x) =>
          !value.includes(x.id) &&
          `${x.name || x.display_name} ${x.email || ""} ${x.username || ""}`
            .toLowerCase()
            .includes(q.toLowerCase()),
      )
      .slice(0, 20);
  return (
    <div className="search-picker">
      <div className="picker-chips">
        {selected.map((x) => (
          <button
            type="button"
            key={x.id}
            onClick={() => onChange(value.filter((id) => id !== x.id))}
          >
            {x.name || x.display_name} ×
          </button>
        ))}
      </div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
      />
      {q && (
        <div className="picker-results">
          {matches.map((x) => (
            <button
              type="button"
              key={x.id}
              onClick={() => {
                onChange([...value, x.id]);
                setQ("");
              }}
            >
              <strong>{x.name || x.display_name}</strong>
              <small>{x.email || x.description || ""}</small>
            </button>
          ))}
          {!matches.length && <small>No matching people or records.</small>}
        </div>
      )}
    </div>
  );
}

function Groups() {
  const groups = useLoad("/admin/groups"),
    types = useLoad("/admin/group-types"),
    users = useLoad("/admin/users");
  const [tab, setTab] = useState("groups"),
    [edit, setEdit] = useState<any>(null),
    [error, setError] = useState(""),
    [reassignTo, setReassignTo] = useState("");
  const newGroup = {
      name: "",
      group_type: "Custom",
      group_type_id: null,
      description: "",
      source: "Local",
      active: true,
      member_ids: [],
      owner_ids: [],
      manager_user_id: null,
      email: "",
      region: "",
      timezone: "America/New_York",
      escalation_contact: "",
    },
    newType = {
      name: "",
      description: "",
      icon: "group",
      color: "#176453",
      purpose: "",
      allowed_uses: [],
      sort_order: 100,
      active: true,
    };
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      const base = tab === "groups" ? "/admin/groups" : "/admin/group-types";
      await api(edit.id ? `${base}/${edit.id}` : base, {
        method: edit.id ? "PATCH" : "POST",
        body: JSON.stringify(edit),
      });
      setEdit(null);
      (tab === "groups" ? groups : types).load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (
      !edit.id ||
      !confirm(
        `Archive ${edit.name}? Existing historical references will be preserved.`,
      )
    )
      return;
    try {
      const query =
        tab === "types" && reassignTo ? `?reassign_to=${reassignTo}` : "";
      await api(
        `${tab === "groups" ? "/admin/groups" : "/admin/group-types"}/${edit.id}${query}`,
        { method: "DELETE" },
      );
      setEdit(null);
      setReassignTo("");
      (tab === "groups" ? groups : types).load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function duplicate() {
    try {
      await api(`/admin/groups/${edit.id}/duplicate`, { method: "POST" });
      setEdit(null);
      groups.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Groups and group types"
      text="Groups collect people; group types describe how those groups may be used."
      action={
        <button
          className="primary"
          onClick={() =>
            setEdit(tab === "groups" ? { ...newGroup } : { ...newType })
          }
        >
          Add {tab === "groups" ? "group" : "group type"}
        </button>
      }
    >
      <div className="console-tabs">
        <button
          className={tab === "groups" ? "active" : ""}
          onClick={() => setTab("groups")}
        >
          Groups
        </button>
        <button
          className={tab === "types" ? "active" : ""}
          onClick={() => setTab("types")}
        >
          Group types
        </button>
      </div>
      {error && <Notice>{error}</Notice>}
      <div className="card-list">
        {(tab === "groups" ? groups.data || [] : types.data || []).map(
          (x: any) => (
            <article key={x.id} onClick={() => setEdit({ ...x })}>
              <div
                className="record-icon"
                style={{ background: tab === "types" ? x.color : undefined }}
              >
                {tab === "groups" ? "G" : x.icon?.[0]?.toUpperCase()}
              </div>
              <div>
                <h4>{x.name}</h4>
                <p>{x.description || x.purpose || "No description"}</p>
                <small>
                  {tab === "groups"
                    ? `${x.group_type} · ${x.member_count} people · ${x.source}`
                    : `${x.group_count} groups · order ${x.sort_order}`}
                </small>
              </div>
              <Status active={x.active} />
              <button>Edit</button>
            </article>
          ),
        )}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} ${tab === "groups" ? "group" : "group type"}`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <div className="record-actions">
                {tab === "groups" && (
                  <button type="button" onClick={duplicate}>
                    Duplicate
                  </button>
                )}
                {tab === "types" && edit.group_count > 0 && (
                  <select
                    value={reassignTo}
                    onChange={(e) => setReassignTo(e.target.value)}
                  >
                    <option value="">Choose replacement type</option>
                    {(types.data || [])
                      .filter((x: any) => x.id !== edit.id && x.active)
                      .map((x: any) => (
                        <option key={x.id} value={x.id}>
                          {x.name}
                        </option>
                      ))}
                  </select>
                )}
                <button type="button" className="danger" onClick={archive}>
                  Archive
                </button>
              </div>
            )
          }
        >
          {tab === "groups" ? (
            <>
              <Field label="Name">
                <input
                  required
                  value={edit.name}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                />
              </Field>
              <Field label="Group type">
                <select
                  value={edit.group_type_id || ""}
                  onChange={(e) => {
                    const found = (types.data || []).find(
                      (x: any) => x.id === +e.target.value,
                    );
                    setEdit({
                      ...edit,
                      group_type_id: +e.target.value,
                      group_type: found?.name || "Custom",
                    });
                  }}
                >
                  <option value="">Choose type</option>
                  {(types.data || []).map((x: any) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Source">
                <select
                  value={edit.source}
                  onChange={(e) => setEdit({ ...edit, source: e.target.value })}
                >
                  {["Local", "Microsoft Entra ID", "LDAP", "SCIM"].map((x) => (
                    <option key={x}>{x}</option>
                  ))}
                </select>
              </Field>
              <Field label="Group email">
                <input
                  type="email"
                  value={edit.email || ""}
                  onChange={(e) => setEdit({ ...edit, email: e.target.value })}
                />
              </Field>
              <Field label="Region">
                <input
                  value={edit.region || ""}
                  onChange={(e) => setEdit({ ...edit, region: e.target.value })}
                />
              </Field>
              <Field label="Time zone">
                <input
                  value={edit.timezone || ""}
                  onChange={(e) =>
                    setEdit({ ...edit, timezone: e.target.value })
                  }
                />
              </Field>
              <Field
                label="Members"
                wide
                help="Search by name, email, username, department, role, team, or location."
              >
                <SearchPicker
                  options={users.data || []}
                  value={edit.member_ids || []}
                  onChange={(v) => setEdit({ ...edit, member_ids: v })}
                />
              </Field>
              <Field label="Owners" wide>
                <SearchPicker
                  options={users.data || []}
                  value={edit.owner_ids || []}
                  onChange={(v) => setEdit({ ...edit, owner_ids: v })}
                />
              </Field>
              <Field label="Manager">
                <select
                  value={edit.manager_user_id || ""}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      manager_user_id: e.target.value ? +e.target.value : null,
                    })
                  }
                >
                  <option value="">No manager</option>
                  {(users.data || []).map((x: any) => (
                    <option key={x.id} value={x.id}>
                      {x.display_name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Escalation contact">
                <input
                  value={edit.escalation_contact || ""}
                  onChange={(e) =>
                    setEdit({ ...edit, escalation_contact: e.target.value })
                  }
                />
              </Field>
              <Field label="Description" wide>
                <textarea
                  value={edit.description || ""}
                  onChange={(e) =>
                    setEdit({ ...edit, description: e.target.value })
                  }
                />
              </Field>
            </>
          ) : (
            <>
              <Field label="Name">
                <input
                  required
                  value={edit.name}
                  onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                />
              </Field>
              <Field label="Purpose">
                <input
                  value={edit.purpose || ""}
                  onChange={(e) =>
                    setEdit({ ...edit, purpose: e.target.value })
                  }
                />
              </Field>
              <Field label="Icon">
                <input
                  value={edit.icon || ""}
                  onChange={(e) => setEdit({ ...edit, icon: e.target.value })}
                />
              </Field>
              <Field label="Color">
                <input
                  type="color"
                  value={edit.color || "#176453"}
                  onChange={(e) => setEdit({ ...edit, color: e.target.value })}
                />
              </Field>
              <Field label="Display order">
                <input
                  type="number"
                  value={edit.sort_order}
                  onChange={(e) =>
                    setEdit({ ...edit, sort_order: +e.target.value })
                  }
                />
              </Field>
              <Field
                label="Allowed uses"
                wide
                help="Comma-separated uses such as queues, approvals, notifications, permissions, and reporting."
              >
                <input
                  value={(edit.allowed_uses || []).join(", ")}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      allowed_uses: e.target.value
                        .split(",")
                        .map((x) => x.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Field>
              <Field label="Description" wide>
                <textarea
                  value={edit.description || ""}
                  onChange={(e) =>
                    setEdit({ ...edit, description: e.target.value })
                  }
                />
              </Field>
            </>
          )}
          <Toggle
            label="Active"
            value={edit.active !== false}
            onChange={(v) => setEdit({ ...edit, active: v })}
          />
        </Modal>
      )}
    </Panel>
  );
}

function Roles() {
  const roles = useLoad("/admin/roles"),
    users = useLoad("/admin/users");
  const [edit, setEdit] = useState<any>(null),
    [effective, setEffective] = useState<any>(null),
    [error, setError] = useState("");
  const empty = {
    key: "",
    name: "",
    description: "",
    permissions: {},
    parent_role_id: null,
    active: true,
  };
  function toggle(area: string, action: string) {
    const list = edit.permissions?.[area] || [];
    setEdit({
      ...edit,
      permissions: {
        ...edit.permissions,
        [area]: list.includes(action)
          ? list.filter((x: string) => x !== action)
          : [...list, action],
      },
    });
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(edit.id ? `/admin/roles/${edit.id}` : "/admin/roles", {
        method: edit.id ? "PATCH" : "POST",
        body: JSON.stringify(edit),
      });
      setEdit(null);
      roles.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function duplicate() {
    try {
      await api(`/admin/roles/${edit.id}/duplicate`, { method: "POST" });
      setEdit(null);
      roles.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (
      edit.system ||
      !confirm(
        `Archive ${edit.name}? Assigned users keep their protected base role.`,
      )
    )
      return;
    try {
      await api(`/admin/roles/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      roles.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Role-based access control"
      text="System roles provide safe defaults. Custom roles add organization-specific permission bundles."
      action={
        <button className="primary" onClick={() => setEdit({ ...empty })}>
          Add custom role
        </button>
      }
    >
      {error && <Notice>{error}</Notice>}
      <div className="role-cards">
        {(roles.data || []).map((x: any) => (
          <article key={x.id} onClick={() => setEdit({ ...x })}>
            <div>
              <h4>{x.name}</h4>
              <p>{x.description}</p>
              <small>
                {x.user_count} users ·{" "}
                {x.system ? "Protected system role" : "Custom role"}
              </small>
            </div>
            <Status active={x.active} />
          </article>
        ))}
      </div>
      <div className="effective-box">
        <strong>View effective permissions</strong>
        <select
          onChange={async (e) =>
            setEffective(
              e.target.value
                ? await api(
                    `/admin/users/${e.target.value}/effective-permissions`,
                  )
                : null,
            )
          }
        >
          <option value="">Choose a user</option>
          {(users.data || []).map((x: any) => (
            <option key={x.id} value={x.id}>
              {x.display_name}
            </option>
          ))}
        </select>
        {effective && (
          <pre>{JSON.stringify(effective.permissions, null, 2)}</pre>
        )}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} role`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <div className="record-actions">
                <button type="button" onClick={duplicate}>
                  Duplicate role
                </button>
                {!edit.system && (
                  <button type="button" className="danger" onClick={archive}>
                    Archive role
                  </button>
                )}
              </div>
            )
          }
        >
          <Field label="Role name">
            <input
              required
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Field>
          <Field
            label="Role key"
            help={
              edit.system
                ? "System role keys cannot be changed."
                : "Lowercase letters, numbers, and underscores."
            }
          >
            <input
              required
              disabled={edit.system}
              value={edit.key}
              onChange={(e) => setEdit({ ...edit, key: e.target.value })}
            />
          </Field>
          <Field label="Inherits from">
            <select
              value={edit.parent_role_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  parent_role_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No parent role</option>
              {(roles.data || [])
                .filter((x: any) => x.id !== edit.id)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Description" wide>
            <textarea
              value={edit.description || ""}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
          </Field>
          <div className="wide permission-matrix">
            <table>
              <thead>
                <tr>
                  <th>Area</th>
                  {permissionActions.map((x) => (
                    <th key={x}>{x.replaceAll("_", " ")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {permissionAreas.map((area) => (
                  <tr key={area}>
                    <th>{area.replaceAll("_", " ")}</th>
                    {permissionActions.map((action) => (
                      <td key={action}>
                        <input
                          type="checkbox"
                          checked={(edit.permissions?.[area] || []).includes(
                            action,
                          )}
                          onChange={() => toggle(area, action)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Toggle
            label="Role active"
            value={edit.active !== false}
            onChange={(v) => setEdit({ ...edit, active: v })}
          />
        </Modal>
      )}
    </Panel>
  );
}

function Teams() {
  const teams = useLoad("/admin/teams"),
    users = useLoad("/admin/users"),
    categories = useLoad("/admin/categories");
  const [edit, setEdit] = useState<any>(null),
    [error, setError] = useState("");
  const empty = {
    name: "",
    key: "",
    description: "",
    lead_user_id: null,
    backup_lead_user_id: null,
    member_ids: [],
    primary_member_ids: [],
    region: "",
    supported_locations: [],
    timezone: "America/New_York",
    business_hours: {},
    supported_services: [],
    supported_categories: [],
    skills: [],
    default_capacity: 10,
    escalation_team_id: null,
    active: true,
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(edit.id ? `/admin/teams/${edit.id}` : "/admin/teams", {
        method: edit.id ? "PATCH" : "POST",
        body: JSON.stringify(edit),
      });
      setEdit(null);
      teams.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (
      !edit.id ||
      !confirm(
        `Archive ${edit.name}? Queue and ticket history will be preserved.`,
      )
    )
      return;
    try {
      await api(`/admin/teams/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      teams.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Service-delivery teams"
      text="Teams define technicians, leadership, skills, regions, schedules, capacity, and queue eligibility."
      action={
        <button className="primary" onClick={() => setEdit({ ...empty })}>
          Add team
        </button>
      }
    >
      {error && <Notice>{error}</Notice>}
      <div className="card-grid">
        {(teams.data || []).map((x: any) => (
          <article key={x.id} onClick={() => setEdit({ ...x })}>
            <h4>{x.name}</h4>
            <p>{x.description || `${x.region || "Global"} support team`}</p>
            <div>
              <b>{x.member_ids.length}</b>
              <span>members</span>
              <b>{x.open_ticket_count}</b>
              <span>open tickets</span>
              <b>{x.available_technician_count}</b>
              <span>available</span>
            </div>
            <Status active={x.active} />
            <small>{x.queue_ids?.length || 0} queues</small>
          </article>
        ))}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} team`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <button type="button" className="danger" onClick={archive}>
                Archive team
              </button>
            )
          }
        >
          <Field label="Name">
            <input
              required
              value={edit.name}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  name: e.target.value,
                  key: edit.id
                    ? edit.key
                    : e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
                })
              }
            />
          </Field>
          <Field label="Unique key">
            <input
              required
              value={edit.key}
              onChange={(e) => setEdit({ ...edit, key: e.target.value })}
            />
          </Field>
          <Field label="Team lead">
            <select
              value={edit.lead_user_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  lead_user_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">Choose lead</option>
              {(users.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.display_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Backup lead">
            <select
              value={edit.backup_lead_user_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  backup_lead_user_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">Choose backup</option>
              {(users.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.display_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Region">
            <input
              value={edit.region || ""}
              onChange={(e) => setEdit({ ...edit, region: e.target.value })}
            />
          </Field>
          <Field label="Time zone">
            <input
              value={edit.timezone || ""}
              onChange={(e) => setEdit({ ...edit, timezone: e.target.value })}
            />
          </Field>
          <Field label="Default technician capacity">
            <input
              type="number"
              min="1"
              value={edit.default_capacity}
              onChange={(e) =>
                setEdit({ ...edit, default_capacity: +e.target.value })
              }
            />
          </Field>
          <Field label="Escalation team">
            <select
              value={edit.escalation_team_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  escalation_team_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No escalation team</option>
              {(teams.data || [])
                .filter((x: any) => x.id !== edit.id)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Members" wide>
            <SearchPicker
              options={users.data || []}
              value={edit.member_ids || []}
              onChange={(v) => setEdit({ ...edit, member_ids: v })}
            />
          </Field>
          <Field
            label="Primary members"
            wide
            help="Primary membership controls the technician's default workspace."
          >
            <SearchPicker
              options={(users.data || []).filter((x: any) =>
                (edit.member_ids || []).includes(x.id),
              )}
              value={edit.primary_member_ids || []}
              onChange={(v) => setEdit({ ...edit, primary_member_ids: v })}
            />
          </Field>
          <Field label="Supported category IDs">
            <SearchPicker
              options={categories.data || []}
              value={edit.supported_categories || []}
              onChange={(v) => setEdit({ ...edit, supported_categories: v })}
            />
          </Field>
          <Field label="Supported locations" wide>
            <input
              value={(edit.supported_locations || []).join(", ")}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  supported_locations: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
          <Field label="Supported services" wide>
            <input
              value={(edit.supported_services || []).join(", ")}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  supported_services: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
          <Field
            label="Business hours"
            wide
            help="JSON calendar such as days, start, end, and holiday calendar."
          >
            <JsonEditor
              value={edit.business_hours || {}}
              onChange={(value) => setEdit({ ...edit, business_hours: value })}
            />
          </Field>
          <Field label="Skills" wide>
            <input
              value={(edit.skills || []).join(", ")}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  skills: e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                })
              }
            />
          </Field>
          <Field label="Description" wide>
            <textarea
              value={edit.description || ""}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
          </Field>
          <Toggle
            label="Team active"
            value={edit.active !== false}
            onChange={(v) => setEdit({ ...edit, active: v })}
          />
        </Modal>
      )}
    </Panel>
  );
}

function Categories() {
  const resource = useLoad("/admin/categories");
  const [edit, setEdit] = useState<any>(null),
    [error, setError] = useState("");
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(
        edit.id ? `/admin/categories/${edit.id}` : "/admin/categories",
        { method: edit.id ? "PATCH" : "POST", body: JSON.stringify(edit) },
      );
      setEdit(null);
      resource.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (
      !edit.id ||
      !confirm(
        `Archive ${edit.name}? Existing tickets keep their historical category value.`,
      )
    )
      return;
    try {
      await api(`/admin/categories/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      resource.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Service categories"
      text="Categories are reusable by forms, queues, routing conditions, SLA policies, and reports."
      action={
        <button
          className="primary"
          onClick={() =>
            setEdit({
              name: "",
              parent_id: null,
              level: "category",
              description: "",
              sort_order: 100,
              configuration: {},
              active: true,
            })
          }
        >
          Add category
        </button>
      }
    >
      {(resource.error || error) && (
        <Notice>
          {resource.error || error}{" "}
          <button onClick={resource.load}>Retry</button>
        </Notice>
      )}
      {resource.loading ? (
        <div className="loading">Loading categories…</div>
      ) : (
        <div className="tree-list">
          {(resource.data || []).map((x: any) => (
            <button key={x.id} onClick={() => setEdit({ ...x })}>
              <span className={`tree-level ${x.level}`} />
              <div>
                <strong>{x.name}</strong>
                <small>
                  {x.level} · order {x.sort_order}
                </small>
              </div>
              <Status active={x.active} />
            </button>
          ))}
        </div>
      )}
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} category`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <button type="button" className="danger" onClick={archive}>
                Archive category
              </button>
            )
          }
        >
          <Field label="Name">
            <input
              required
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Field>
          <Field label="Level">
            <select
              value={edit.level}
              onChange={(e) => setEdit({ ...edit, level: e.target.value })}
            >
              <option value="category">Category</option>
              <option value="subcategory">Subcategory</option>
              <option value="item">Item</option>
            </select>
          </Field>
          <Field label="Parent">
            <select
              value={edit.parent_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  parent_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">No parent</option>
              {(resource.data || [])
                .filter((x: any) => x.id !== edit.id)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Display order">
            <input
              type="number"
              value={edit.sort_order}
              onChange={(e) =>
                setEdit({ ...edit, sort_order: +e.target.value })
              }
            />
          </Field>
          <Field label="Description" wide>
            <textarea
              value={edit.description || ""}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
          </Field>
          <Toggle
            label="Active"
            value={edit.active !== false}
            onChange={(v) => setEdit({ ...edit, active: v })}
          />
        </Modal>
      )}
    </Panel>
  );
}

function Queues() {
  const queues = useLoad("/admin/queues"),
    teams = useLoad("/admin/teams"),
    users = useLoad("/admin/users");
  const [edit, setEdit] = useState<any>(null),
    [simulation, setSimulation] = useState<any>(null),
    [error, setError] = useState("");
  const empty = {
    name: "",
    key: "",
    team_id: "",
    manager_user_id: null,
    description: "",
    assignment_strategy: "round_robin",
    configuration: {
      region: "",
      locations: [],
      channels: ["portal"],
      max_capacity: 10,
      max_wait_minutes: 60,
      self_assignment: true,
      overflow_queue_id: null,
      fallback_behavior: "triage",
      sla_policy: "",
      notification_policy: "",
      visibility: "team",
    },
    priority_order: 100,
    eligible_teams: [],
    active: true,
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(edit.id ? `/admin/queues/${edit.id}` : "/admin/queues", {
        method: edit.id ? "PATCH" : "POST",
        body: JSON.stringify(edit),
      });
      setEdit(null);
      queues.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  function setConfig(k: string, v: any) {
    setEdit({ ...edit, configuration: { ...edit.configuration, [k]: v } });
  }
  async function archive() {
    if (
      !edit.id ||
      !confirm(
        `Archive ${edit.name}? Existing tickets and reporting history will be preserved.`,
      )
    )
      return;
    try {
      await api(`/admin/queues/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      queues.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Assignment queues"
      text="Routing rules place tickets into a queue. The queue determines eligible teams and how an available technician is selected."
      action={
        <button className="primary" onClick={() => setEdit({ ...empty })}>
          Add queue
        </button>
      }
    >
      {error && <Notice>{error}</Notice>}
      <div className="queue-help">
        <b>Example:</b> Location = United States → US Support Queue → US-Tech
        team → round robin among available technicians.
      </div>
      <div className="card-list">
        {(queues.data || []).map((x: any) => (
          <article key={x.id}>
            <div className="record-icon">Q</div>
            <div onClick={() => setEdit({ ...x })}>
              <h4>{x.name}</h4>
              <p>{x.description || "No operational description"}</p>
              <small>
                {x.team} owner · {x.eligible_teams.length} eligible teams ·{" "}
                {x.assignment_strategy.replaceAll("_", " ")}
              </small>
            </div>
            <Status active={x.active} />
            <button
              onClick={async () =>
                setSimulation(
                  await api(`/admin/queues/${x.id}/simulate`, {
                    method: "POST",
                  }),
                )
              }
            >
              Simulate
            </button>
            <button onClick={() => setEdit({ ...x })}>Edit</button>
          </article>
        ))}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} queue`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <button type="button" className="danger" onClick={archive}>
                Archive queue
              </button>
            )
          }
        >
          <Field label="Queue name">
            <input
              required
              value={edit.name}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  name: e.target.value,
                  key: edit.id
                    ? edit.key
                    : e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
                })
              }
            />
          </Field>
          <Field label="Unique key">
            <input
              required
              value={edit.key}
              onChange={(e) => setEdit({ ...edit, key: e.target.value })}
            />
          </Field>
          <Field
            label="Owning team"
            help="Accountable for the queue and its service outcomes."
          >
            <select
              required
              value={edit.team_id}
              onChange={(e) => setEdit({ ...edit, team_id: +e.target.value })}
            >
              <option value="">Choose team</option>
              {(teams.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Queue manager">
            <select
              value={edit.manager_user_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  manager_user_id: e.target.value ? +e.target.value : null,
                })
              }
            >
              <option value="">Choose manager</option>
              {(users.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.display_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assignment strategy">
            <select
              value={edit.assignment_strategy}
              onChange={(e) =>
                setEdit({ ...edit, assignment_strategy: e.target.value })
              }
            >
              {[
                "round_robin",
                "least_active",
                "lowest_workload",
                "skills_based",
                "priority_weighted",
                "fixed_assignee",
                "manual",
              ].map((x) => (
                <option key={x} value={x}>
                  {x.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Queue priority">
            <input
              type="number"
              value={edit.priority_order}
              onChange={(e) =>
                setEdit({ ...edit, priority_order: +e.target.value })
              }
            />
          </Field>
          <Field
            label="Eligible teams"
            wide
            help="A queue can use multiple teams. The first selected team receives eligibility priority 100."
          >
            <SearchPicker
              options={teams.data || []}
              value={(edit.eligible_teams || []).map((x: any) => x.team_id)}
              onChange={(v) =>
                setEdit({
                  ...edit,
                  eligible_teams: v.map((id, i) => ({
                    team_id: id,
                    eligibility_priority: (i + 1) * 100,
                    weight: 100,
                    schedule: {},
                    active: true,
                  })),
                })
              }
            />
          </Field>
          <Field label="Region / country">
            <input
              value={edit.configuration?.region || ""}
              onChange={(e) => setConfig("region", e.target.value)}
            />
          </Field>
          <Field label="Channels">
            <input
              value={(edit.configuration?.channels || []).join(", ")}
              onChange={(e) =>
                setConfig(
                  "channels",
                  e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          <Field label="Max work per technician">
            <input
              type="number"
              min="1"
              value={edit.configuration?.max_capacity || 10}
              onChange={(e) => setConfig("max_capacity", +e.target.value)}
            />
          </Field>
          <Field label="Maximum waiting minutes">
            <input
              type="number"
              min="1"
              value={edit.configuration?.max_wait_minutes || 60}
              onChange={(e) => setConfig("max_wait_minutes", +e.target.value)}
            />
          </Field>
          <Field label="Fallback behavior">
            <select
              value={edit.configuration?.fallback_behavior || "triage"}
              onChange={(e) => setConfig("fallback_behavior", e.target.value)}
            >
              <option value="triage">Send to triage queue</option>
              <option value="overflow">Send to overflow queue</option>
              <option value="manual">Leave unassigned for manual review</option>
            </select>
          </Field>
          <Field label="Queue visibility">
            <select
              value={edit.configuration?.visibility || "team"}
              onChange={(e) => setConfig("visibility", e.target.value)}
            >
              <option value="team">Eligible teams</option>
              <option value="staff">All service staff</option>
              <option value="restricted">Managers only</option>
            </select>
          </Field>
          <Field label="Supported organizations / clients" wide>
            <input
              value={(edit.configuration?.organizations || []).join(", ")}
              onChange={(e) =>
                setConfig(
                  "organizations",
                  e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          <Field label="Supported request types" wide>
            <input
              value={(edit.configuration?.request_types || []).join(", ")}
              onChange={(e) =>
                setConfig(
                  "request_types",
                  e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          <Field label="Supported categories" wide>
            <input
              value={(edit.configuration?.categories || []).join(", ")}
              onChange={(e) =>
                setConfig(
                  "categories",
                  e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
          </Field>
          <Field label="Business hours calendar">
            <input
              value={edit.configuration?.business_hours_calendar || ""}
              onChange={(e) =>
                setConfig("business_hours_calendar", e.target.value)
              }
            />
          </Field>
          <Field label="Queue time zone">
            <input
              value={edit.configuration?.timezone || "America/New_York"}
              onChange={(e) => setConfig("timezone", e.target.value)}
            />
          </Field>
          <Field label="Overflow queue">
            <select
              value={edit.configuration?.overflow_queue_id || ""}
              onChange={(e) =>
                setConfig(
                  "overflow_queue_id",
                  e.target.value ? +e.target.value : null,
                )
              }
            >
              <option value="">No overflow queue</option>
              {(queues.data || [])
                .filter((x: any) => x.id !== edit.id)
                .map((x: any) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Escalation team">
            <select
              value={edit.configuration?.escalation_team_id || ""}
              onChange={(e) =>
                setConfig(
                  "escalation_team_id",
                  e.target.value ? +e.target.value : null,
                )
              }
            >
              <option value="">No escalation team</option>
              {(teams.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="SLA policy">
            <input
              value={edit.configuration?.sla_policy || ""}
              onChange={(e) => setConfig("sla_policy", e.target.value)}
            />
          </Field>
          <Field label="Notification policy">
            <input
              value={edit.configuration?.notification_policy || ""}
              onChange={(e) => setConfig("notification_policy", e.target.value)}
            />
          </Field>
          <Field label="Operational purpose" wide>
            <textarea
              value={edit.description || ""}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
          </Field>
          <Toggle
            label="Allow self-assignment"
            value={edit.configuration?.self_assignment !== false}
            onChange={(v) => setConfig("self_assignment", v)}
          />
          <Toggle
            label="Queue active"
            value={edit.active !== false}
            onChange={(v) => setEdit({ ...edit, active: v })}
          />
        </Modal>
      )}
      {simulation && (
        <Modal
          title="Queue assignment simulation"
          onClose={() => setSimulation(null)}
        >
          <div className="wide simulation">
            <h4>{simulation.queue.name}</h4>
            <p>Strategy: {simulation.assignment_strategy}</p>
            <strong>Eligible teams</strong>
            <ul>
              {simulation.eligible_teams.map((x: any) => (
                <li key={x.id}>{x.name}</li>
              ))}
            </ul>
            <strong>Eligible technicians</strong>
            <ul>
              {simulation.eligible_technicians.map((x: any) => (
                <li key={x.id}>
                  {x.name} · {x.active_work} active
                </li>
              ))}
            </ul>
            <strong>Excluded</strong>
            <ul>
              {simulation.excluded_technicians.map((x: any) => (
                <li key={x.id}>
                  {x.name}: {x.reason}
                </li>
              ))}
            </ul>
            <h4>
              Selected:{" "}
              {simulation.selected_technician?.name || "No eligible technician"}
            </h4>
          </div>
        </Modal>
      )}
    </Panel>
  );
}

function Routing() {
  const rules = useLoad("/admin/routing-rules"),
    queues = useLoad("/admin/queues"),
    teams = useLoad("/admin/teams"),
    events = useLoad("/admin/event-catalog");
  const [edit, setEdit] = useState<any>(null),
    [test, setTest] = useState<any>(null),
    [versions, setVersions] = useState<any>(null),
    [sample, setSample] = useState<any>({
      location_name: "United States",
      requester_email: "requester@medreceivables.com",
      requester_domain: "medreceivables.com",
      category: "Hardware",
      priority: "Medium",
      channel: "portal",
    }),
    [error, setError] = useState("");
  const empty = {
    name: "",
    description: "",
    trigger: "ticket.created",
    priority_order: 100,
    conditions: {
      logic: "AND",
      conditions: [{ field: "location_name", operator: "equals", value: "" }],
    },
    actions: {
      queue_id: null,
      team_id: null,
      assignment_strategy: "round_robin",
    },
    status: "draft",
    active: false,
    stop_processing: true,
    overwrite_existing: false,
    reevaluate_fields: [],
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(
        edit.id ? `/admin/routing-rules/${edit.id}` : "/admin/routing-rules",
        { method: edit.id ? "PATCH" : "POST", body: JSON.stringify(edit) },
      );
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  function conditions() {
    return edit.conditions?.conditions || [];
  }
  function changeCondition(i: number, k: string, v: any) {
    const next = [...conditions()];
    next[i] = { ...next[i], [k]: v };
    setEdit({ ...edit, conditions: { ...edit.conditions, conditions: next } });
  }
  async function duplicate() {
    try {
      await api(`/admin/routing-rules/${edit.id}/duplicate`, {
        method: "POST",
      });
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (!confirm(`Archive ${edit.name}?`)) return;
    try {
      await api(`/admin/routing-rules/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function history() {
    setVersions({
      rule: edit,
      items: await api(`/admin/routing-rules/${edit.id}/versions`),
    });
    setEdit(null);
  }
  return (
    <Panel
      title="Routing rule builder"
      text="Rules run in order; lower numbers run first. Test rules before activation and keep a fallback triage rule."
      action={
        <button className="primary" onClick={() => setEdit({ ...empty })}>
          Add routing rule
        </button>
      }
    >
      {error && <Notice>{error}</Notice>}
      <div className="routing-test">
        <div>
          <strong>Test all active rules</strong>
          <input
            value={sample.requester_email}
            onChange={(e) =>
              setSample({
                ...sample,
                requester_email: e.target.value,
                requester_domain: e.target.value.includes("@")
                  ? e.target.value.split("@").pop()?.toLowerCase()
                  : sample.requester_domain,
              })
            }
            placeholder="Requester email"
          />
          <input
            value={sample.location_name}
            onChange={(e) =>
              setSample({ ...sample, location_name: e.target.value })
            }
            placeholder="Requester location"
          />
          <input
            value={sample.category}
            onChange={(e) => setSample({ ...sample, category: e.target.value })}
            placeholder="Category"
          />
          <select
            value={sample.priority}
            onChange={(e) => setSample({ ...sample, priority: e.target.value })}
          >
            <option>Low</option>
            <option>Medium</option>
            <option>High</option>
            <option>Critical</option>
          </select>
        </div>
        <button
          onClick={async () =>
            setTest(
              await api("/admin/routing-rules/test", {
                method: "POST",
                body: JSON.stringify(sample),
              }),
            )
          }
        >
          Run simulation
        </button>
      </div>
      <div className="card-list">
        {(rules.data || []).map((x: any) => (
          <article key={x.id} onClick={() => setEdit({ ...x })}>
            <div className="record-icon">{x.priority_order}</div>
            <div>
              <h4>{x.name}</h4>
              <p>
                {x.description ||
                  `${x.trigger} · ${x.conditions?.conditions?.length || x.conditions?.length || 0} conditions`}
              </p>
              <small>
                {x.status} ·{" "}
                {x.stop_processing
                  ? "stops after match"
                  : "continues processing"}{" "}
                · {x.match_count} matches
              </small>
            </div>
            <Status active={x.active} />
            <button>Edit</button>
          </article>
        ))}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} routing rule`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <div className="record-actions">
                <button type="button" onClick={duplicate}>
                  Duplicate
                </button>
                <button type="button" onClick={history}>
                  Version history
                </button>
                <button type="button" className="danger" onClick={archive}>
                  Archive
                </button>
              </div>
            )
          }
        >
          <Field label="Name">
            <input
              required
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Field>
          <Field label="Execution order" help="Lower numbers run first.">
            <input
              type="number"
              value={edit.priority_order}
              onChange={(e) =>
                setEdit({ ...edit, priority_order: +e.target.value })
              }
            />
          </Field>
          <Field label="Trigger">
            <select
              value={edit.trigger}
              onChange={(e) => setEdit({ ...edit, trigger: e.target.value })}
            >
              {(events.data || []).map((x: any) => (
                <option key={x.key} value={x.key}>
                  {x.key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select
              value={edit.status}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  status: e.target.value,
                  active: e.target.value === "active",
                })
              }
            >
              <option value="draft">Draft</option>
              <option value="active">Active</option>
            </select>
          </Field>
          <Field label="Description" wide>
            <textarea
              value={edit.description || ""}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
          </Field>
          <div className="wide condition-builder">
            <header>
              <strong>Conditions</strong>
              <select
                value={edit.conditions?.logic || "AND"}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    conditions: { ...edit.conditions, logic: e.target.value },
                  })
                }
              >
                <option>AND</option>
                <option>OR</option>
              </select>
              <button
                type="button"
                onClick={() =>
                  setEdit({
                    ...edit,
                    conditions: {
                      ...edit.conditions,
                      conditions: [
                        ...conditions(),
                        { field: "category", operator: "equals", value: "" },
                      ],
                    },
                  })
                }
              >
                Add condition
              </button>
            </header>
            {conditions().map((c: any, i: number) => (
              <div key={i}>
                <select
                  value={c.field}
                  onChange={(e) => changeCondition(i, "field", e.target.value)}
                >
                  {[
                    "organization",
                    "requester",
                    "requester_email",
                    "requester_domain",
                    "requester_department",
                    "location_name",
                    "requester_group",
                    "vip",
                    "channel",
                    "request_type",
                    "category",
                    "subcategory",
                    "service",
                    "asset_type",
                    "priority",
                    "impact",
                    "urgency",
                    "keywords",
                    "business_hours",
                    "telephone_number",
                    "call_queue",
                  ].map((x) => (
                    <option key={x} value={x}>
                      {x.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
                <select
                  value={c.operator || "equals"}
                  onChange={(e) =>
                    changeCondition(i, "operator", e.target.value)
                  }
                >
                  {[
                    "equals",
                    "does_not_equal",
                    "contains",
                    "does_not_contain",
                    "starts_with",
                    "ends_with",
                    "is_empty",
                    "is_not_empty",
                    "in",
                    "not_in",
                    "greater_than",
                    "less_than",
                    "matches",
                  ].map((x) => (
                    <option key={x} value={x}>
                      {x.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
                <input
                  value={c.value ?? ""}
                  onChange={(e) => changeCondition(i, "value", e.target.value)}
                />
                <button
                  type="button"
                  onClick={() =>
                    setEdit({
                      ...edit,
                      conditions: {
                        ...edit.conditions,
                        conditions: conditions().filter(
                          (_: any, n: number) => n !== i,
                        ),
                      },
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <Field label="Assign queue">
            <select
              value={edit.actions?.queue_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  actions: {
                    ...edit.actions,
                    queue_id: e.target.value ? +e.target.value : null,
                  },
                })
              }
            >
              <option value="">Do not change queue</option>
              {(queues.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assign team">
            <select
              value={edit.actions?.team_id || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  actions: {
                    ...edit.actions,
                    team_id: e.target.value ? +e.target.value : null,
                  },
                })
              }
            >
              <option value="">Use queue eligibility</option>
              {(teams.data || []).map((x: any) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assignment strategy">
            <select
              value={edit.actions?.assignment_strategy || "round_robin"}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  actions: {
                    ...edit.actions,
                    assignment_strategy: e.target.value,
                  },
                })
              }
            >
              {[
                "round_robin",
                "least_active",
                "lowest_workload",
                "skills_based",
                "manual",
              ].map((x) => (
                <option key={x} value={x}>
                  {x.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </Field>
          <div className="wide record-actions">
            <button
              type="button"
              onClick={async () =>
                setTest(
                  await api("/admin/routing-rules/evaluate", {
                    method: "POST",
                    body: JSON.stringify({ rule: edit, sample }),
                  }),
                )
              }
            >
              Test this rule with sample above
            </button>
          </div>
          <Toggle
            label="Stop after this rule matches"
            value={edit.stop_processing !== false}
            onChange={(v) => setEdit({ ...edit, stop_processing: v })}
          />
          <Toggle
            label="May overwrite existing assignment"
            value={!!edit.overwrite_existing}
            onChange={(v) => setEdit({ ...edit, overwrite_existing: v })}
          />
        </Modal>
      )}
      {versions && (
        <Modal
          title={`Version history: ${versions.rule.name}`}
          onClose={() => setVersions(null)}
        >
          <div className="wide log-list">
            {versions.items.map((v: any) => (
              <article key={v.id}>
                <div>
                  <strong>Version {v.version}</strong>
                  <small>{new Date(v.created_at).toLocaleString()}</small>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    if (confirm(`Restore version ${v.version}?`)) {
                      await api(
                        `/admin/routing-rules/${versions.rule.id}/rollback/${v.id}`,
                        { method: "POST" },
                      );
                      setVersions(null);
                      rules.load();
                    }
                  }}
                >
                  Restore
                </button>
              </article>
            ))}
          </div>
        </Modal>
      )}
      {test && (
        <Modal title="Routing simulation trace" onClose={() => setTest(null)}>
          <div className="wide simulation">
            <h4>
              {test.matched
                ? "A routing rule matched"
                : "No active rule matched"}
            </h4>
            {test.trace.map((x: any) => (
              <article key={x.rule_id}>
                <strong>
                  {x.rule}: {x.matched ? "MATCHED" : "SKIPPED"}
                </strong>
                <ul>
                  {x.conditions.map((line: string) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </article>
            ))}
            {test.queue_simulation && (
              <h4>
                Selected queue: {test.queue_simulation.queue.name} →{" "}
                {test.queue_simulation.selected_technician?.name ||
                  "No technician eligible"}
              </h4>
            )}
          </div>
        </Modal>
      )}
    </Panel>
  );
}

function AutomationCenter() {
  const resource = useLoad("/admin/automation-center");
  const [policies, setPolicies] = useState<any>({});
  const [message, setMessage] = useState("");
  useEffect(() => { if (resource.data?.policies) setPolicies(resource.data.policies); }, [resource.data]);
  const cards: any[] = [
    ["duplicate_detection", "Duplicate ticket detection", "Finds likely matching requests and suggests a linked record. It never merges tickets automatically."],
    ["priority_escalation", "Auto-priority escalation", "Flags aging urgent work and follows your selected notification path."],
    ["after_hours_alerts", "After-hours alerts", "Notifies the on-call path for tickets created outside your operating hours."],
    ["unresponsive_tech", "Unresponsive technician alerts", "Sends a reminder or escalation when assigned work has no technician activity."],
    ["scheduled_maintenance", "Scheduled maintenance notes", "Adds approved maintenance notices and keeps requesters informed."],
    ["knowledge_base_linking", "Knowledge base suggestions", "Suggests approved troubleshooting articles without changing the ticket."],
    ["license_software_expiry", "License and software expiry tracking", "Creates advance visibility for eligible software and license records."],
    ["satisfaction_surveys", "Satisfaction surveys", "Sends a configurable post-resolution survey after the selected delay."],
    ["chat_auto_archive", "Chat auto-archive", "Archives inactive live conversations while preserving their ticket history."],
    ["password_expiry", "Password expiry management", "Stages 15-day reminders, 5-day login notices, the 3-day self-service choice, and IT fallback. Requires an identity source before use."],
    ["announcements", "Announcement delivery", "Keeps announcements visible in the portal and controls optional endpoint-agent popups."],
  ];
  function update(key:string, patch:any) { setPolicies((current:any) => ({...current, [key]: {...(current[key] || {}), ...patch}})); }
  async function save() {
    try { const result=await api("/admin/automation-center",{method:"PATCH",body:JSON.stringify({policies})}); setPolicies(result.policies); setMessage("Automation settings saved. Only the policies you enabled can run."); resource.load(); }
    catch(e:any){ setMessage(e.message); }
  }
  async function test(key:string) {
    try { const result=await api(`/admin/automation-center/${key}/test`,{method:"POST"}); setMessage(result.message); }
    catch(e:any){ setMessage(e.message); }
  }
  return <Panel title="Automation Center" text="Each policy is independent, disabled by default, and auditable. Test controls never change a ticket, account, device, or message.">
    {message&&<Notice type={message.includes("saved")||message.includes("completed")?"success":"error"}>{message}</Notice>}
    <div className="notification-automation-guide"><strong>Safe rollout</strong><span>1. Configure</span><span>2. Test</span><span>3. Enable</span><small>Start with one policy at a time. Password expiry will remain staged until a supported identity source is configured.</small></div>
    <div className="card-list automation-policy-list">{cards.map(([key,title,text])=>{const policy=policies[key]||{};return <article key={key}>
      <div className="record-icon">⚙</div><div><h4>{title}</h4><p>{text}</p><small>{policy.enabled?"Enabled":"Disabled"}</small></div>
      <Toggle label="" value={!!policy.enabled} onChange={(enabled)=>update(key,{enabled})}/>
      <button type="button" onClick={()=>test(key)}>Test</button>
    </article>})}</div>
    <div className="record-actions"><button className="primary" onClick={save}>Save automation settings</button></div>
  </Panel>
}

function AnnouncementsAdmin() {
  const resource=useLoad("/admin/announcements");
  const [edit,setEdit]=useState<any>(null),[message,setMessage]=useState("");
  const empty={title:"",body:"",severity:"info",active:true};
  async function save(e:FormEvent){e.preventDefault();try{await api(edit.id?`/admin/announcements/${edit.id}`:"/admin/announcements",{method:edit.id?"PATCH":"POST",body:JSON.stringify(edit)});setEdit(null);setMessage("Announcement saved.");resource.load()}catch(error:any){setMessage(error.message)}}
  return <Panel title="Service announcements" text="Active announcements appear on the portal. Endpoint-agent popups are controlled in Automation Center and remain off until you enable them." action={<button className="primary" onClick={()=>setEdit({...empty})}>New announcement</button>}>
    {message&&<Notice type={message.includes("saved")?"success":"error"}>{message}</Notice>}
    <div className="card-list">{(resource.data||[]).map((item:any)=><article key={item.id} onClick={()=>setEdit({...item})}><div className="record-icon">{item.severity==="critical"?"!":"i"}</div><div><h4>{item.title}</h4><p>{item.body}</p><small>{item.severity} · {item.active?"Active":"Draft"}</small></div><Status active={item.active}/><button>Edit</button></article>)}</div>
    {edit&&<Modal title={`${edit.id?"Edit":"Create"} announcement`} onClose={()=>setEdit(null)} onSave={save}>
      <Field label="Title" wide><input required value={edit.title} onChange={e=>setEdit({...edit,title:e.target.value})}/></Field>
      <Field label="Message" wide><textarea required rows={6} value={edit.body} onChange={e=>setEdit({...edit,body:e.target.value})}/></Field>
      <Field label="Severity"><select value={edit.severity} onChange={e=>setEdit({...edit,severity:e.target.value})}><option value="info">Information</option><option value="warning">Warning</option><option value="critical">Critical</option></select></Field>
      <Toggle label="Publish this announcement" value={!!edit.active} onChange={active=>setEdit({...edit,active})}/>
    </Modal>}
  </Panel>
}

function Notifications() {
  const rules = useLoad("/admin/notification-rules"),
    events = useLoad("/admin/event-catalog"),
    controls = useLoad("/admin/notification-settings");
  const [edit, setEdit] = useState<any>(null),
    [error, setError] = useState("");
  const empty = {
    name: "",
    trigger: "ticket.created",
    classification: "customer",
    conditions: [],
    recipients: [{ type: "requester", channel: "to" }],
    template: {
      subject: "[{{ticket.number}}] {{ticket.subject}}",
      text_body: "Hello {{requester.first_name}},\n\n",
      html_body: "",
    },
    locale: "en",
    status: "draft",
    rate_limit: {},
    suppress_actor: true,
    active: false,
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      await api(
        edit.id
          ? `/admin/notification-rules/${edit.id}`
          : "/admin/notification-rules",
        { method: edit.id ? "PATCH" : "POST", body: JSON.stringify(edit) },
      );
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function seed() {
    const result = await api("/admin/notification-rules/seed-defaults", {
      method: "POST",
    });
    setError(
      result.created
        ? `${result.created} professional templates created.`
        : "All default templates already exist.",
    );
    rules.load();
  }
  async function duplicate() {
    try {
      await api(`/admin/notification-rules/${edit.id}/duplicate`, {
        method: "POST",
      });
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function archive() {
    if (!confirm(`Archive ${edit.name}?`)) return;
    try {
      await api(`/admin/notification-rules/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      rules.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  function updateRecipient(i: number, key: string, value: string) {
    const next = [...(edit.recipients || [])];
    next[i] = { ...next[i], [key]: value };
    setEdit({ ...edit, recipients: next });
  }
  async function setDelivery(enabled: boolean) {
    if (!enabled && !confirm("Disable every in-app and email notification? Any email waiting to send will be suppressed.")) return;
    try {
      const result=await api("/admin/notification-settings",{method:"PATCH",body:JSON.stringify({enabled})});
      setError(enabled ? "All notifications are enabled." : `All notifications are disabled. ${result.queued_emails_suppressed || 0} queued email(s) were suppressed.`);
      controls.load();
    } catch (e:any) { setError(e.message); }
  }
  async function setEmailDelivery(email_enabled: boolean) {
    if (!email_enabled && !confirm("Disable outbound email? In-app notifications and inbound email-to-ticket processing will remain active.")) return;
    try {
      const result=await api("/admin/notification-settings",{method:"PATCH",body:JSON.stringify({email_enabled})});
      setError(email_enabled ? "Outbound email is enabled." : `Testing mode is active. Outbound email is disabled and ${result.queued_emails_suppressed || 0} queued email(s) were suppressed.`);
      controls.load();
    } catch (e:any) { setError(e.message); }
  }
  return (
    <Panel
      title="Notifications and event catalog"
      text="Events are immutable reporting signals. Notification rules turn selected events into customer or internal messages."
      action={
        <div>
          <button onClick={seed}>Install default templates</button>
          <button className="primary" onClick={() => setEdit({ ...empty })}>
            Custom notification
          </button>
        </div>
      }
    >
      {error && (
        <Notice
          type={
            error.includes("created") || error.includes("exist") || error.includes("notifications are")
              ? "success"
              : "error"
          }
        >
          {error}
        </Notice>
      )}
      <div className="notification-master-control">
        <div>
          <strong>Global notification delivery</strong>
          <p>{controls.data?.enabled === false ? "Disabled — Northstar records suppressed events in the audit log but sends nothing." : "Enabled — standard ticket recipients and published notification rules are active."}</p>
        </div>
        <button className={controls.data?.enabled === false ? "primary" : "danger"} onClick={()=>setDelivery(controls.data?.enabled === false)}>
          {controls.data?.enabled === false ? "Enable all notifications" : "Disable all notifications"}
        </button>
      </div>
      <div className="notification-master-control">
        <div>
          <strong>Outbound email</strong>
          <p>{controls.data?.email_enabled === false ? "Testing mode — no requester, technician, approver, or other user will receive email. In-app notifications and inbound email intake remain active." : "Live — Northstar may send email generated by ticket and approval events."}</p>
        </div>
        <button className={controls.data?.email_enabled === false ? "primary" : "danger"} onClick={()=>setEmailDelivery(controls.data?.email_enabled === false)}>
          {controls.data?.email_enabled === false ? "Enable outbound email" : "Disable outbound email"}
        </button>
      </div>
      <div className="notification-automation-guide">
        <strong>Standard recipients are automatic</strong>
        <span>Request received → requester</span><span>Ticket assigned → assigned technician</span><span>Public reply → other party</span><span>Approval requested → approver</span><span>Resolved or closed → requester</span>
        <small>Rules below customize the message or add recipients; they do not replace the standard recipient.</small>
      </div>
      <div className="event-strip">
        <strong>{(events.data || []).length} reportable events</strong>
        <span>
          {(events.data || [])
            .slice(0, 8)
            .map((x: any) => x.key)
            .join(" · ")}
        </span>
      </div>
      <div className="card-list">
        {(rules.data || []).map((x: any) => (
          <article key={x.id} onClick={() => setEdit({ ...x })}>
            <div className="record-icon">@</div>
            <div>
              <h4>{x.name}</h4>
              <p>{x.template?.subject}</p>
              <small>
                {x.trigger} · {x.classification} · {x.locale}
              </small>
            </div>
            <Status active={x.active} />
            <button>Edit</button>
          </article>
        ))}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Edit" : "Create"} notification`}
          onClose={() => setEdit(null)}
          onSave={save}
          danger={
            edit.id && (
              <div className="record-actions">
                <button type="button" onClick={duplicate}>
                  Duplicate
                </button>
                <button type="button" className="danger" onClick={archive}>
                  Archive
                </button>
              </div>
            )
          }
        >
          <Field label="Name">
            <input
              required
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Field>
          <Field label="Event trigger">
            <select
              value={edit.trigger}
              onChange={(e) => setEdit({ ...edit, trigger: e.target.value })}
            >
              {(events.data || []).map((x: any) => (
                <option key={x.key} value={x.key}>
                  {x.key}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Audience">
            <select
              value={edit.classification}
              onChange={(e) =>
                setEdit({ ...edit, classification: e.target.value })
              }
            >
              <option value="customer">Customer notification</option>
              <option value="internal">Internal notification</option>
            </select>
          </Field>
          <div className="wide condition-builder">
            <header>
              <strong>Recipients</strong>
              <button
                type="button"
                onClick={() =>
                  setEdit({
                    ...edit,
                    recipients: [
                      ...(edit.recipients || []),
                      { type: "requester", channel: "to" },
                    ],
                  })
                }
              >
                Add recipient
              </button>
            </header>
            {(edit.recipients || []).map((r: any, i: number) => (
              <div key={i}>
                <select
                  value={r.type || "requester"}
                  onChange={(e) => updateRecipient(i, "type", e.target.value)}
                >
                  {[
                    "requester",
                    "opener",
                    "assignee",
                    "team_lead",
                    "queue_manager",
                    "approver",
                    "manager",
                    "group",
                    "explicit_address",
                    "custom_field",
                  ].map((x) => (
                    <option key={x} value={x}>
                      {x.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
                <select
                  value={r.channel || "to"}
                  onChange={(e) =>
                    updateRecipient(i, "channel", e.target.value)
                  }
                >
                  <option value="to">To</option>
                  <option value="cc">CC</option>
                  <option value="bcc">BCC</option>
                </select>
                <input
                  value={r.value || ""}
                  onChange={(e) => updateRecipient(i, "value", e.target.value)}
                  placeholder="Group, address, or field when required"
                />
                <button
                  type="button"
                  onClick={() =>
                    setEdit({
                      ...edit,
                      recipients: edit.recipients.filter(
                        (_: any, n: number) => n !== i,
                      ),
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <Field label="Locale">
            <input
              value={edit.locale || "en"}
              onChange={(e) => setEdit({ ...edit, locale: e.target.value })}
            />
          </Field>
          <Field label="Rate limit per ticket / hour">
            <input
              type="number"
              min="0"
              value={edit.rate_limit?.per_ticket_per_hour || 0}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  rate_limit: {
                    ...edit.rate_limit,
                    per_ticket_per_hour: +e.target.value,
                  },
                })
              }
            />
          </Field>
          <Field label="Deduplication window (minutes)">
            <input
              type="number"
              min="0"
              value={edit.rate_limit?.dedupe_minutes || 0}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  rate_limit: {
                    ...edit.rate_limit,
                    dedupe_minutes: +e.target.value,
                  },
                })
              }
            />
          </Field>
          <Field label="Subject" wide>
            <input
              required
              value={edit.template?.subject || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  template: { ...edit.template, subject: e.target.value },
                })
              }
            />
          </Field>
          <Field
            label="Plain-text body"
            wide
            help="Variables: {{ticket.number}}, {{ticket.subject}}, {{requester.first_name}}, {{assignee.name}}, {{ticket.url}}"
          >
            <textarea
              rows={12}
              value={edit.template?.text_body || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  template: { ...edit.template, text_body: e.target.value },
                })
              }
            />
          </Field>
          <Field
            label="HTML body"
            wide
            help="Unsafe scripts, frames, objects, and javascript URLs are rejected."
          >
            <textarea
              rows={8}
              value={edit.template?.html_body || ""}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  template: { ...edit.template, html_body: e.target.value },
                })
              }
            />
          </Field>
          <Toggle
            label="Suppress notifications caused by the recipient's own action"
            value={edit.suppress_actor !== false}
            onChange={(v) => setEdit({ ...edit, suppress_actor: v })}
          />
          <Toggle
            label="Published and active"
            value={edit.status === "active" && edit.active}
            onChange={(v) =>
              setEdit({ ...edit, status: v ? "active" : "draft", active: v })
            }
          />
          <div className="wide template-preview">
            <strong>Preview</strong>
            <h4>
              {edit.template?.subject
                ?.replace("{{ticket.number}}", "INC-000123")
                .replace("{{ticket.subject}}", "Laptop cannot connect")}
            </h4>
            <pre>{edit.template?.text_body}</pre>
          </div>
        </Modal>
      )}
    </Panel>
  );
}

function Integrations({ kind }: { kind: string }) {
  const resource = useLoad(`/admin/integrations?kind=${kind}`);
  const readiness = useLoad("/admin/integrations/connect/readiness");
  const [edit, setEdit] = useState<any>(null),
    [logs, setLogs] = useState<any>(null),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [registration, setRegistration] = useState({
      client_id: "",
      client_secret: "",
      environment: "production",
    });
  const providers =
    kind === "directory"
      ? ["Microsoft Entra ID", "Active Directory / LDAP", "SCIM 2.0"]
      : kind === "email"
        ? ["Microsoft 365", "Google Workspace", "Generic SMTP / IMAP"]
        : [
            "RingCentral",
            "Microsoft Teams Phone",
            "Zoom Phone",
            "8x8",
            "Cisco Webex Calling",
            "Five9",
            "Genesys Cloud",
            "Twilio",
            "Other / Custom Provider",
          ];
  function blank() {
    const provider = providers[0];
    return {
      name: provider,
      kind,
      provider,
      enabled: false,
      configuration: {
        sync_scope: "all_users",
        sync_schedule: "daily",
        deactivation_policy: "disable",
        polling_interval: "5 minutes",
        attachment_limit_mb: 25,
        ticket_creation_policy: "answered_or_destination",
        caller_match: "phone_number",
        retention_days: 90,
      },
      secrets: {},
      clear_secrets: [],
    };
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (guidedProviders.includes(edit.provider)) {
        const result = await api("/admin/integrations/connect/start", {
          method: "POST",
          body: JSON.stringify({
            name: edit.name,
            kind,
            provider: edit.provider,
            configuration: edit.configuration,
          }),
        });
        if (!result.ready) {
          setMessage(result.message);
          return;
        }
        location.assign(result.authorization_url);
        return;
      }
      await api(
        edit.id ? `/admin/integrations/${edit.id}` : "/admin/integrations",
        { method: edit.id ? "PATCH" : "POST", body: JSON.stringify(edit) },
      );
      setEdit(null);
      resource.load();
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function saveRegistration() {
    const provider = edit.provider.startsWith("Microsoft")
      ? "microsoft"
      : "ringcentral";
    setBusy(true);
    setMessage("");
    try {
      const result = await api(
        `/admin/integrations/connect/registration/${provider}`,
        { method: "PUT", body: JSON.stringify(registration) },
      );
      if (!result.ready)
        throw new Error("Both application values are required.");
      setRegistration({ ...registration, client_secret: "" });
      setMessage(
        `${provider === "microsoft" ? "Microsoft" : "RingCentral"} application registration saved securely. You can now continue to provider sign-in.`,
      );
      readiness.load();
    } catch (e: any) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function archive() {
    if (
      !edit.id ||
      !confirm(
        `Archive ${edit.name}? Stored credentials will remain inaccessible and the connection will be disabled.`,
      )
    )
      return;
    try {
      await api(`/admin/integrations/${edit.id}`, { method: "DELETE" });
      setEdit(null);
      resource.load();
    } catch (e: any) {
      setMessage(e.message);
    }
  }
  async function test(x: any) {
    const result = await api(`/admin/integrations/${x.id}/test`, {
      method: "POST",
    });
    setMessage(result.last_error);
    resource.load();
  }
  return (
    <Panel
      title={
        kind === "directory"
          ? "Identity and provisioning connections"
          : kind === "email"
            ? "Inbound and outbound email connections"
            : "Phone and call-event connections"
      }
      text="Connect through the provider's secure sign-in page. Tenant IDs, account IDs, passwords, secrets, and webhook URLs are discovered or managed automatically."
      action={
        <button className="primary" onClick={() => setEdit(blank())}>
          Add connection
        </button>
      }
    >
      {message && (
        <Notice type={message.includes("complete") ? "success" : "error"}>
          {message}
        </Notice>
      )}
      {readiness.data &&
        ((kind === "telephony" && !readiness.data.ringcentral?.ready) ||
          (kind !== "telephony" && !readiness.data.microsoft?.ready)) && (
          <Notice>
            Provider application setup is not complete. Click Add connection,
            then enter the one-time server application ID and credential shown
            in the Provider application setup section.
          </Notice>
        )}
      <div className="card-list">
        {(resource.data || []).map((x: any) => (
          <article key={x.id}>
            <div className="record-icon">
              {kind === "email" ? "@" : kind === "telephony" ? "☎" : "ID"}
            </div>
            <div
              onClick={() => setEdit({ ...x, secrets: {}, clear_secrets: [] })}
            >
              <h4>{x.name}</h4>
              <p>{x.provider}</p>
              <small>
                {x.last_error || `${x.status} · Provider authorization`}
              </small>
            </div>
            <Status
              active={
                x.status === "Connected" ||
                x.status === "Ready for provider test"
              }
              label={x.status}
            />
            <button onClick={() => test(x)}>Test</button>
            <button
              onClick={async () =>
                setLogs(await api(`/admin/integrations/${x.id}/logs`))
              }
            >
              Activity
            </button>
            <button
              onClick={() => setEdit({ ...x, secrets: {}, clear_secrets: [] })}
            >
              Manage
            </button>
          </article>
        ))}
      </div>
      {edit && (
        <Modal
          title={`${edit.id ? "Manage" : "Connect"} ${edit.provider}`}
          onClose={() => setEdit(null)}
          onSave={save}
          busy={busy}
          danger={
            edit.id && (
              <button type="button" className="danger" onClick={archive}>
                Disconnect and archive
              </button>
            )
          }
        >
          <Field label="Connection name">
            <input
              required
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
          </Field>
          <Field label="Provider">
            <select
              value={edit.provider}
              onChange={(e) =>
                setEdit({
                  ...edit,
                  provider: e.target.value,
                  name: e.target.value,
                  configuration: {},
                  secrets: {},
                })
              }
            >
              {providers.map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          {guidedProviders.includes(edit.provider) && (
            <div className="wide guided-connect">
              <div className="guided-provider-mark">
                {edit.provider.startsWith("Microsoft") ? "M" : "RC"}
              </div>
              <div>
                <strong>
                  {edit.provider.startsWith("Microsoft")
                    ? "Continue securely with Microsoft"
                    : "Continue securely with RingCentral"}
                </strong>
                <p>
                  Sign in on the provider's website, complete MFA, review the
                  requested access, and return automatically. Northstar never
                  receives your password.
                </p>
                <small
                  className={
                    readiness.data?.[
                      edit.provider.startsWith("Microsoft")
                        ? "microsoft"
                        : "ringcentral"
                    ]?.ready
                      ? "ready"
                      : "setup"
                  }
                >
                  {readiness.data?.[
                    edit.provider.startsWith("Microsoft")
                      ? "microsoft"
                      : "ringcentral"
                  ]?.message || "Checking provider readiness…"}
                </small>
              </div>
            </div>
          )}
          {edit.provider === "Microsoft 365" && (
            <div className="wide provider-status">
              <strong>Required Microsoft Graph application permissions</strong>
              <p>Add <b>Mail.ReadWrite</b> and <b>Mail.Send</b> as Application permissions in Microsoft Entra, grant administrator consent, then reconnect this mailbox. Northstar uses them only for the configured support mailbox.</p>
            </div>
          )}
          {edit.provider === "RingCentral" && (
            <div className="wide provider-status">
              <strong>Required RingCentral application scopes</strong>
              <p>Enable <b>ReadAccounts</b>, <b>WebSocketsSubscription</b>, and <b>CallControl</b>. Northstar keeps an outbound event connection open, so an internal server does not require a public webhook URL.</p>
            </div>
          )}
          {guidedProviders.includes(edit.provider) && readiness.data && (
            <div className="wide provider-registration">
              <header>
                <div>
                  <strong>Provider application setup</strong>
                  <p>
                    Server-owner setup only. Status:{" "}
                    {readiness.data[
                      edit.provider.startsWith("Microsoft")
                        ? "microsoft"
                        : "ringcentral"
                    ].ready
                      ? "configured and ready"
                      : "configuration required"}
                    . Customer administrators will not see or enter these
                    application credentials.
                  </p>
                </div>
                <a
                  href={
                    readiness.data[
                      edit.provider.startsWith("Microsoft")
                        ? "microsoft"
                        : "ringcentral"
                    ].registration_url
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  Open provider registration ↗
                </a>
              </header>
              <label>
                <b>Callback / redirect URL</b>
                <input
                  readOnly
                  value={
                    readiness.data[
                      edit.provider.startsWith("Microsoft")
                        ? "microsoft"
                        : "ringcentral"
                    ].callback_url
                  }
                />
                <small>
                  Copy this exact address into the provider application.
                </small>
                {edit.provider.startsWith("Microsoft") && (
                  <small>
                    This same URL securely handles administrator consent and user sign-in. In Microsoft Entra, set Supported account types to <strong>Accounts in any organizational directory</strong> so approved client tenants can use their company accounts.
                  </small>
                )}
              </label>
              <label>
                <b>Application client ID</b>
                <input
                  autoComplete="off"
                  value={registration.client_id}
                  onChange={(e) =>
                    setRegistration({
                      ...registration,
                      client_id: e.target.value,
                    })
                  }
                  placeholder="Paste the provider application client ID"
                />
                {readiness.data[
                  edit.provider.startsWith("Microsoft")
                    ? "microsoft"
                    : "ringcentral"
                ].client_id_configured && (
                  <small>
                    An application ID is stored. Enter both fields only to
                    replace the registration.
                  </small>
                )}
              </label>
              <label>
                <b>Application credential</b>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={registration.client_secret}
                  onChange={(e) =>
                    setRegistration({
                      ...registration,
                      client_secret: e.target.value,
                    })
                  }
                  placeholder="Paste the new client secret value"
                />
                {readiness.data[
                  edit.provider.startsWith("Microsoft")
                    ? "microsoft"
                    : "ringcentral"
                ].credential_configured && (
                  <small>An encrypted credential is already stored.</small>
                )}
              </label>
              {edit.provider === "RingCentral" && (
                <label>
                  <b>Environment</b>
                  <select
                    value={registration.environment}
                    onChange={(e) =>
                      setRegistration({
                        ...registration,
                        environment: e.target.value,
                      })
                    }
                  >
                    <option value="production">Production</option>
                    <option value="sandbox">Sandbox</option>
                  </select>
                </label>
              )}
              <button
                type="button"
                className="primary"
                disabled={
                  busy ||
                  !registration.client_id.trim() ||
                  !registration.client_secret
                }
                onClick={saveRegistration}
              >
                Save application registration
              </button>
            </div>
          )}
          {(
            providerFields[edit.provider] || ["base_url", "account_identifier"]
          ).map((key: string) => (
            <Field
              key={key}
              label={key === "call_queue_ids" ? "Help desk queue, extension, or phone number" : key.replaceAll("_", " ")}
              help={key === "call_queue_ids" ? "Comma-separated RingCentral queue IDs, extension numbers, or support phone numbers. Calls to other destinations are ignored." : key === "ticket_creation_policy" ? "Northstar monitors call events but creates tickets only when this rule matches." : undefined}
              wide={[
                "attribute_mappings",
                "did_queue_mappings",
                "extension_mappings",
              ].includes(key)}
            >
              {key === "ticket_creation_policy" ? <select
                value={edit.configuration?.[key] || "answered_or_destination"}
                onChange={(e) => setEdit({...edit,configuration:{...edit.configuration,[key]:e.target.value}})}
              ><option value="answered_or_destination">Technician answers OR call reaches a configured help desk destination</option><option value="answered_technician">Only when a mapped technician answers</option><option value="configured_destination">Only when the call reaches a configured help desk destination</option></select> : key === "caller_match" ? <select
                value={edit.configuration?.[key] || "phone_number"}
                onChange={(e) => setEdit({...edit,configuration:{...edit.configuration,[key]:e.target.value}})}
              ><option value="phone_number">Match requester by phone number</option><option value="always_new">Always create an unidentified caller</option></select> : <input
                value={
                  Array.isArray(edit.configuration?.[key])
                    ? edit.configuration[key].join(", ")
                    : typeof edit.configuration?.[key] === "object"
                      ? JSON.stringify(edit.configuration[key])
                      : edit.configuration?.[key] || ""
                }
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    configuration: {
                      ...edit.configuration,
                      [key]: e.target.value,
                    },
                  })
                }
                placeholder={`Enter ${key.replaceAll("_", " ")}`}
                autoComplete="off"
              />}
            </Field>
          ))}
          {(providerSecrets[edit.provider] ?? ["api_secret"]).map(
            (key: string) => (
              <Field
                key={key}
                label={key.replaceAll("_", " ")}
                help={
                  edit.secret_status?.[key]
                    ? "A credential is stored. Leave blank to keep it."
                    : "Credential is required and will be encrypted."
                }
              >
                <input
                  type="password"
                  autoComplete="new-password"
                  value={edit.secrets?.[key] || ""}
                  onChange={(e) =>
                    setEdit({
                      ...edit,
                      secrets: { ...edit.secrets, [key]: e.target.value },
                    })
                  }
                  placeholder={
                    edit.secret_status?.[key]
                      ? "Stored securely"
                      : "Enter secure credential"
                  }
                />
              </Field>
            ),
          )}
          {!guidedProviders.includes(edit.provider) && (
            <Toggle
              label="Enable connection"
              value={!!edit.enabled}
              onChange={(v) => setEdit({ ...edit, enabled: v })}
            />
          )}
          {!guidedProviders.includes(edit.provider) && (
            <div className="wide provider-status">
              <strong>Capability status</strong>
              <p>
                Saving stores configuration securely. “Validate settings” checks
                required fields and credentials. Live synchronization,
                inbound/outbound mail tests, webhook registration, and call
                processing become available only through an installed provider
                adapter with valid credentials.
              </p>
            </div>
          )}
          {!guidedProviders.includes(edit.provider) && (
            <div className="wide provider-guidance">
              <strong>Setup workflow</strong>
              <ol>
                <li>Complete all provider fields.</li>
                <li>Save secure credentials.</li>
                <li>Run Test to validate configuration.</li>
                <li>
                  Review required provider consent, webhook, and network
                  prerequisites.
                </li>
                <li>
                  Enable synchronization or event processing only after a
                  successful live provider test.
                </li>
              </ol>
            </div>
          )}
          {guidedProviders.includes(edit.provider) && (
            <div className="wide consent-summary">
              <strong>What happens next</strong>
              <ol>
                <li>Provider sign-in and MFA</li>
                <li>Administrator reviews the requested permissions</li>
                <li>Tenant or account is identified automatically</li>
                <li>Northstar validates and records the connection</li>
              </ol>
            </div>
          )}
        </Modal>
      )}
      {logs && (
        <Modal title="Connection logs" onClose={() => setLogs(null)}>
          <div className="wide log-list">
            {logs.length ? (
              logs.map((x: any) => (
                <article key={x.id}>
                  <Status active={x.level === "success"} label={x.level} />
                  <div>
                    <strong>{x.event}</strong>
                    <p>{x.details?.message || JSON.stringify(x.details)}</p>
                    <small>{new Date(x.created_at).toLocaleString()}</small>
                  </div>
                </article>
              ))
            ) : (
              <p>No connection activity recorded.</p>
            )}
          </div>
        </Modal>
      )}
    </Panel>
  );
}

function HelpDeskSettings() {
  const resource = useLoad("/admin/settings/help_desk"),
    [draft, setDraft] = useState<any>(null),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    if (resource.data?.[0])
      setDraft(JSON.parse(JSON.stringify(resource.data[0])));
  }, [resource.data]);
  if (resource.loading)
    return <div className="loading">Loading Help Desk Settings…</div>;
  if (!draft)
    return (
      <Notice>
        {resource.error || "Help Desk Settings have not been installed."}
      </Notice>
    );
  const value = draft.value || {};
  const change = (key: string, next: any) =>
    setDraft({ ...draft, value: { ...value, [key]: next } });
  async function save() {
    setError("");
    try {
      await api(`/admin/settings/${draft.id}`, {
        method: "PATCH",
        body: JSON.stringify({ value: draft.value }),
      });
      setMessage("Help Desk Settings saved and added to the audit log.");
      resource.load();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Panel
      title="Help Desk Settings"
      text="Safe operational defaults for staff workflow, customer access, ticket behavior, security, and attachments."
      action={null}
    >
      {message && <Notice type="success">{message}</Notice>}
      {error && <Notice>{error}</Notice>}
      <div className="helpdesk-settings-grid">
        <Field label="Help desk title">
          <input
            value={value.help_desk_title || ""}
            onChange={(e) => change("help_desk_title", e.target.value)}
          />
        </Field>
        <Field label="Tickets per page">
          <input
            type="number"
            min="10"
            max="250"
            value={value.tickets_per_page || 50}
            onChange={(e) => change("tickets_per_page", +e.target.value)}
          />
        </Field>
        <Field
          label="Automatic reload (seconds)"
          help="Set to zero to disable automatic reload."
        >
          <input
            type="number"
            min="0"
            value={value.auto_reload_seconds || 0}
            onChange={(e) => change("auto_reload_seconds", +e.target.value)}
          />
        </Field>
        <Field
          label="Autoclose inactive tickets (days)"
          help="Set to zero to require manual closure."
        >
          <input
            type="number"
            min="0"
            value={value.autoclose_days || 0}
            onChange={(e) => change("autoclose_days", +e.target.value)}
          />
        </Field>
        <Field label="Staff reply form">
          <select
            value={value.reply_form_position || "bottom"}
            onChange={(e) => change("reply_form_position", e.target.value)}
          >
            <option value="top">Top of ticket</option>
            <option value="bottom">Bottom of ticket</option>
          </select>
        </Field>
        <Field label="Ticket conversation order">
          <select
            value={value.conversation_order || "oldest_first"}
            onChange={(e) => change("conversation_order", e.target.value)}
          >
            <option value="oldest_first">Oldest reply first</option>
            <option value="newest_first">Newest reply first</option>
          </select>
        </Field>
        <Field label="Customer portal">
          <select
            value={value.customer_portal || "required_login"}
            onChange={(e) => change("customer_portal", e.target.value)}
          >
            <option value="required_login">Login required</option>
            <option value="optional_login">Login optional</option>
            <option value="disabled">Disabled</option>
          </select>
        </Field>
        <Field label="Session duration (minutes)">
          <input
            type="number"
            min="15"
            value={value.session_minutes || 480}
            onChange={(e) => change("session_minutes", +e.target.value)}
          />
        </Field>
        <Toggle
          label="Automatically assign eligible technicians"
          value={value.auto_assign !== false}
          onChange={(next) => change("auto_assign", next)}
        />
        <Toggle
          label="Allow customers to reopen tickets"
          value={value.allow_reopen !== false}
          onChange={(next) => change("allow_reopen", next)}
        />
        <Toggle
          label="Require requester email"
          value={value.require_email !== false}
          onChange={(next) => change("require_email", next)}
        />
        <Toggle
          label="Require subject"
          value={value.require_subject !== false}
          onChange={(next) => change("require_subject", next)}
        />
        <Toggle
          label="Require description"
          value={value.require_message !== false}
          onChange={(next) => change("require_message", next)}
        />
        <Toggle
          label="Track time worked"
          value={value.time_tracking !== false}
          onChange={(next) => change("time_tracking", next)}
        />
        <Toggle
          label="Allow ticket ratings"
          value={value.ticket_ratings !== false}
          onChange={(next) => change("ticket_ratings", next)}
        />
        <Toggle
          label="Enable attachments"
          value={value.attachments_enabled !== false}
          onChange={(next) => change("attachments_enabled", next)}
        />
        <Field label="Maximum files per reply">
          <input
            type="number"
            min="1"
            max="20"
            value={value.max_files_per_reply || 10}
            onChange={(e) => change("max_files_per_reply", +e.target.value)}
          />
        </Field>
        <Field label="Maximum file size (MB)">
          <input
            type="number"
            min="1"
            max="100"
            value={value.max_file_size_mb || 25}
            onChange={(e) => change("max_file_size_mb", +e.target.value)}
          />
        </Field>
        <Field
          label="Allowed file extensions"
          wide
          help="Comma-separated allowlist; executable and script formats remain blocked."
        >
          <input
            value={(value.allowed_file_types || []).join(", ")}
            onChange={(e) =>
              change(
                "allowed_file_types",
                e.target.value
                  .split(",")
                  .map((x) => x.trim().toLowerCase())
                  .filter(Boolean),
              )
            }
          />
        </Field>
        <Field label="Failed login attempts before lockout">
          <input
            type="number"
            min="3"
            max="20"
            value={value.login_attempts || 5}
            onChange={(e) => change("login_attempts", +e.target.value)}
          />
        </Field>
        <Field label="Lockout duration (minutes)">
          <input
            type="number"
            min="5"
            value={value.lockout_minutes || 15}
            onChange={(e) => change("lockout_minutes", +e.target.value)}
          />
        </Field>
      </div>
      <div className="helpdesk-settings-actions">
        <button className="primary" onClick={save}>
          Save Help Desk Settings
        </button>
      </div>
    </Panel>
  );
}

function General() {
  const resource = useLoad("/admin/organization"),
    [message, setMessage] = useState("");
  if (!resource.data)
    return <div className="loading">Loading organization…</div>;
  async function save(e: FormEvent) {
    e.preventDefault();
    await api("/admin/organization", {
      method: "PATCH",
      body: JSON.stringify(resource.data),
    });
    setMessage("Organization settings saved and audited.");
  }
  return (
    <Panel
      title="Organization identity"
      text="Branding and support defaults used throughout this organization."
      action={null}
    >
      <form className="general-form" onSubmit={save}>
        {message && <Notice type="success">{message}</Notice>}
        <Field label="Organization name">
          <input
            value={resource.data.name}
            onChange={(e) =>
              resource.setData({ ...resource.data, name: e.target.value })
            }
          />
        </Field>
        <Field label="Time zone">
          <input
            value={resource.data.timezone}
            onChange={(e) =>
              resource.setData({ ...resource.data, timezone: e.target.value })
            }
          />
        </Field>
        <Field label="Support email">
          <input
            value={resource.data.support_email}
            onChange={(e) =>
              resource.setData({
                ...resource.data,
                support_email: e.target.value,
              })
            }
          />
        </Field>
        <Field label="Support phone">
          <input
            value={resource.data.support_phone}
            onChange={(e) =>
              resource.setData({
                ...resource.data,
                support_phone: e.target.value,
              })
            }
          />
        </Field>
        <Field label="Logo URL" wide>
          <input
            value={resource.data.logo_url}
            onChange={(e) =>
              resource.setData({ ...resource.data, logo_url: e.target.value })
            }
          />
        </Field>
        <button className="primary">Save organization</button>
      </form>
    </Panel>
  );
}
function ReadOnly({ kind }: { kind: string }) {
  const path = kind === "audit" ? "/audit" : "/admin/health",
    resource = useLoad(path);
  const [detail,setDetail]=useState<any>(null);
  if (resource.error)
    return (
      <Notice>
        {resource.error} <button onClick={resource.load}>Retry</button>
      </Notice>
    );
  if (!resource.data) return <div className="loading">Loading…</div>;
  return (
    <Panel
      title={
        kind === "audit" ? "Administrative audit trail" : "Application health"
      }
      text={descriptions[kind]}
      action={<button onClick={resource.load}>Refresh</button>}
    >
      {kind === "audit" ? (
        <div className="log-list">
          {resource.data.map((x: any) => (
            <article key={x.id} className="audit-entry" role="button" tabIndex={0} onClick={()=>setDetail(x)} onKeyDown={e=>{if(e.key==="Enter"||e.key===" ")setDetail(x)}}>
              <Status active label="Recorded" />
              <div>
                <strong>{x.action}</strong>
                <p>
                  {x.record_type} {x.record_id || ""} · actor{" "}
                  {x.actor?.name || x.actor_id || "system"}
                </p>
                {x.details?.recipient && <p>To: {x.details.recipient.name || "Unknown"} · {x.details.recipient.email || "No email"}</p>}
                <small>{new Date(x.created_at).toLocaleString()}</small>
              </div>
              <button type="button" onClick={e=>{e.stopPropagation();setDetail(x)}}>View details</button>
            </article>
          ))}
        </div>
      ) : (
        <div className="health-grid-console">
          {Object.entries(resource.data).map(([k, v]) => (
            <article key={k}>
              <small>{k.replaceAll("_", " ")}</small>
              <strong>
                {typeof v === "object"
                  ? JSON.stringify(v)
                  : String(v ?? "Not configured")}
              </strong>
            </article>
          ))}
        </div>
      )}
      {detail&&<Modal title="Audit event details" onClose={()=>setDetail(null)}>
        <div className="wide audit-detail">
          <dl>
            <div><dt>Action</dt><dd>{detail.action}</dd></div>
            <div><dt>Date and time</dt><dd>{new Date(detail.created_at).toLocaleString()}</dd></div>
            <div><dt>Actor</dt><dd>{detail.actor ? `${detail.actor.name} · ${detail.actor.email}` : "System"}</dd></div>
            <div><dt>Record</dt><dd>{detail.record_type} {detail.record_id || ""}</dd></div>
            {detail.details?.recipient&&<div><dt>Recipient</dt><dd>{detail.details.recipient.name || "Unknown"} · {detail.details.recipient.email || "No email"}</dd></div>}
            {detail.details?.ticket&&<div><dt>Ticket</dt><dd>{detail.details.ticket.number} · {detail.details.ticket.subject}</dd></div>}
            {detail.details?.notification&&<div><dt>Delivery</dt><dd>{detail.details.notification.event} · {detail.details.notification.delivery_status}</dd></div>}
            <div><dt>Source IP</dt><dd>{detail.source_ip || "System process"}</dd></div>
            <div><dt>Correlation ID</dt><dd>{detail.correlation_id}</dd></div>
          </dl>
          <strong>Recorded values</strong>
          <pre>{JSON.stringify({previous:detail.previous,new:detail.new},null,2)}</pre>
        </div>
      </Modal>}
    </Panel>
  );
}
function Jump({
  title,
  text,
  action,
  onClick,
}: {
  title: string;
  text: string;
  action: string;
  onClick: () => void;
}) {
  return (
    <section className="console-jump">
      <span>✦</span>
      <h3>{title}</h3>
      <p>{text}</p>
      <button className="primary" onClick={onClick}>
        {action} →
      </button>
    </section>
  );
}

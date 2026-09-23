# Northstar Desk — Administrator manual

## Administration principles

Configure the system from **Settings** and **Administration**; do not edit application code or database rows manually. Changes are permission-controlled and recorded in the audit log. Use PostgreSQL for production and keep database credentials, OAuth secrets, and signing keys outside the application directory.

## Initial setup checklist

1. Configure the database and verify backups and restoration.
2. Configure hostname, ports, TLS/reverse proxy, and firewall rules.
3. Configure Microsoft Entra ID for SSO and first-login account creation.
4. Configure teams, group types, queues, categories, and routing rules.
5. Configure notification templates and test-mode suppression before adding real users.
6. Configure Microsoft Graph email and RingCentral only after provider permissions and redirect URLs are approved.
7. Create or publish request forms and approval workflows.
8. Enroll endpoint agents using the approved deployment package or Group Policy.

## Identity and users

Microsoft Entra ID is the preferred sign-in method. Users authenticate with their company account and MFA; active local accounts are optional for break-glass administration and testing. First successful SSO login can create the local profile according to the configured policy.

Manage users under **Settings → Users**:

- **Tech users** are eligible for assignment and team queues.
- **All users** are requesters and may submit or view their own tickets.
- Assign roles, teams, availability, and group membership deliberately.
- Reset a local password with a temporary password; the user must change it at next sign-in.
- Disable accounts rather than deleting historical ownership records unless retention policy permits deletion.

Standard roles are end user, technician, team lead, manager, administrator, and auditor. Permissions are enforced by the API, not merely hidden in the interface.

## Teams, groups, queues, and routing

Create teams for service ownership (for example MRA, US-Tech, or India-Tech). Create queues for the work stream and select the owning team. Use round-robin for balanced assignment; use least-active when workload depth is the deciding factor.

Routing rules are evaluated by priority. Build rules from conditions such as request type, category, sender/requester domain, location, form, or channel, then set actions such as assign team, assign queue, assignment method, and priority. Use a specific rule for each business boundary (for example `requester domain = medreceivables.com → MRA queue`) and test it with a representative sample before activating it. Enable “stop processing” only when later rules must not run.

## Categories and forms

Categories drive reporting, forms, SLAs, and routing. Keep names stable and use subcategories for meaningful operational detail. In **Studio**, create reusable incident, change, access, hardware, and support request forms. Configure required fields, dropdown options, help text, visibility, asset/user fields, and approval workflow. Save drafts for review; publish only after live testing.

## Approvals and change management

Create approval workflows tied to forms. Define ordered approval steps by role or named approver. Pending items appear in **Approvals**; decisions, comments, and notification events are retained with the ticket. Require approval for changes that affect production, security, access, or regulated data.

## Email and notifications

Microsoft Graph application permissions are used for unattended mailbox intake and outbound mail. Configure the mailbox, allowed sender/domain policy, and notification templates. Inbound messages are deduplicated by Message-ID and threaded using ticket number, In-Reply-To, and References. Outbound notifications should use the ticket number in the subject.

Use predefined notification rules as starting templates, then edit recipients, subject, body, conditions, and suppression behavior. In a test environment, disable global email delivery or enable a safe test recipient before onboarding users. Review delivery activity and audit details when diagnosing mail.

## RingCentral and call intake

Configure RingCentral OAuth credentials, webhook URL, queue/extension mapping, and the call-creation policy. Create a ticket only for the configured queue/extension and the event that indicates a technician answered; do not create tickets for every ringing or missed event unless explicitly required.

## Reports and leadership reporting

Use **Reports** for live operational views and **Studio → Reports** for reusable custom reports. A saved report can define its own columns, filters, date conditions, grouping, and CSV output. Recommended leadership views include service volume, backlog aging, SLA attainment, first-response and resolution times, technician workload, reopen rate, top categories, and approval/change activity.

For a password-reset report, set the date range (for example the previous six months) and export password-reset audit activity. The export includes timestamp, action, user, record, source IP, and event details.

## Asset inventory and endpoint agents

The endpoint agent sends inventory to the server and does not retain ticket or inventory data locally. Match assets to users by email and hostname/asset tag. Deploy through the packaged installer or Group Policy. Review enrollment and last-inventory timestamps in **Assets**; investigate stale or unidentified devices.

## Security, backups, and updates

- Use TLS in production and synchronize server time with a trusted Windows time source.
- Restrict database, attachment, and configuration directories to the service account and administrators.
- Store OAuth client-secret **values**, not secret IDs; never place secrets in tickets or source control.
- Keep encrypted backups and test restoration before upgrades.
- Apply updates through the administrator-only update workflow or the versioned server installer. Confirm the displayed application version after restart and retain the release hash.

## Audit and incident response

The audit log records configuration changes, authentication, routing, notifications, approvals, email processing, and security events. Open an event for full details when available. Preserve correlation IDs, timestamps, and safe diagnostics. Do not modify audit records.

## Smart Self-Service

Smart Self-Service is disabled by default. In **Settings → Smart self-service**, create tenant-owned knowledge articles as drafts, review their requester-facing steps, and publish them before use. Begin with **Suggest to technician** mode. Only approved low-risk articles can be marked for automatic delivery. High-priority, restricted, security, access, change, outage, and VIP requests are excluded. Unanswered offers return to IT after the configured response window; every offer, outcome, publication, and timeout is retained in the ticket and audit history.

## Common recovery actions

- Service unavailable: verify the Northstar service, PostgreSQL, port, reverse proxy, and Windows firewall.
- Invalid host header: confirm the configured hostname/allowed hosts and use the canonical URL.
- OAuth failure: verify redirect URI, tenant, client ID, secret value, provider consent, and synchronized server clock.
- Database migration failure: stop the service, preserve the verified backup, review `C:\ProgramData\NorthstarDesk\setup-error.log`, and restore or resume only after diagnosis.
- Port conflict: change the configured HTTP/HTTPS ports and restart the service; do not hard-code a port in a shortcut or proxy.

# Northstar Desk — Technician manual

## Purpose

Northstar Desk is the service desk workspace for incidents, service requests, changes, approvals, communication, and asset context. Use the ticket as the single record of work: every reply, note, decision, attachment, and status change belongs there.

## Daily workflow

1. Sign in with Microsoft SSO (MFA applies) or your assigned local account.
2. Open **Overview** to review active work, unassigned tickets, high-priority work, SLA risk, and waiting states.
3. Open **Tickets** and choose the appropriate view: assigned to me, my team, unassigned, overdue, or all open tickets.
4. Open a ticket by selecting its ticket number or subject. Confirm the requester, email, affected asset, owning team, priority, and SLA target.
5. Work the request, recording meaningful progress in the timeline.

## Ticket communication

- **Public reply** is visible to the requester and sends the configured notification to the requester and assigned technician as applicable.
- **Internal note** is for technician and manager coordination and is not shown to the requester.
- **Restricted note** is for sensitive operational information and is limited to authorized roles.
- Reply from the ticket whenever possible. Email replies containing the ticket number remain in the same conversation and are saved to the ticket.
- Do not include passwords, MFA codes, payment data, or sensitive personal information in a ticket.

## Assignment and status

Assignment is normally automatic through routing rules and queue round-robin. A technician may manually assign a ticket when authorized. Only available technicians are eligible for automatic assignment.

Use statuses consistently:

- **New/Assigned** — received and ownership is being established.
- **In Progress** — actively being worked.
- **Waiting on User/Vendor/Approval** — work is blocked; add a note explaining the next action and owner.
- **Resolved** — solution delivered; include a concise resolution summary.
- **Closed** — requester confirmed resolution or the closure policy completed.

When changing priority, provide the reason. Never close a ticket without documenting the outcome.

## Requester and asset context

Requester identity is taken from the authenticated account or inbound email. The requester’s assigned asset inventory is displayed when available. Verify the hostname/asset tag before troubleshooting and mention the relevant device in your notes.

## Attachments and chat

Use the attachment area for screenshots, logs, and approved support files. Do not upload secrets. Live chat invitations and messages are stored as part of the ticket; move important decisions from chat into a clear public reply or internal note.

## Safe automation

If an approved action is available (for example restarting a service or closing a frozen application), review the target and requester impact before running it. Record what was requested, what ran, and the result. Actions are permission-controlled and audited.

## Smart Self-Service suggestions

When an approved knowledge match appears on a ticket, verify that the steps are safe and relevant, then select **Send suggested solution**. The exact guidance is saved in the public timeline. The requester can confirm the fix, report that it did not work, or request live help. A failed, declined, or unanswered suggestion returns the ticket to IT; it never silently closes the request.

## Technician reporting

Use **Reports** to review workload, SLA performance, aging, requester demand, and team distribution. Administrators can create custom reports in **Studio → Reports** with selected columns, filters, grouping, and CSV export.

## Troubleshooting

- Ticket not found: return to **Tickets**, refresh, and open the current ticket number; access is authorization-scoped.
- Email reply creates a new ticket: include the ticket number in the subject and ensure the original message headers are preserved.
- Missing requester or asset: verify the email address matches the directory/asset record exactly.
- No notification: check the ticket timeline and ask an administrator to review notification rules, delivery status, and the global test-environment suppression setting.

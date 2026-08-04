# Manual acceptance checklist

## Studio, approvals, and custom reporting

- [ ] Administrator creates a draft form by dragging or clicking fields, reorders fields, publishes it, and sees it in the service catalog.
- [ ] Required fields and configured choices are enforced on submission.
- [ ] Incident Report creates an `INC-` ticket and Change Management creates a `CHG-` ticket.
- [ ] Submitting Change Management places the ticket in Waiting on Approval and adds it to the assigned manager's approval inbox.
- [ ] Approver records a comment and approves; requester receives an in-app notification and queued email, and the ticket returns to IT work.
- [ ] Approver rejects a test request; requester is notified and the ticket is cancelled with decision history retained.
- [ ] SMTP delivery succeeds under the background-worker account and a forced delivery failure appears in Automation failures without exposing credentials.
- [ ] Administrator creates a saved report using both standard ticket fields and a custom form field.
- [ ] Manager searches for, runs, groups, and exports the saved report; restricted records remain hidden from unauthorized roles.

## Installation and identity

- [ ] Fresh Windows installation completes with `scripts\install.ps1`.
- [ ] `scripts\start.ps1` opens a healthy service at `http://127.0.0.1:8000`.
- [ ] All documented test roles can sign in and must replace the temporary password.
- [ ] Five failed passwords lock the account; administrator reset restores it.
- [ ] Logout invalidates the session, and expired sessions require login.

## End user

- [ ] End user creates each request type and sees a unique INC, REQ, or HR number.
- [ ] Affected asset selector shows only that user's assets.
- [ ] End user sees only their tickets and public messages.
- [ ] User reply notifies the technician; confirm resolution closes a ticket.
- [ ] Recently resolved ticket reopens; old or ineligible ticket does not.
- [ ] Announcements and feedback submission work.

## Technician and manager

- [ ] Queue views show unassigned, personal, team, SLA, priority, and waiting work.
- [ ] Public reply notifies the user; internal and restricted notes remain distinct.
- [ ] Assignment, category, priority reason, next action, waiting state, resolve, and bulk status work.
- [ ] Unavailable technicians are excluded from automatic assignment and the reason is recorded.
- [ ] Dashboard metrics open their underlying records and CSV export downloads authorized data.

## Email, assets, audit, and operations

- [ ] Configured IMAP message creates a ticket and acknowledgment notification.
- [ ] Reply threads via headers even with a changed subject.
- [ ] Duplicate, bounce, auto-reply, and out-of-office messages create no duplicate ticket.
- [ ] Attachment metadata is recorded while contents are absent; sender receives policy text.
- [ ] Asset tag, populated hostname, and populated serial number enforce uniqueness.
- [ ] Asset reassignments retain history.
- [ ] Every privileged action creates an append-only audit event.
- [ ] Worker/mail/database/migration state appears on health.
- [ ] Failed automation appears in the exception queue and can be resolved with a note.

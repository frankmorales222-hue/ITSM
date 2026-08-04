# Northstar Studio guide

Northstar Studio lets each organization create service forms, approval paths, and saved reports without changing application code. Administrators open **Studio** from the main navigation.

## Form designer

1. Select **New** in the form library.
2. Name the form and choose its ticket category.
3. Drag fields from the palette into the canvas, or click a field type on touch devices.
4. Drag existing fields to reorder them. Edit the label, stable field key, instructions, required state, and choices directly on the canvas.
5. Enable **Published** when the form is ready for the service catalog, then save.

Supported controls include short and long text, dropdowns, multiple choice, date, number, checkbox, email, asset, user, and section headings. Field definitions and submissions are validated again on the server. Existing submissions retain their recorded values when a form is later changed.

The installation includes published Incident Report, Change Management, and IT Support forms. They are normal organization-owned Studio forms and may be changed or unpublished.

## Approval workflows

Each form can have one active approval workflow. A workflow may contain up to 20 sequential steps. Each step can route to the first active user in a role or to a specific active user.

Submitting a form with a workflow creates the ticket in **Waiting on Approval**, adds it to the approver's inbox, and queues an email notification. An approval advances to the next step. The final approval releases the ticket to IT. A rejection cancels the ticket and emails the requester. Every decision, comment, step, and notification is recorded in the audit and ticket history.

Configure SMTP values in `.env`, then run:

```powershell
scripts\configure-smtp-secret.ps1 -Username helpdesk@example.org
```

The SMTP password is stored in Windows Credential Manager, not in `.env` or the database. The background worker sends pending approval emails. Delivery failures appear in the automation exception queue.

## Report builder

Administrators choose report columns, drag them into the desired order, add safe filters, and optionally group results. Ticket fields and every custom form field are available. Saved reports appear under **Custom reports**, where authorized managers, team leads, administrators, and auditors can search, run, and export them.

Reports use role-scoped ticket visibility. A saved report never bypasses restricted-ticket or organization boundaries. The screen displays at most 1,000 matching rows; larger result sets should be narrowed with filters.

## Governance recommendations

- Keep stable field keys after publishing because report definitions reference them.
- Test a new form and approval route with non-production users before publishing broadly.
- Use a specific approver when only one person has authority; use a role when coverage is more important.
- Periodically deactivate obsolete reports and forms instead of reusing them for unrelated purposes.
- Treat form and workflow changes as controlled configuration because every change affects future records.

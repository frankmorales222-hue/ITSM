# Northstar Studio guide

Northstar Studio lets each organization create service forms, approval paths, and saved reports without changing application code. Administrators open **Studio** from the main navigation.

Every published request form inherits a system-controlled requester panel. It shows the Requested For profile, the authenticated Opened By user, local request date/time, and inventory assets matched by email. Authorized IT staff can request for another active user. The ticket stores an immutable requester snapshot so later directory changes do not rewrite historical context.

## Form designer

The visual designer has three working areas: the form and field library, the live requester-facing canvas, and the properties inspector. Open an existing form or choose **New form**, then start from a blank canvas or a professional starter kit for a complete IT service request, incident, access request, or change management.

Drag or click fields from the compact element list to add them, drag existing fields to reorder them, and select any field to configure its label, stable reporting key, placeholder, help text, choices, required state, and width. Hover over a field in the element library for an explanation of what it collects and when to use it. Text, email, and phone fields also support a character limit such as 8 or 25; this controls both the maximum accepted answer and the visible input length. Dropdown, radio, choice-card, and multi-select options are managed as individual rows with **Add option** and remove controls. The canvas supports desktop, tablet, and mobile previews. Full, two-thirds, half, and one-third field widths are carried into the published service-catalog form.

Supported controls include short and long text, dropdowns, visual choice cards, radio groups, multi-selects, date, time, number, phone, checkbox, email, asset, user, and section headings. Field definitions and submissions are validated again on the server. Existing submissions retain their recorded values when a form is later changed.

Each field can be visible, hidden, read-only, or conditionally displayed when another field has a configured answer. Conditional fields let one smart form show hardware questions after Hardware is selected, access questions after Access is selected, and so on. Hidden and non-matching required fields do not block submission.

Fields using the reporting keys `impact` and `urgency` drive ticket priority calculation when submitted. **Save draft** keeps the form editable and hidden from requesters. **Save template** stores a reusable starting pattern that is also hidden from requesters. **Publish** is the only action that makes a form available in the service catalog. Saving a published form as a draft removes it from the catalog.

The installation also creates **Studio Field Test Form** as an unpublished draft. It contains every supported field type, multi-option choice controls, multiple layouts, required fields, and live ITSM person/asset selectors. Use its Preview mode to test the requester experience, and publish it only if requesters should be able to submit it.

Asset linking uses the authoritative ticket requester email. On every standard, Studio, or email-created ticket, ITSM compares that address case-insensitively with the assigned employee email in Asset Inventory and automatically attaches every matching active asset. Any asset selected manually is merged with those matches. The technician-facing request context includes the asset tag, hostname, device type, manufacturer/model, serial number, assigned employee, location, and status.

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

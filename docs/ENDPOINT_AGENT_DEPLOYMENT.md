# Northstar Endpoint Agent deployment

## How automatic installation works

A browser is not permitted to silently install Windows software when somebody
signs in to Northstar Desk. Corporate devices therefore use a computer startup
deployment in Group Policy (or another device-management system). This provides
the intended zero-touch experience before the user opens the Help Desk.

The enterprise installer is idempotent:

- When no protected local configuration exists, it enrolls the computer once.
- When the agent is already enrolled, it upgrades the binaries and reuses the
  existing per-device credential. It does not enroll or install a second agent.
- It performs a full inventory upload before installation reports success.
- It starts the protected inventory process as LocalSystem at every startup.
- It performs another protected inventory immediately when a Windows user signs
  in, so the asset/user association does not wait for the normal collection cycle.
- It starts the notification-area companion for each user at sign-in.

## Group Policy command

Copy the contents of `endpoint_agent/artifacts/NorthstarEndpointAgent-enterprise`
to a computer-readable deployment share. Run this command from a computer
startup policy, replacing both paths:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\server\software\NorthstarEndpointAgent\install-enterprise.ps1" -ServerUrl "https://helpdesk.company.example" -EnrollmentTokenFile "\\server\software\NorthstarEndpointAgent\enrollment.token"
```

Restrict the deployment share and token file to domain computers and deployment
administrators. Remove the token file from the share after the rollout window.
Enrollment tokens are displayed once, expire, and have a maximum-use limit.

## User experience

The inventory service has no desktop access and its credential remains protected
for the machine account. A separate tray companion contains no credentials.
Clicking its icon displays:

- **Open Help Desk**
- **Create a Ticket**
- **Exit tray companion** (this does not stop inventory collection)

The tray starts for existing interactive sessions at their next Windows sign-in.

## Self-service installation from Northstar Desk

Authenticated users can install an unmanaged or remote Windows computer from
the Overview page:

1. Choose **Install Windows Agent**.
2. The app downloads `NorthstarEndpointAgent-Setup.exe` and copies a temporary
   enrollment code when browser permissions allow it.
3. Open setup, approve Windows UAC, and paste the code.
4. Setup enrolls one computer, uploads inventory immediately, and enables the
   tray companion.

The code expires after 30 minutes, works once, and is replaced when that user
generates another code. The download requires an authenticated Help Desk
session. If the machine already has protected agent configuration, setup repairs
or updates the existing agent instead of enrolling a duplicate.

Self-service setup does not bypass Windows administration policy. A user without
local installation rights must have an administrator approve the UAC prompt.

## Local test

HTTP is accepted only for `localhost` and `127.0.0.1`. All non-local deployments
must use HTTPS. An administrator can test the package with:

```powershell
.\install-enterprise.ps1 -ServerUrl "http://127.0.0.1:8011" -EnrollmentTokenFile ".\enrollment.token"
```

Uninstall with `uninstall-enterprise.cmd`. Add `-PurgeData` to the PowerShell
uninstaller only when the protected enrollment data should also be removed.

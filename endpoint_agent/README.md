# Northstar Windows Endpoint Agent

This is the standalone Windows inventory collector for Northstar Desk and the shared Asset Inventory. It collects technical endpoint facts, keeps a local snapshot and durable upload queue, and sends inventory to the ITSM API with a per-device credential.

## Ownership rules

- The agent owns observed hardware, hostname, operating system, software, security, health, and last-seen facts.
- AssetPilot/ITSM owns asset tag, assigned employee, location, department, purchasing, warranty, vendor, cost, and lifecycle.
- Existing assets are matched by device link, serial number, then hostname.
- A new discovery receives a clearly marked `DISC-...` identifier until an administrator reconciles it with the business inventory.
- A matching signed-in work email is confirmed automatically. An unassigned asset needs two consecutive observations before assignment. Conflicts are flagged and never overwrite the official assignment.

## Pilot installation

1. Start Northstar Desk and sign in as an administrator.
2. Open **Assets → Endpoint agents → Generate enrollment token**.
3. Copy the one-time token.
4. From Command Prompt, run:

```cmd
endpoint_agent\scripts\install-pilot.cmd http://127.0.0.1:8000 user@company.com
```

Run the command from **Command Prompt or PowerShell**. The installer securely prompts for the one-time token so it is not displayed or saved in command history. It reuses the Python runtime already installed for Northstar Desk and creates an isolated environment for the agent.

The email argument is optional. Without it, the agent uses `whoami /upn`. The installer performs the first inventory immediately and creates a quiet per-user Windows Startup shortcut using `pythonw.exe`. Running the installer again repairs or upgrades an existing enrollment without requesting another token.

For computers other than the ITSM server, replace `127.0.0.1` with the centrally hosted HTTPS Northstar Desk address. Do not deploy credentials over plain HTTP across a network.

## Enterprise installation

The production package installs a standalone executable under Program Files, keeps credentials and inventory under ProgramData, and registers a machine-level Scheduled Task that runs as LocalSystem at startup. No Python installation is required on endpoint computers.

1. Configure Northstar Desk with PostgreSQL and a trusted HTTPS DNS address.
2. In **Assets → Endpoint agents**, generate an **Enterprise deployment token**.
3. Put the token in a protected text file available only to the deployment system.
4. Build the package on the ITSM build computer:

```powershell
endpoint_agent\scripts\build-enterprise-package.ps1
```

5. Deploy the resulting ZIP through Intune, Group Policy, or an RMM and run elevated:

```cmd
install-enterprise.cmd https://helpdesk.company.example enrollment.token
```

The same command repairs or upgrades an installed agent. The enrollment token is deleted from the endpoint after it is read. Use `uninstall-enterprise.cmd` to remove the executable while preserving diagnostics, or add `-PurgeData` to remove local inventory and credentials.

Recommended Intune detection rule: file exists at `C:\Program Files\Northstar Endpoint Agent\NorthstarEndpointAgent.exe` and Scheduled Task `Northstar Endpoint Agent` exists. Recommended install context: **System**, 64-bit PowerShell.

## Manual development run

```cmd
set PYTHONPATH=endpoint_agent
python -m asset_agent --data-dir data\agent-pilot --server http://127.0.0.1:8000 --enrollment-token TOKEN --once
```

Agent data is stored under `%LOCALAPPDATA%\NorthstarEndpointAgent`. The device credential is protected using Windows DPAPI. Inventory continues to queue locally while the server is unavailable.

## Deployment behavior and safeguards

- The pilot installer runs in a signed-in user session; the enterprise installer runs machine-wide as LocalSystem.
- Enterprise credentials use Windows DPAPI machine scope and ProgramData ACLs restricted to SYSTEM and administrators.
- Production packages can be Authenticode-signed by passing `-CertificateThumbprint` to the build script.
- The server must be centrally reachable over trusted HTTPS before deployment.
- Some security probes may report `Unavailable` under normal-user permissions; the inventory still completes.
- Asset assignment based on observed email is disabled for records marked with `extended_data.assignment_mode = "shared"`.
- Identity matching uses unique email/UPN, directory object ID, employee ID, and finally the configured account-name fallback. Ambiguous, conflicting, and unknown identities enter assignment review and do not overwrite ownership.

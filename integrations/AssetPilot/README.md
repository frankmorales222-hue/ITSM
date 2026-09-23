# AssetPilot 3.3

This is the permanent AssetPilot source repository:

`C:\Users\frank\OneDrive\rojects\Asset Inventory\AssetPilot-2.1-Source`

All future source changes, tests, packaging, and release notes belong here.
Production database files must remain outside OneDrive and outside this
repository.

All interface work must follow [UI_STANDARDS.md](UI_STANDARDS.md). A UI change
is incomplete if it clips content, causes page-level horizontal scrolling, or
has not been checked at the required responsive widths.

## Current status

AssetPilot 3.3 completes the planned Phase 3 scope and adds the Phase 3.1
usability corrections plus a professional application-wide experience. The application has been
reconstructed here as a normal, maintainable .NET solution and builds without
references to the former compiled distribution. A clean startup is verified
with all migrations, the deduplicated bundled inventory, the health endpoint,
and the first-run administrator workflow.

The original Razor views were recovered as generated C# view sources. They
preserve the 2.0 UI while the pages changed for 2.1 are replaced with ordinary,
maintainable `.cshtml` files.

## Requirements

- .NET 10 SDK for source builds
- PowerShell 7 or Windows PowerShell 5.1 for the helper scripts

End-user release packages are self-contained and do not require .NET to be
installed on the destination computer or server.

## Build

From this folder:

```powershell
dotnet restore AssetPilot.slnx
dotnet build AssetPilot.slnx --no-restore -m:1
```

The single-worker option avoids intermittent output-file locks while the
repository is synchronized by OneDrive.

Or use:

```powershell
.\scripts\Build.ps1
```

## Run locally

```powershell
dotnet run --project .\src\AssetPilot.Web\AssetPilot.Web.csproj --no-build
```

Open the URL printed in the terminal. On a brand-new database, AssetPilot
opens the administrator setup page first.

The development database defaults to:

`src\AssetPilot.Web\App_Data\assetpilot.db`

This path is ignored by source control. Never copy a live database while the
application is running; use **System > Backups**.

## Create an installable release

```powershell
.\scripts\Publish-AssetPilot.ps1 -RuntimeIdentifiers win-x64
```

Multiple targets can be produced in one command:

```powershell
.\scripts\Publish-AssetPilot.ps1 `
  -RuntimeIdentifiers win-x64,win-arm64,linux-x64,linux-arm64
```

Self-contained ZIP files and SHA-256 checksums are written to `artifacts`.

## AssetPilot 3.3 completed features

- redesigned command-center dashboard with lifecycle, availability, assignment,
  shipment, and purchasing signals
- dashboard-style Available Stock and Operations Reports pages
- plain-language stock goals with prominent red warnings below the configured
  percentage and an exact purchase-request quantity
- plain-language settings labels with stock planning routed to Available Stock
- consistent filter, action, status, and return-flow terminology
- corrected Master Data validation and case-insensitive search
- consistent professional navigation with the correct active item on every page
- context-aware asset return links for stock, inventory, employee, dashboard,
  and global-search workflows
- application-wide partial search for assets, employees, and shipments; Ctrl+K
  focuses this search from anywhere
- protected Administrator permissions and visible Built-in/Custom role states
- one-click restoration of built-in role templates
- reliable branding saves without unrelated settings validation
- exact-format audit export matching `Asset inventory US.xlsx`
- Assigned To followed by Asset/Hostname in the inventory list
- every workbook field available while creating or editing an asset
- multiple monitors plus dock, keyboard, mouse, headset, and printer
- employee creation linked directly to asset creation and assignment
- shipment **Update Shipping** action with UPS, FedEx, and USPS adapters,
  public tracking links, last-checked details, and event history
- deduplicating future imports
- partial, case-insensitive search across all asset fields
- partial, case-insensitive search across employee names and all employee fields
- available stock that automatically excludes assigned assets
- configurable stock targets and percentage thresholds by type and location
- prominent dashboard and stock-page PR-required alerts
- direct assign, transfer, and return-to-stock controls on the asset record
- working asset detail tabs, including lifecycle and audit history
- clickable inventory rows and employee asset quick-view dialogs
- functional user, role, and permission security administration
- customizable application name, organization, logo, and primary color
- dedicated stock inventory totals and filters by type, location, and condition
- exact-format filtered export directly from Asset Inventory and Stock Inventory
- persistent duplicate-review queue with edit, retry, update, and dismiss decisions
- deletion of incorrect shipment tracking data without deleting the shipment
- protected employee deletion available only after the employee is disabled

`SeedData/Asset inventory US template.xlsx` is the canonical 36-column
import/export template supplied by the user. Imports must match its headers
exactly and exports are generated directly from that template. The separate
populated `Asset inventory US.xlsx` file is used only for the initial inventory
seed.

Carrier APIs require credentials issued by UPS, FedEx, or USPS. Configure them
with environment variables as documented in `DEPLOYMENT.md`; never place
credentials in source control.

## Repository map

- `src` — application source and database migrations
- `tests` — automated tests
- `scripts` — repeatable build and packaging commands
- `deployment` — release launcher/service templates
- `.recovery` — local reconstruction evidence and tools; not used by builds
- `SeedData` under the web project — bundled initial inventory

See [DEPLOYMENT.md](DEPLOYMENT.md) for computer and server installation.

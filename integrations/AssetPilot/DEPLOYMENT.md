# AssetPilot deployment

AssetPilot is distributed as a self-contained application. Target computers do
not need the .NET runtime, SQL Server, or IIS.

## User invitation email

AssetPilot emails new users a secure password-creation link. Configure these environment variables on the server before inviting users: `Email__Smtp__Host`, `Email__Smtp__Port` (normally `587`), `Email__Smtp__UseSsl` (normally `true`), `Email__Smtp__Username`, `Email__Smtp__Password`, and `Email__Smtp__FromAddress`.

Do not store a production SMTP password in `appsettings.json`. Use the server environment or secret manager. The invitation link uses the server address through which the administrator opened AssetPilot, so open the application using its shared production URL before sending invitations.

## Supported packages

The packaging script supports:

| Package | Intended host |
|---|---|
| `win-x64` | 64-bit Windows 10/11 and Windows Server |
| `win-arm64` | ARM64 Windows |
| `linux-x64` | 64-bit Linux servers |
| `linux-arm64` | ARM64 Linux servers |

The operating system still needs to be supported by .NET 10 and the machine
must allow the application to listen on its configured TCP port.

## Windows desktop

1. Extract the entire `AssetPilot-3.6.0-win-x64.zip`.
2. Double-click `Install AssetPilot.cmd`.
3. Start AssetPilot from the Desktop or Start Menu shortcut.

The installer is per-user and does not require administrator access. It places
the program under:

```text
%LOCALAPPDATA%\Programs\AssetPilot
```

The desktop launcher stores the database separately under:

```text
%LOCALAPPDATA%\AssetPilot\Data\assetpilot.db
```

The same extracted package can run without installation by double-clicking
`Start AssetPilot.cmd`.

## Windows Server

For an initial server test, extract the Windows package to a durable local
folder and run:

```cmd
"Run AssetPilot Server.cmd"
```

The default server launcher listens only on the local computer at port 5080 and
stores the database and verified backups in a `Data` folder beside the
executable. Keep this loopback-only default when using a reverse proxy.

```cmd
set ASPNETCORE_URLS=http://127.0.0.1:5080
set Database__Path=D:\AssetPilotData\assetpilot.db
set Backup__Path=D:\AssetPilotData\Backups
AssetPilot.exe
```

For production:

- Run AssetPilot using a dedicated, unprivileged service account.
- Keep the database on a local disk, not a network share.
- Grant the service account write access only to the database directory.
- Put IIS, nginx, Apache, or another reverse proxy in front of AssetPilot.
- Terminate HTTPS at the reverse proxy.
- Set `Hosting__UseForwardedHeaders=true` when the reverse proxy runs on the
  same server so AssetPilot honors the forwarded HTTPS scheme.
- Set `Hosting__UseHttpsRedirection=true` after forwarded headers and HTTPS are
  working.
- Forward only the intended port through the host firewall.
- Use a process supervisor or Windows service wrapper to restart the process
  after failure or reboot.

## Linux server

Extract the appropriate Linux package under `/opt/assetpilot`:

```bash
sudo mkdir -p /opt/assetpilot /var/lib/assetpilot
sudo unzip AssetPilot-3.6.0-linux-x64.zip -d /opt
sudo mv /opt/AssetPilot-3.6.0-linux-x64/* /opt/assetpilot/
sudo rmdir /opt/AssetPilot-3.6.0-linux-x64
sudo chmod +x /opt/assetpilot/AssetPilot
sudo chmod +x /opt/assetpilot/start-assetpilot.sh
```

For an interactive test:

```bash
ASPNETCORE_URLS=http://127.0.0.1:5080 \
Database__Path=/var/lib/assetpilot/assetpilot.db \
/opt/assetpilot/AssetPilot
```

The package includes `assetpilot.service`. Before installing it, create a
dedicated account and set directory ownership:

```bash
sudo useradd --system --home /var/lib/assetpilot --shell /usr/sbin/nologin assetpilot
sudo chown -R assetpilot:assetpilot /var/lib/assetpilot
sudo cp /opt/assetpilot/assetpilot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now assetpilot
sudo systemctl status assetpilot
```

Use nginx, Apache, Caddy, or another reverse proxy for HTTPS and external
network access.

## Configuration

Configuration can be supplied through `appsettings.json`, command-line
arguments, or environment variables. Environment variables use double
underscores for nested keys.

| Setting | Environment variable | Default |
|---|---|---|
| Listening URL | `ASPNETCORE_URLS` | `http://127.0.0.1:5080` |
| Database file | `Database__Path` | `App_Data/assetpilot.db` |
| HTTPS redirect | `Hosting__UseHttpsRedirection` | `false` |
| Reverse-proxy headers | `Hosting__UseForwardedHeaders` | `false` |
| Seed bundled inventory | `Import__SeedExistingInventory` | `true` |
| Backup directory | `Backup__Path` | `App_Data/Backups` |
| Environment | `ASPNETCORE_ENVIRONMENT` | `Production` |

The bundled inventory is checked at every startup. Existing matches are
skipped, so upgrades and restarts do not create duplicates. Set
`Import__SeedExistingInventory=false` only when deploying a new empty
installation that should not receive the bundled US inventory.

### Carrier tracking

The shipment page always provides the carrier's public tracking link. Automatic
status and event updates use each carrier's official API and require credentials
issued for your organization:

| Carrier | Environment variables |
|---|---|
| UPS | `Tracking__UPS__ClientId`, `Tracking__UPS__ClientSecret` |
| FedEx | `Tracking__FedEx__ClientId`, `Tracking__FedEx__ClientSecret` |
| USPS | `Tracking__USPS__ClientId`, `Tracking__USPS__ClientSecret` |

Set only the credentials for carriers you use. If credentials are absent,
**Update Shipping** reports that configuration is required without losing the
shipment or its tracking number. Store production secrets in the service
account's environment or a protected secret store, not in `appsettings.json`.

## SQLite deployment constraints

- Run exactly one AssetPilot application process per database.
- Do not point multiple servers at one SQLite file.
- Do not store the live database on SMB, NFS, OneDrive, or another synchronized
  or network filesystem.
- Use a local SSD and include the database in a tested backup process.
- WAL mode creates `assetpilot.db-wal` and `assetpilot.db-shm` while running.
- A live-file copy is not a safe backup workflow while writes are occurring.

These constraints are appropriate for the current SQLite deployment target. A multi-instance or
high-availability deployment would require a different database architecture
and is outside the current release.

## Verified backup and restore

Administrators can create a live, consistent backup from **System > Backups**.
AssetPilot uses SQLite `VACUUM INTO`, opens the resulting database read-only,
runs `PRAGMA quick_check`, and retains the file only when verification succeeds.

To restore:

1. Stop every AssetPilot process using the database.
2. Copy the current database and its WAL/SHM files to a recovery folder.
3. Copy the selected verified backup over the configured `assetpilot.db`.
4. Start AssetPilot.
5. Confirm `/health`, sign in, and compare the dashboard asset count.

Never replace the database while AssetPilot is running.

## Build distributable packages

On a development machine with the .NET 10 SDK:

```powershell
dotnet restore AssetPilot.slnx
dotnet build AssetPilot.slnx --configuration Release --no-restore -m:1
dotnet test AssetPilot.slnx --configuration Release --no-build -m:1

.\scripts\Publish-AssetPilot.ps1 -RuntimeIdentifiers win-x64
```

Build several platforms:

```powershell
.\scripts\Publish-AssetPilot.ps1 `
  -RuntimeIdentifiers win-x64,win-arm64,linux-x64,linux-arm64
```

ZIP archives and SHA-256 checksum files are written to `artifacts`.

## Phase 3 through 3.3 scope

This build includes the completed foundation plus deduplicated inventory
imports, exact-format audit export, comprehensive asset and peripheral entry,
employee-to-asset assignment, carrier tracking, logistics workflows,
operational reports, and system settings/jobs. It retains verified backups and
the single-process SQLite deployment model.

See `PRODUCTION_CHECKLIST.md` for the final installation, acceptance, backup,
and handoff procedure.


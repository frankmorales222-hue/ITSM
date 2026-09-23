# AssetPilot 3.3 production checklist

Use this checklist on the computer or server that will host the live
application. Do not use a test database as the production database.

## 1. Prepare the host

- Install current Windows security updates.
- Use a local SSD. Do not place the database in OneDrive, SharePoint, Dropbox,
  an SMB share, or another synchronized/network folder.
- Confirm only one AssetPilot process will use the database.
- Decide whether this is:
  - a single-computer installation using the Desktop/Start Menu launcher; or
  - a server installation behind an HTTPS reverse proxy.

## 2. Verify and install the package

1. Verify `AssetPilot-3.4.3-win-x64.zip` against its `.sha256` file.
2. Extract the entire ZIP before running anything.
3. For a desktop installation, run `Install AssetPilot.cmd`.
4. For a server, place the extracted files in a durable local application
   directory and use a dedicated unprivileged service account.

Desktop production data is stored at:

```text
%LOCALAPPDATA%\AssetPilot\Data\assetpilot.db
```

Desktop verified backups are stored at:

```text
%LOCALAPPDATA%\AssetPilot\Data\Backups
```

## 3. First start

- Start AssetPilot and wait for the browser to open.
- Confirm the first-run administrator page appears.
- Create the named administrator with a unique work email and a strong password
  of at least 12 characters.
- Store the password in the organization's approved password manager.
- Confirm the dashboard opens and the footer displays version 3.4.3.
- Open `/health` and confirm it returns a healthy response.

## 4. Validate production data

- Confirm the Asset Inventory count matches the approved source workbook.
- Search for several known employees, hostnames, asset tags, and serial
  numbers using partial text and different capitalization.
- Export Asset Inventory and confirm it opens in Excel with the approved
  36-column format.
- Run a second test import of the same workbook and confirm duplicates are sent
  to Duplicate Review rather than added as new assets.
- Review disabled employees and active asset assignments.

## 5. Configure stock planning

- Open **Available Stock**.
- Create a stock goal for each equipment type and location that needs a
  purchasing warning.
- Example: Laptop, All locations, Stock goal 50, Warn below 50%.
- Confirm a shortage is red on Available Stock, Dashboard, and Operations
  Reports.
- Confirm the recommended purchase-request quantity equals the stock goal minus
  available stock.

## 6. Verify permissions

- Open **Security** as the administrator.
- Confirm Administrator shows all permissions assigned and protected.
- Assign each user the smallest built-in role appropriate to their work.
- If a built-in role is modified, confirm it is labeled **Custom**.
- Keep at least two active administrator accounts after production handoff.
- Disable former users promptly; delete only disabled employees after their
  equipment is returned or transferred.

## 7. Verify backup and recovery

1. Open **Backups** and create a verified backup.
2. Confirm the backup appears with a verified status.
3. Record the database and backup directories.
4. Copy the verified backup to the organization's protected backup system.
5. Schedule a restore drill:
   - stop AssetPilot;
   - preserve the current database and WAL/SHM files;
   - restore the verified backup;
   - start AssetPilot;
   - confirm `/health`, sign-in, dashboard counts, and a sample asset.

Never copy or replace the live SQLite database while AssetPilot is running.

## 8. Server-only security

- Bind AssetPilot to `http://127.0.0.1:5080`.
- Put IIS, nginx, Apache, or Caddy in front of it.
- Serve users only over HTTPS.
- Set `Hosting__UseForwardedHeaders=true` for a same-host reverse proxy.
- Enable `Hosting__UseHttpsRedirection=true` only after forwarded HTTPS is
  confirmed.
- Allow external traffic only to the reverse proxy's HTTPS port.
- Run AssetPilot with automatic restart after failure and after reboot.
- Store carrier API credentials in protected environment variables, never in
  source files.

## 9. Final acceptance

Production is accepted when:

- `/health` confirms database connectivity;
- administrators and assigned roles can sign in;
- asset, employee, stock, shipment, report, import, export, and search
  workflows pass;
- the inventory count matches the approved workbook;
- duplicate imports do not create duplicate assets;
- a verified backup has been created and copied off-host;
- the production data path is local and documented;
- server users connect through HTTPS, if deployed as a server.

Record the installation date, host name, AssetPilot version, database path,
backup path, administrator owners, and restore-test date in the organization's
operations documentation.


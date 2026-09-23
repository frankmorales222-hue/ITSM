param()

$ErrorActionPreference = "Stop"
$installerRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $installerRoot
$compiler = @(
  "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw "Inno Setup 6 compiler is not installed." }

& (Join-Path $installerRoot "build-server-bundle.ps1")
if ($LASTEXITCODE -ne 0) { throw "The recovery server bundle could not be built." }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskUpdateController.iss"
  if ($LASTEXITCODE -ne 0) { throw "The update-controller payload could not be compiled." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Update-Controller-0.4.75.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Update-controller recovery: fixes signed component-update completion, restores automatic restart of the existing Northstar Desk and HTTPS tasks after a verified update, and refreshes the distributed Endpoint Agent 0.1.24 installer. It does not change the database, tickets, configuration, HTTPS certificate, Caddy configuration, ports, routing, email, or existing scheduled-task definitions."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.75" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.65" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.75.nsupdate") --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "The signed recovery update package could not be created." }

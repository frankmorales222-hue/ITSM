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

# The agent rejects stale AD computer-account overrides.  The component update
# also refreshes the server executable, which sanitizes any legacy bad value
# already stored in the database at the next agent heartbeat.
& (Join-Path $projectRoot "endpoint_agent\scripts\build-self-service-installer.ps1")
if ($LASTEXITCODE -ne 0) { throw "Endpoint-agent installer could not be built." }
& (Join-Path $installerRoot "build-server-bundle.ps1")
if ($LASTEXITCODE -ne 0) { throw "Server bundle could not be built." }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskIdentitySafety.iss"
  if ($LASTEXITCODE -ne 0) { throw "Asset identity safety update installer compilation failed." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Asset-Identity-Safety-Update-0.4.77.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Asset identity safety only: prevents AD computer accounts such as HOSTNAME$@company.com from replacing a real observed user, cleans legacy invalid observations at the next heartbeat, and ships Endpoint Agent 0.1.26. This update does not alter the database schema, tickets, routing, email, authentication, frontend, HTTPS certificates, Caddy configuration, ports, scheduled-task definitions, or other settings."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.77" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.65" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.77.nsupdate") --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "Asset identity safety update package signing failed." }

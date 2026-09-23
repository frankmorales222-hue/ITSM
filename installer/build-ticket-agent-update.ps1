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

$dist = Join-Path $projectRoot "frontend\dist"
$agent = Join-Path $projectRoot "endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.23.exe"
if (-not (Test-Path -LiteralPath (Join-Path $dist "index.html")) -or
    -not (Get-ChildItem -LiteralPath (Join-Path $dist "assets") -File -ErrorAction SilentlyContinue)) {
  throw "The compiled browser build is missing."
}
if (-not (Test-Path -LiteralPath $agent)) { throw "The endpoint agent installer is missing: $agent" }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskTicketAgent.iss"
  if ($LASTEXITCODE -ne 0) { throw "Ticket and agent update installer compilation failed." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Ticket-Agent-Update-0.4.73.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Ticket and endpoint-agent refresh only: moves linked asset details into the requester banner, strengthens the ticket timeline display, removes duplicate lower telemetry, adds Refresh Help Desk agent in the tray, and ships Endpoint Agent 0.1.23. The update does not alter the database, tickets, authentication, routing, email, HTTPS certificates, Caddy configuration, ports, or server executable."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.73" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.65" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.73.nsupdate") --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "Ticket and agent update package signing failed." }

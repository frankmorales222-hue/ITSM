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

& (Join-Path $projectRoot "endpoint_agent\scripts\build-self-service-installer.ps1")
if ($LASTEXITCODE -ne 0) { throw "Endpoint-agent installer could not be built." }
& (Join-Path $installerRoot "build-server-bundle.ps1")
if ($LASTEXITCODE -ne 0) { throw "Server bundle could not be built." }

Push-Location (Join-Path $projectRoot "frontend")
try {
  & npm.cmd run build
  if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
}
finally { Pop-Location }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskIdentityTheme.iss"
  if ($LASTEXITCODE -ne 0) { throw "Identity and appearance update installer compilation failed." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Identity-Theme-Update-0.4.79.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Appearance release: replaces the legacy theme choices with Modern Look (Infinx light theme) and Dark Mode. Includes the pending 0.4.77 endpoint identity correction and Endpoint Agent 0.1.26. This update does not alter the database schema or data, tickets, routing, email, authentication, HTTPS certificates, Caddy configuration, ports, scheduled-task definitions, or other settings."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.79" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.65" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.79.nsupdate") --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "Identity and appearance update package signing failed." }

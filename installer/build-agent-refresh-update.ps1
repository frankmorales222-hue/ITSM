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

$agent = Join-Path $projectRoot "endpoint_agent\artifacts\NorthstarEndpointAgent-Setup-0.1.39.exe"
if (-not (Test-Path -LiteralPath $agent)) { throw "The endpoint agent installer is missing: $agent" }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskAgentRefresh.iss"
  if ($LASTEXITCODE -ne 0) { throw "Agent refresh update installer compilation failed." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Agent-Refresh-Update-0.4.91.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Endpoint-agent only: ships Endpoint Agent 0.1.39. The tray returns to signed-in users after SYSTEM updates, and upgrades from the legacy 32-bit installation now repoint both scheduled tasks before safely removing only the old x86 files and uninstall entry. Endpoint enrollment and ProgramData configuration are preserved."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.91" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.86" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.91.nsupdate") `
  --component-update --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "Endpoint agent update package signing failed." }

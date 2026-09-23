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
if ($LASTEXITCODE -ne 0) { throw "The remote-agent publishing server bundle could not be built." }

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskRemoteAgentPublishing.iss"
  if ($LASTEXITCODE -ne 0) { throw "The remote-agent publishing update installer could not be compiled." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Remote-Agent-Publishing-Update-0.4.76.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Remote agent update delivery: adds an administrator-only release publisher in Assets > Endpoint agents. Administrators can upload a newer NorthstarEndpointAgent-Setup-x.y.z.exe installer once; enrolled remote agents receive its existing SHA-256-verified automatic update within one minute when online. This release does not change the database, tickets, routing, email, HTTPS certificates, Caddy configuration, ports, authentication, endpoint inventory, or existing agent workflow."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.76" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.65" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.76.nsupdate") --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "The remote-agent publishing update package could not be created." }

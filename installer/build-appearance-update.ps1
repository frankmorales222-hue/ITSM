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

# The checked-in dist is the release-verified 0.4.88 visual build. Refuse to
# package if its essential browser files are absent.
$dist = Join-Path $projectRoot "frontend\dist"
if (-not (Test-Path -LiteralPath (Join-Path $dist "index.html")) -or
    -not (Get-ChildItem -LiteralPath (Join-Path $dist "assets") -File -ErrorAction SilentlyContinue)) {
  throw "The verified appearance build is missing."
}

Push-Location $installerRoot
try {
  & $compiler "NorthstarDeskTheme.iss"
  if ($LASTEXITCODE -ne 0) { throw "Appearance update installer compilation failed." }
}
finally { Pop-Location }

$payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Appearance-Update-0.4.88.exe"
$privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
$passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
$notes = "Appearance-only corrective release: the Request timeline now scrolls with the full ticket page instead of using a fixed-height inner scrollbar. The package is correctly identified as a component update so successful installation is recorded without requiring a server-version change. It does not alter the database, tickets, routing, email, HTTPS certificates, Caddy configuration, ports, endpoint agent, or server application executable."
& (Join-Path $projectRoot ".venv\Scripts\python.exe") (Join-Path $installerRoot "update-package.py") build `
  --private-key $privateKey --password-file $passwordFile --payload $payload `
  --version "0.4.88" --publisher "Northstar" --release-notes $notes `
  --minimum-current-version "0.4.86" --output (Join-Path $installerRoot "artifacts\NorthstarDesk-0.4.88.nsupdate") `
  --component-update --allow-unsigned
if ($LASTEXITCODE -ne 0) { throw "Appearance update package signing failed." }

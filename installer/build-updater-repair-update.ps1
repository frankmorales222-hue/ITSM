param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $python)) { throw "Project Python runtime not found." }
if (-not $iscc) { throw "Inno Setup compiler was not found." }

Push-Location $projectRoot
try {
    & (Join-Path $PSScriptRoot "build-server-bundle.ps1") -Python $python
    if ($LASTEXITCODE -ne 0) { throw "Northstar Desk server bundle failed." }

    & $iscc (Join-Path $PSScriptRoot "NorthstarDeskUpdaterRepair.iss")
    if ($LASTEXITCODE -ne 0) { throw "Updater repair installer build failed." }

    $payload = Join-Path $PSScriptRoot "artifacts\NorthstarDesk-Updater-Repair-0.4.84.exe"
    $privateKey = Join-Path $PSScriptRoot "signing\private\northstar.update-private.pem"
    $passwordFile = Join-Path $PSScriptRoot "signing\private\northstar.update-private.password.txt"
    $output = Join-Path $PSScriptRoot "artifacts\NorthstarDesk-0.4.84.nsupdate"
    $notes = "Updater lifecycle repair. This one server update restarts Northstar Desk and HTTPS once. Future component-only updates keep both tasks online. It does not alter the database, tickets, configuration, HTTPS certificate, Caddy configuration, ports, endpoint agent, routing, or email."

    & $python (Join-Path $PSScriptRoot "update-package.py") build `
        --private-key $privateKey --password-file $passwordFile --payload $payload `
        --version "0.4.84" --publisher "Northstar" --release-notes $notes `
        --minimum-current-version "0.4.77" --output $output --allow-unsigned
    if ($LASTEXITCODE -ne 0) { throw "Signed update package build failed." }
    Write-Host "Updater repair package created at $output"
}
finally {
    Pop-Location
}

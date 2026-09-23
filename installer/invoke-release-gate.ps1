param(
    [string]$Python = "",
    [switch]$RequirePostgreSQL
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) { $Python = Join-Path $projectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Project Python runtime not found." }

function Invoke-Checked([string]$Label, [scriptblock]$Action) {
    Write-Host "RELEASE GATE: $Label"
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$Label failed with exit code $LASTEXITCODE." }
}

Push-Location $projectRoot
try {
    Invoke-Checked "frontend production build" {
        pnpm --dir frontend run build
    }
    Invoke-Checked "Northstar Python tests" {
        & $Python -m pytest -q --ignore=tests/test_postgresql_release_gate.py `
            --ignore=tests/test_server_installer.py
    }
    Invoke-Checked "server installer source tests" {
        & $Python -m pytest -q tests/test_server_installer.py -k "not final_server_installer_exists"
    }
    Invoke-Checked "AssetPilot unit tests" {
        dotnet test integrations/AssetPilot/tests/AssetPilot.UnitTests/AssetPilot.UnitTests.csproj `
            --no-restore -m:1 --disable-build-servers
    }
    Invoke-Checked "AssetPilot integration tests" {
        dotnet test integrations/AssetPilot/tests/AssetPilot.IntegrationTests/AssetPilot.IntegrationTests.csproj `
            --no-restore -m:1 --disable-build-servers
    }

    if ($RequirePostgreSQL) {
        if ($env:NORTHSTAR_POSTGRES_RELEASE_GATE -ne "EPHEMERAL_DATABASE_SERVER" -or
            -not $env:NORTHSTAR_POSTGRES_ADMIN_URL) {
            throw "An explicitly acknowledged disposable PostgreSQL server is required to build a release."
        }
        Invoke-Checked "PostgreSQL fresh-install and legacy-resume tests" {
            & $Python -m pytest -q --noconftest tests/test_postgresql_release_gate.py
        }
    }
    Write-Host "RELEASE GATE PASSED"
}
finally {
    Pop-Location
}

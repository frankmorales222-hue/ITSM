param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Database,
    [PSCredential]$Credential,
    [int]$Port = 5432,
    [string]$SourceDatabaseUrl = "sqlite:///./data/itsm.db"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
if ($Server -notmatch '^[A-Za-z0-9.-]+$') { throw "Server contains unsupported characters." }
if ($Database -notmatch '^[A-Za-z0-9_-]+$') { throw "Database contains unsupported characters." }
if (-not $Credential) { $Credential = Get-Credential -Message "Enter the PostgreSQL migration account" }
$user = [Uri]::EscapeDataString($Credential.UserName)
$password = [Uri]::EscapeDataString($Credential.GetNetworkCredential().Password)
$env:ITSM_MIGRATION_TARGET_URL = "postgresql+psycopg://${user}:${password}@${Server}:${Port}/${Database}"
Write-Host "A verified SQLite backup will be created before copying data."
try {
    & ".venv\Scripts\python.exe" -m itsm.database_ops migrate-to-postgres --source $SourceDatabaseUrl --target-env
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed. The SQLite source was not changed." }
} finally {
    Remove-Item Env:ITSM_MIGRATION_TARGET_URL -ErrorAction SilentlyContinue
}

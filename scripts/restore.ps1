param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [switch]$Confirm
)
$ErrorActionPreference = "Stop"
if (-not $Confirm) { throw "Restore changes the live database. Re-run with -Confirm after stopping Northstar Desk." }
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
& ".venv\Scripts\python.exe" -m itsm.database_ops restore $BackupPath --confirm RESTORE
if ($LASTEXITCODE -ne 0) { throw "Database restore failed." }

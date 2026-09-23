param(
    [string]$DataRoot = "$env:ProgramData\NorthstarDesk",
    [Parameter(Mandatory = $true)]
    [string]$PackagePath,
    [switch]$Confirm
)
$ErrorActionPreference = "Stop"
if (-not $Confirm) { throw "Import overwrites the configured Northstar database. Re-run with -Confirm after stopping Northstar Desk." }
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
$env:ITSM_CONFIG_FILE = Join-Path $DataRoot ".env"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
& ".venv\Scripts\python.exe" -m itsm.database_ops import-migration $PackagePath --data-root $DataRoot --confirm IMPORT
if ($LASTEXITCODE -ne 0) { throw "Migration package import failed." }
Write-Host "Migration import completed. Run database migrations before starting the service if this was not done by the packaged server command."

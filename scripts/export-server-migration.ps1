param(
    [string]$DataRoot = "$env:ProgramData\NorthstarDesk",
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$BackupPath = ""
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
$arguments = @("-m", "itsm.database_ops", "package-migration", "--data-root", $DataRoot, "--output", $OutputPath)
if ($BackupPath) {
    $arguments += @("--backup-path", $BackupPath)
}
& ".venv\Scripts\python.exe" @arguments
if ($LASTEXITCODE -ne 0) { throw "Migration package export failed." }
Write-Host "Transfer the package securely. It contains database data and configuration secrets."

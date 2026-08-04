param([switch]$Confirm)
if (-not $Confirm) { throw "This deletes and recreates demo data. Re-run with -Confirm." }
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
& ".venv\Scripts\python.exe" -m itsm.seed --reset


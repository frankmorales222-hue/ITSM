$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
& ".venv\Scripts\python.exe" -m itsm.production_check
if ($LASTEXITCODE -ne 0) { throw "Production readiness checks failed." }

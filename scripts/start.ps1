$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed. Run scripts\install.ps1 first." }
if (-not (Test-Path "frontend\dist\index.html")) { throw "Interface build is missing. Run scripts\build.ps1." }
$worker = Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m","itsm.worker" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
Write-Host "Northstar Desk starting at http://127.0.0.1:8000"
Write-Host "Background worker PID: $($worker.Id). Close this window to stop the web service; use Stop-Process $($worker.Id) to stop the worker."
& ".venv\Scripts\python.exe" -m uvicorn itsm.main:app --host 127.0.0.1 --port 8000


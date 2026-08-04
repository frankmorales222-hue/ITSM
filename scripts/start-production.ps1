$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"

if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
if (-not (Test-Path ".env")) { throw "Production .env file is missing." }
if (-not (Test-Path "frontend\dist\index.html")) { throw "Interface build is missing. Run scripts\build.cmd." }

& ".venv\Scripts\python.exe" -m itsm.database_ops backup
if ($LASTEXITCODE -ne 0) { throw "Startup stopped because the pre-migration backup failed." }
& ".venv\Scripts\python.exe" -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
& ".venv\Scripts\python.exe" -m itsm.production_check
if ($LASTEXITCODE -ne 0) { throw "Production readiness checks failed." }

$worker = Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m","itsm.worker" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
$forwardedAllowIps = & ".venv\Scripts\python.exe" -c "from itsm.config import settings; print(settings.forwarded_allow_ips)"
Write-Host "Northstar Desk production process is starting."
try {
    & ".venv\Scripts\python.exe" -m uvicorn itsm.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips $forwardedAllowIps
} finally {
    Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue
}

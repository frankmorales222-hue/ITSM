$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed. Run scripts\install.ps1 first." }
if (-not (Test-Path "frontend\dist\index.html")) { throw "Interface build is missing. Run scripts\build.ps1." }

$appUrl = "http://127.0.0.1:8000"
$healthUrl = "$appUrl/api/health/ready"
$alreadyRunning = $false
try {
    $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
    $alreadyRunning = $health.status -eq "ready"
} catch {
    $alreadyRunning = $false
}

if ($alreadyRunning) {
    Write-Host "Northstar Desk is already running at $appUrl" -ForegroundColor Green
    Write-Host "Opening the existing application. A second server is not needed."
    Start-Process $appUrl
    exit 0
}

$portInUse = $false
$portCheck = [System.Net.Sockets.TcpClient]::new()
try {
    $connect = $portCheck.ConnectAsync("127.0.0.1", 8000)
    $portInUse = $connect.Wait(500) -and $portCheck.Connected
} catch {
    $portInUse = $false
} finally {
    $portCheck.Dispose()
}
if ($portInUse) {
    throw "Port 8000 is already in use by another program. If Northstar Desk is still starting, wait a few seconds and run Start ITSM.cmd again."
}

& ".venv\Scripts\python.exe" -m alembic upgrade head
$worker = Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m","itsm.worker" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
Write-Host "Northstar Desk starting at $appUrl"
Write-Host "Background worker PID: $($worker.Id). Press Ctrl+C to stop Northstar Desk."
try {
    & ".venv\Scripts\python.exe" -m uvicorn itsm.main:app --host 127.0.0.1 --port 8000
} finally {
    Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue
}

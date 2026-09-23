[CmdletBinding()]
param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"

# This launcher deliberately uses its own configuration, SQLite database,
# storage, worker, and port.  It never imports or opens the production .env.
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $projectRoot "data\local-test"
$testDatabase = Join-Path $testRoot "northstar-test.db"
$testConfig = Join-Path $testRoot ".env.local-test"
$testPort = 8010
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The local test environment needs the project virtual environment. Run scripts\\install.ps1 once first."
}

New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $testRoot "backups") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $testRoot "updates") -Force | Out-Null

if ($Reset -and (Test-Path -LiteralPath $testDatabase)) {
    Remove-Item -LiteralPath $testDatabase -Force
}
$newTestDatabase = -not (Test-Path -LiteralPath $testDatabase)

$configLines = @(
    'ITSM_DATABASE_URL=sqlite:///./data/local-test/northstar-test.db',
    'ITSM_DATA_DIRECTORY=data/local-test',
    'ITSM_BACKUP_DIRECTORY=data/local-test/backups',
    'ITSM_UPDATE_STAGING_DIRECTORY=data/local-test/updates',
    'ITSM_ENVIRONMENT=local-test',
    'ITSM_SECRET_KEY=local-test-only-not-for-production-2026',
    'ITSM_SESSION_MINUTES=120',
    'ITSM_COOKIE_SECURE=false',
    'ITSM_ALLOWED_ORIGINS=http://127.0.0.1:8010,http://localhost:8010',
    'ITSM_PUBLIC_URL=http://127.0.0.1:8010',
    'ITSM_TRUSTED_HOSTS=127.0.0.1,localhost,testserver',
    'ITSM_FORWARDED_ALLOW_IPS=127.0.0.1',
    'ITSM_BIND_HOST=127.0.0.1',
    'ITSM_PORT=8010',
    'ITSM_OUTBOUND_EMAIL_ENABLED=false',
    'ITSM_ASSETPILOT_ENABLED=false',
    'ITSM_MICROSOFT_CLIENT_ID=',
    'ITSM_MICROSOFT_CLIENT_SECRET=',
    'ITSM_RINGCENTRAL_CLIENT_ID=',
    'ITSM_RINGCENTRAL_CLIENT_SECRET='
)
Set-Content -LiteralPath $testConfig -Value $configLines -Encoding utf8

Set-Location $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
$env:ITSM_CONFIG_FILE = $testConfig

$listener = [System.Net.Sockets.TcpClient]::new()
try {
    $running = $listener.ConnectAsync("127.0.0.1", $testPort).Wait(300) -and $listener.Connected
} catch {
    $running = $false
} finally {
    $listener.Dispose()
}
if ($running) {
    Start-Process "http://127.0.0.1:$testPort"
    Write-Host "Northstar local test is already running at http://127.0.0.1:$testPort" -ForegroundColor Green
    exit 0
}

& $python -m alembic upgrade head
if ($newTestDatabase) {
    & $python -m itsm.seed
}

# Keep the local-only administrator deterministic. This runs against the
# isolated SQLite test database configured above and never reaches production.
& $python -c "from itsm.database import SessionLocal; from itsm.models import User; from itsm.security import hash_password; s=SessionLocal(); u=s.query(User).filter(User.username=='admin').one_or_none(); assert u is not None, 'Local test admin was not created'; u.password_hash=hash_password('ChangeMe!2026'); u.active=True; u.must_change_password=False; s.commit(); s.close()"

$worker = Start-Process -FilePath $python -ArgumentList "-m", "itsm.worker" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
Write-Host "Northstar LOCAL TEST is starting at http://127.0.0.1:$testPort" -ForegroundColor Cyan
Write-Host "Test sign-in: admin / ChangeMe!2026" -ForegroundColor Yellow
Write-Host "This uses data\\local-test only. Press Ctrl+C to stop it." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:$testPort"
try {
    & $python -m uvicorn itsm.main:app --host 127.0.0.1 --port $testPort
} finally {
    Stop-Process -Id $worker.Id -Force -ErrorAction SilentlyContinue
}

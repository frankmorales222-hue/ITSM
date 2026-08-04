$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.12 or later is required. Install it from python.org and enable Add Python to PATH." }
python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or later is required'"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Python package manager upgrade failed." }
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    Push-Location frontend
    try {
        pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        pnpm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location frontend
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } finally { Pop-Location }
} elseif (Test-Path "frontend\dist\index.html") {
    Write-Host "Node.js is not installed; using the verified prebuilt interface in frontend\dist."
} else {
    throw "Node.js 20 or later is required because no prebuilt interface was found. Install Node.js, then run this script again."
}
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
New-Item -ItemType Directory -Force -Path data,logs | Out-Null
$env:PYTHONPATH = Join-Path $projectRoot "backend"
& ".venv\Scripts\python.exe" -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Database migration failed." }
& ".venv\Scripts\python.exe" -m itsm.seed
if ($LASTEXITCODE -ne 0) { throw "Database seed failed." }
Write-Host "Installation complete. Run scripts\start.cmd, then open http://127.0.0.1:8000"

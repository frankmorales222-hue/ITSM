$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python 3.12 or later is required. Install it from python.org and enable Add Python to PATH." }
python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or later is required'"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js 20 or later is required to build the interface." }
Push-Location frontend
npm install
npm run build
Pop-Location
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
New-Item -ItemType Directory -Force -Path data,logs | Out-Null
$env:PYTHONPATH = Join-Path $projectRoot "backend"
& ".venv\Scripts\python.exe" -m alembic upgrade head
& ".venv\Scripts\python.exe" -m itsm.seed
Write-Host "Installation complete. Run scripts\start.ps1, then open http://127.0.0.1:8000"


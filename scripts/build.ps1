$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Application is not installed. Run scripts\install.cmd first."
}
Push-Location frontend
try {
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        pnpm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    } else {
        throw "Node.js 20 or later with npm or pnpm is required to rebuild the interface."
    }
} finally {
    Pop-Location
}

$env:PYTHONPATH = Join-Path $projectRoot "backend"
& ".venv\Scripts\python.exe" -m pytest
if ($LASTEXITCODE -ne 0) { throw "Automated tests failed." }
Write-Host "Build complete and automated tests passed."

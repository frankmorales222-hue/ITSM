$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "backend"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit","-Command","Set-Location '$projectRoot'; `$env:PYTHONPATH='$projectRoot\backend'; .venv\Scripts\python.exe -m uvicorn itsm.main:app --reload --host 127.0.0.1 --port 8000" -WorkingDirectory $projectRoot
Set-Location (Join-Path $projectRoot "frontend")
npm run dev


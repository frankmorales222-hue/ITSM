@echo off
set "NORTHSTAR_PORT=8000"
set "NORTHSTAR_URL="
for /f "tokens=1,* delims==" %%A in ('findstr /b "ITSM_PORT=" "%ProgramData%\NorthstarDesk\.env" 2^>nul') do set "NORTHSTAR_PORT=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /b "ITSM_PUBLIC_URL=" "%ProgramData%\NorthstarDesk\.env" 2^>nul') do set "NORTHSTAR_URL=%%B"
if not defined NORTHSTAR_URL set "NORTHSTAR_URL=http://127.0.0.1:%NORTHSTAR_PORT%"
powershell.exe -NoProfile -Command "try { $r=Invoke-RestMethod -Uri '%NORTHSTAR_URL%/api/health/ready' -TimeoutSec 2; if($r.status -ne 'ready'){exit 1} } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  schtasks.exe /Run /TN "Northstar Desk" >nul 2>&1
  timeout /t 2 /nobreak >nul
  powershell.exe -NoProfile -Command "try { $r=Invoke-RestMethod -Uri '%NORTHSTAR_URL%/api/health/ready' -TimeoutSec 2; if($r.status -ne 'ready'){exit 1} } catch { exit 1 }" >nul 2>&1
  if errorlevel 1 (
    powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Process -WindowStyle Hidden -FilePath '%~dp0NorthstarDeskServer.exe' -ArgumentList @('serve','--data-root','%ProgramData%\NorthstarDesk')"
    timeout /t 3 /nobreak >nul
  )
)
start "" "%NORTHSTAR_URL%"

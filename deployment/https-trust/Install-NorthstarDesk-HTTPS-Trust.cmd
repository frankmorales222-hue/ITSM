@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-NorthstarDesk-HTTPS-Trust.ps1"
if errorlevel 1 (
  echo.
  echo Northstar HTTPS trust installation failed.
  pause
  exit /b 1
)
echo.
echo Northstar HTTPS trust installation completed successfully.
pause


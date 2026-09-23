@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Create-Northstar-HTTPS-Trust-Package.ps1"
if errorlevel 1 (
  echo.
  echo Northstar HTTPS trust package creation failed.
  pause
  exit /b 1
)
echo.
echo Northstar HTTPS trust package created successfully.
pause


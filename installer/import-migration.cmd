@echo off
setlocal
set "APPDIR=%~dp0"
set "DATAROOT=%ProgramData%\NorthstarDesk"
if "%~1"=="" (
  set /p "PACKAGE=Enter the full path to NorthstarDesk-Migration.zip: "
) else (
  set "PACKAGE=%~1"
)
if not exist "%PACKAGE%" (
  echo Migration package not found: %PACKAGE%
  pause
  exit /b 2
)
"%SystemRoot%\System32\schtasks.exe" /End /TN "Northstar Desk" >nul 2>&1
"%SystemRoot%\System32\schtasks.exe" /End /TN "Northstar HTTPS" >nul 2>&1
"%APPDIR%NorthstarDeskServer.exe" import-migration --data-root "%DATAROOT%" --package "%PACKAGE%" --confirm IMPORT
if errorlevel 1 (
  echo Migration import failed. The pre-import backup is preserved.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%APPDIR%install-tasks.ps1"
echo.
echo Migration completed. Northstar Desk services were restarted.
pause
exit /b 0

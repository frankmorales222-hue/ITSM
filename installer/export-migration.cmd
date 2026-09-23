@echo off
setlocal
set "APPDIR=%~dp0"
set "DATAROOT=%ProgramData%\NorthstarDesk"
if "%~1"=="" (
  set "OUTPUT=%USERPROFILE%\Desktop\NorthstarDesk-Migration.zip"
) else (
  set "OUTPUT=%~1"
)
if "%~2"=="" (
  "%APPDIR%NorthstarDeskServer.exe" export-migration --data-root "%DATAROOT%" --output "%OUTPUT%"
) else (
  "%APPDIR%NorthstarDeskServer.exe" export-migration --data-root "%DATAROOT%" --output "%OUTPUT%" --backup-path "%~2"
)
if errorlevel 1 (
  echo Migration export failed.
  pause
  exit /b 1
)
echo.
echo Migration package created at:
echo %OUTPUT%
pause
exit /b 0

@echo off
if "%~1"=="" (
  echo Usage: install-pilot.cmd SERVER_URL [USER_EMAIL]
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-pilot.ps1" -ServerUrl "%~1" -UserEmail "%~2"

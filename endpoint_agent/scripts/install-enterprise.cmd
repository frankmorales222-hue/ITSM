@echo off
if "%~1"=="" (
  echo Usage: install-enterprise.cmd https://helpdesk.company.example [TOKEN_FILE]
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-enterprise.ps1" -ServerUrl "%~1" -EnrollmentTokenFile "%~2"


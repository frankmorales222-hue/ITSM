@echo off
title Northstar Desk Production
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-production.ps1"
if errorlevel 1 pause

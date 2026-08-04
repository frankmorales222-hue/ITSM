@echo off
title Northstar Desk Production Check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0production-check.ps1"
if errorlevel 1 pause

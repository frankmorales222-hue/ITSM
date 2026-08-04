@echo off
title Back Up Northstar Desk
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1"
if errorlevel 1 pause

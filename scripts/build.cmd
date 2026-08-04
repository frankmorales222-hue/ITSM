@echo off
title Build Northstar Desk
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
if errorlevel 1 pause

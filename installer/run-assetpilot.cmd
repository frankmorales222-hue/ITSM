@echo off
setlocal
set "ASPNETCORE_URLS=http://127.0.0.1:5080"
set "ASPNETCORE_ENVIRONMENT=Production"
if exist "%ProgramData%\NorthstarDesk\AssetPilot\assetpilot.env.cmd" call "%ProgramData%\NorthstarDesk\AssetPilot\assetpilot.env.cmd"
if not defined Database__Provider set "Database__Provider=Sqlite"
if not defined Database__Path set "Database__Path=%ProgramData%\NorthstarDesk\AssetPilot\Data\assetpilot.db"
if not defined Backup__Path set "Backup__Path=%ProgramData%\NorthstarDesk\AssetPilot\Backups"
if not defined Import__SeedExistingInventory set "Import__SeedExistingInventory=false"
if not defined Hosting__UseForwardedHeaders set "Hosting__UseForwardedHeaders=true"
if not exist "%ProgramData%\NorthstarDesk\AssetPilot\Data" mkdir "%ProgramData%\NorthstarDesk\AssetPilot\Data"
if not exist "%ProgramData%\NorthstarDesk\AssetPilot\Backups" mkdir "%ProgramData%\NorthstarDesk\AssetPilot\Backups"
"%~dp0AssetPilot\AssetPilot.exe" 1>>"%ProgramData%\NorthstarDesk\assetpilot.out.log" 2>>"%ProgramData%\NorthstarDesk\assetpilot.err.log"

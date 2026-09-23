$ErrorActionPreference = "Stop"
$source = "C:\Users\frank\Documents\ITSM\installer\dist\NorthstarDeskServer"
$destination = "C:\Program Files\Northstar Desk"
if (-not (Test-Path -LiteralPath (Join-Path $source "NorthstarDeskServer.exe"))) { throw "The updated server bundle is missing." }

& schtasks.exe /End /TN "Northstar Desk" 2>$null | Out-Null
Get-Process -Name "NorthstarDeskServer" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

& robocopy.exe $source $destination /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -gt 7) { throw "Northstar application files could not be updated (robocopy exit code $LASTEXITCODE)." }

& "C:\Users\frank\Documents\ITSM\scripts\configure-network-test.ps1" -LanAddress "10.0.0.201" -Port 8011

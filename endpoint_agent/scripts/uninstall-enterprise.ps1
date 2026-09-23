param(
    [switch]$PurgeData,
    [switch]$KeepInstallFiles,
    [string]$InstallRoot = "$env:ProgramFiles\Northstar Endpoint Agent",
    [string]$DataRoot = "$env:ProgramData\NorthstarEndpointAgent"
)
$ErrorActionPreference = "Stop"
$taskName = "Northstar Endpoint Agent"
$logonTaskName = "Northstar Endpoint Agent - User Logon Inventory"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
& $schtasks /End /TN $taskName 2>$null | Out-Null
& $schtasks /Delete /TN $taskName /F 2>$null | Out-Null
& $schtasks /End /TN $logonTaskName 2>$null | Out-Null
& $schtasks /Delete /TN $logonTaskName /F 2>$null | Out-Null
Get-Process -Name "NorthstarEndpointAgent" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "NorthstarEndpointTray" -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "Northstar Endpoint Tray" -ErrorAction SilentlyContinue
if (-not $KeepInstallFiles -and (Test-Path -LiteralPath $InstallRoot)) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
if ($PurgeData -and (Test-Path -LiteralPath $DataRoot)) { Remove-Item -LiteralPath $DataRoot -Recurse -Force }
Write-Host $(if($PurgeData){"Agent and local inventory removed."}else{"Agent removed; inventory data retained at $DataRoot."})

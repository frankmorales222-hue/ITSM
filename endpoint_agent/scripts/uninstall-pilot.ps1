$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "Northstar Endpoint Agent" -Confirm:$false -ErrorAction SilentlyContinue
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "Northstar Endpoint Agent.lnk"
Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*asset_agent*NorthstarEndpointAgent*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "Northstar Endpoint Agent startup task removed. Local inventory remains in $env:LOCALAPPDATA\NorthstarEndpointAgent."

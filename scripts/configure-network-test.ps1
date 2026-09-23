param(
    [string]$LanAddress = "",
    [int]$Port = 0,
    [switch]$RestoreLocalOnly
)
$ErrorActionPreference = "Stop"

$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($LanAddress) { $arguments += @("-LanAddress", $LanAddress) }
    if ($Port) { $arguments += @("-Port", $Port) }
    if ($RestoreLocalOnly) { $arguments += "-RestoreLocalOnly" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait
    exit
}

$dataRoot = Join-Path $env:ProgramData "NorthstarDesk"
$envPath = Join-Path $dataRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) { throw "Northstar Desk is not installed in $dataRoot." }
$script:lines = @(Get-Content -LiteralPath $envPath)

function Get-Setting([string]$Name) {
    $line = $script:lines | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if ($line) { return (($line -split "=",2)[1]).Trim('"') }
    return ""
}
function Set-Setting([string]$Name,[string]$Value) {
    $replacement = "$Name=$Value"
    $found = $false
    $script:lines = @($script:lines | ForEach-Object {
        if ($_ -match "^$([regex]::Escape($Name))=") { $found=$true; $replacement } else { $_ }
    })
    if (-not $found) { $script:lines += $replacement }
}

if (-not $Port) { $Port = [int](Get-Setting "ITSM_PORT") }
if (-not $Port) { $Port = 8011 }
if (-not $LanAddress -and -not $RestoreLocalOnly) {
    $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop | Sort-Object RouteMetric | Select-Object -First 1
    $LanAddress = (Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1 -ExpandProperty IPAddress)
}
if (-not $RestoreLocalOnly -and $LanAddress -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw "A valid LAN IPv4 address is required." }

$backup = "$envPath.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
Copy-Item -LiteralPath $envPath -Destination $backup -Force
Set-Setting "ITSM_OUTBOUND_EMAIL_ENABLED" "false"
if ($RestoreLocalOnly) {
    Set-Setting "ITSM_PUBLIC_URL" "http://127.0.0.1:$Port"
    Set-Setting "ITSM_ALLOWED_ORIGINS" "http://127.0.0.1:$Port,http://localhost:$Port"
    Set-Setting "ITSM_TRUSTED_HOSTS" "127.0.0.1,localhost"
    Set-Setting "ITSM_BIND_HOST" "127.0.0.1"
} else {
    Set-Setting "ITSM_PUBLIC_URL" "http://${LanAddress}:$Port"
    Set-Setting "ITSM_ALLOWED_ORIGINS" "http://${LanAddress}:$Port,http://127.0.0.1:$Port,http://localhost:$Port"
    Set-Setting "ITSM_TRUSTED_HOSTS" "$LanAddress,127.0.0.1,localhost"
    Set-Setting "ITSM_BIND_HOST" "0.0.0.0"
}
$script:lines | Set-Content -LiteralPath $envPath -Encoding UTF8

$ruleName = "Northstar Desk Network Test"
Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
if (-not $RestoreLocalOnly) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP `
        -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
}

& schtasks.exe /End /TN "Northstar Desk" 2>$null | Out-Null
Get-Process -Name "NorthstarDeskServer" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
& schtasks.exe /Run /TN "Northstar Desk" | Out-Null

$url = if ($RestoreLocalOnly) { "http://127.0.0.1:$Port" } else { "http://${LanAddress}:$Port" }
Write-Host "Northstar Desk is restarting at $url" -ForegroundColor Green
Write-Host "Outbound email remains disabled. Configuration backup: $backup"
if (-not $RestoreLocalOnly) {
    Write-Warning "Temporary LAN test mode uses HTTP. Use test accounts only. Microsoft SSO and remote endpoint agents require trusted HTTPS."
}
Start-Sleep -Seconds 4
Start-Process $url

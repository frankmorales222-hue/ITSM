[CmdletBinding()]
param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$logRoot = Join-Path $env:LOCALAPPDATA "NorthstarEndpointAgent"
$logPath = Join-Path $logRoot "tray-launch.log"
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
function Write-TrayLaunchLog([string]$Message) {
    Add-Content -LiteralPath $logPath -Value "$(Get-Date -Format o) $Message" -Encoding UTF8
}
$configPath = Join-Path $PSScriptRoot "tray-config.json"
$tray = Join-Path $PSScriptRoot "NorthstarEndpointTray\NorthstarEndpointTray.exe"
$runtimePath = Join-Path $logRoot "tray-runtime.json"
if (-not (Test-Path -LiteralPath $configPath) -or -not (Test-Path -LiteralPath $tray)) {
    Write-TrayLaunchLog "Startup aborted: tray executable or non-secret tray configuration is missing."
    # A desktop companion problem must never change the result of an otherwise
    # successful machine agent installation. Startup and refresh can retry.
    exit 0
}

try { $serverUrl = [string]((Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).server_url) }
catch { Write-TrayLaunchLog "Startup aborted: tray configuration is invalid."; exit 0 }
if (-not $serverUrl) { Write-TrayLaunchLog "Startup aborted: Help Desk URL is missing."; exit 0 }

$sessionId = (Get-Process -Id $PID).SessionId
$trayFullPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $tray).Path)
$alreadyRunning = @(Get-Process -Name "NorthstarEndpointTray" -ErrorAction SilentlyContinue |
    Where-Object { $_.SessionId -eq $sessionId }
)
if ($Restart -and $alreadyRunning.Count -gt 0) {
    Write-TrayLaunchLog "Restart requested: stopping $($alreadyRunning.Count) existing tray process(es) in session $sessionId."
    $alreadyRunning | Stop-Process -Force -ErrorAction Stop
    $deadline = (Get-Date).AddSeconds(12)
    do {
        Start-Sleep -Milliseconds 250
        $alreadyRunning = @(Get-Process -Name "NorthstarEndpointTray" -ErrorAction SilentlyContinue |
            Where-Object { $_.SessionId -eq $sessionId })
    } while ($alreadyRunning.Count -gt 0 -and (Get-Date) -lt $deadline)
    if ($alreadyRunning.Count -gt 0) {
        Write-TrayLaunchLog "Restart failed: an older tray executable is still running in session $sessionId."
        exit 1
    }
}
if ($Restart) {
    # This marker is created only after the new tray executable has registered
    # its notification icon. Removing an old marker prevents a successful
    # upgrade from being reported while Windows is still showing an old tray.
    Remove-Item -LiteralPath $runtimePath -Force -ErrorAction SilentlyContinue
}
if ($alreadyRunning.Count -eq 0) {
    try {
        $process = Start-Process -FilePath $tray -ArgumentList @("--server", $serverUrl.TrimEnd('/')) -PassThru
        # The Windows notification area may display a new icon several seconds after
        # the tray process starts. Do not treat that normal delay as a failed install.
        Write-TrayLaunchLog "Tray companion launch requested from '$tray' in session $sessionId with PID $($process.Id)."
    } catch {
        Write-TrayLaunchLog "Tray process failed to start: $($_.Exception.Message)"
        exit 0
    }

    if ($Restart) {
        $deadline = (Get-Date).AddSeconds(15)
        $verified = $false
        do {
            Start-Sleep -Milliseconds 250
            try {
                $runtime = Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
                $runtimePid = [int]$runtime.pid
                $runtimeExecutable = [System.IO.Path]::GetFullPath([string]$runtime.executable)
                if ($runtimePid -eq $process.Id -and
                    $runtimeExecutable -ieq $trayFullPath -and
                    [bool]$runtime.tray_menu_test_notification) {
                    $verified = $true
                    break
                }
            } catch {
                # The tray has not registered its icon and runtime marker yet.
            }
        } while ((Get-Date) -lt $deadline)

        if (-not $verified) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Write-TrayLaunchLog "Restart failed: the new tray executable did not register a verified runtime marker."
            exit 1
        }
        Write-TrayLaunchLog "Tray runtime verified from '$trayFullPath' with Test notification support."
    }
} else {
    Write-TrayLaunchLog "Tray process is already running in session $sessionId."
}
exit 0

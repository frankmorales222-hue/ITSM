$ErrorActionPreference = "SilentlyContinue"
$taskNames = @("Northstar Endpoint Agent", "Northstar Endpoint Agent - User Logon Inventory")
$processNames = @("NorthstarEndpointAgent", "NorthstarEndpointTray")
$diagnostic = Join-Path $env:ProgramData "NorthstarEndpointAgent-stop-error.log"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
Remove-Item -LiteralPath $diagnostic -Force -ErrorAction SilentlyContinue

# Keep the interactive-startup registration intact. The tray is stopped below
# only so its executable can be replaced. Removing this registration during an
# update caused a failed repair to leave the user without a tray companion.

# Future versions may use a Windows service instead of a scheduled task. This
# makes the same installer safely upgrade either deployment model.
Get-Service -Name "NorthstarEndpointAgent" -ErrorAction SilentlyContinue |
    Stop-Service -Force -ErrorAction SilentlyContinue

# Stop the current run without disabling the registered tasks.  A normal
# upgrade preserves the existing machine enrollment and task definitions, then
# starts the same task after replacing only the agent binaries.  Disabling the
# task here made a later repair failure leave a previously healthy agent down.
foreach ($taskName in $taskNames) {
    & $schtasks /End /TN $taskName 2>$null | Out-Null
}

# taskkill is more reliable than Stop-Process across Windows sessions. Keep the
# PowerShell fallback for machines where taskkill returns before process exit.
foreach ($processName in $processNames) {
    & taskkill.exe /F /T /IM "$processName.exe" 2>$null | Out-Null
}
Get-Process -Name $processNames -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

# Terminate cross-session instances that aren't visible to the interactive
# process provider on older Windows Server builds.
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in @("NorthstarEndpointAgent.exe", "NorthstarEndpointTray.exe") } |
    ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null }

$deadline = (Get-Date).AddSeconds(30)
do {
    $running = Get-Process -Name $processNames -ErrorAction SilentlyContinue
    if (-not $running) { exit 0 }
    foreach ($processName in $processNames) {
        & taskkill.exe /F /T /IM "$processName.exe" 2>$null | Out-Null
    }
    Start-Sleep -Milliseconds 250
} while ((Get-Date) -lt $deadline)

$details = $running | Select-Object ProcessName, Id, SessionId, Path | Format-List | Out-String
Set-Content -LiteralPath $diagnostic -Value $details -Encoding UTF8
Write-Error "Northstar Endpoint Agent is still running. Diagnostic: $diagnostic"
exit 1

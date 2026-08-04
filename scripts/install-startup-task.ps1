param(
    [string]$TaskName = "Northstar Desk",
    [switch]$AtStartup,
    [PSCredential]$Credential
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $PSScriptRoot "start-production.ps1"
if (-not (Test-Path $launcher)) { throw "Production launcher was not found." }

$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)

if ($AtStartup) {
    if (-not $Credential) { $Credential = Get-Credential -Message "Enter the dedicated Windows service account for Northstar Desk" }
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $password = $Credential.GetNetworkCredential().Password
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -User $Credential.UserName -Password $password -RunLevel Highest -Force | Out-Null
    Write-Host "Startup task '$TaskName' installed for $($Credential.UserName)."
} else {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
        -User $identity -RunLevel Highest -Force | Out-Null
    Write-Host "Logon task '$TaskName' installed for $identity."
}
Write-Host "Run scripts\production-check.cmd before starting the task."

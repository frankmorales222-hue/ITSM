$ErrorActionPreference = "Stop"
$applicationRoot = $PSScriptRoot
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable `
    -MultipleInstances IgnoreNew

$tasks = @(
    @{ Name = "Northstar Desk"; Script = "run-northstar.cmd" },
    @{ Name = "Northstar HTTPS"; Script = "run-caddy.cmd" }
)
foreach ($task in $tasks) {
    $scriptPath = Join-Path $applicationRoot $task.Script
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Scheduled task launcher is missing: $scriptPath"
    }
    $action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/d /c `"$scriptPath`"" `
        -WorkingDirectory $applicationRoot
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $task.Name
}

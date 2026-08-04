param([string]$TaskName = "Northstar Desk")
$ErrorActionPreference = "Stop"
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Scheduled task '$TaskName' removed. Application data was not changed."
} else {
    Write-Host "Scheduled task '$TaskName' is not installed."
}

[CmdletBinding()]
param(
    [string]$TaskName = "Northstar Endpoint Tray Launcher",
    [string]$InstallRoot = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
trap {
    Write-Error (($_ | Out-String).Trim())
    exit 1
}
$launcher = Join-Path $InstallRoot "launch-tray.ps1"
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "The Northstar tray launcher was not found: $launcher"
}

$powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
$commandXml = [Security.SecurityElement]::Escape($powerShell)
$argumentsXml = [Security.SecurityElement]::Escape($arguments)
$workingDirectoryXml = [Security.SecurityElement]::Escape($InstallRoot)
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>Northstar Desk</Author><Description>Launches the Northstar Endpoint tray for signed-in users after install or update.</Description></RegistrationInfo>
  <Triggers />
  <Principals><Principal id="Users"><GroupId>S-1-5-32-545</GroupId><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>false</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden><RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT1M</ExecutionTimeLimit><Priority>7</Priority></Settings>
  <Actions Context="Users"><Exec><Command>$commandXml</Command><Arguments>$argumentsXml</Arguments><WorkingDirectory>$workingDirectoryXml</WorkingDirectory></Exec></Actions>
</Task>
"@

# No trigger is registered intentionally. Setup invokes this group-principal
# task on demand, which starts the tray in signed-in BUILTIN\Users sessions.
# The Common Startup shortcut remains responsible for future sign-ins.
$xmlPath = Join-Path $env:TEMP "northstar-tray-launcher-$PID.xml"
try {
    Set-Content -LiteralPath $xmlPath -Value $taskXml -Encoding Unicode
    $schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $schtasks /Create /TN $TaskName /XML $xmlPath /F 2>&1
        $createExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($createExitCode -ne 0) {
        throw "Could not register '$TaskName' (exit code $createExitCode): $($output -join ' ')"
    }
    try {
        $ErrorActionPreference = "Continue"
        $registeredText = (& $schtasks /Query /TN $TaskName /XML 2>&1) -join "`n"
        $queryExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($queryExitCode -ne 0) {
        throw "The Northstar tray launcher task could not be queried after registration (exit code $queryExitCode)."
    }
    [xml]$registered = $registeredText
    $namespace = New-Object Xml.XmlNamespaceManager($registered.NameTable)
    $namespace.AddNamespace("t", $registered.DocumentElement.NamespaceURI)
    $principal = $registered.SelectSingleNode("/t:Task/t:Principals/t:Principal", $namespace)
    $groupText = [string]$principal.GroupId
    try {
        $groupSid = (New-Object Security.Principal.NTAccount($groupText)).Translate([Security.Principal.SecurityIdentifier]).Value
    } catch {
        try { $groupSid = (New-Object Security.Principal.SecurityIdentifier($groupText)).Value }
        catch { $groupSid = "" }
    }
    $runLevel = [string]$principal.RunLevel
    $logonType = $principal.SelectSingleNode("t:LogonType", $namespace)
    if (-not $principal -or $groupSid -ne "S-1-5-32-545" -or
        $logonType -or ($runLevel -and $runLevel -ne "LeastPrivilege")) {
        throw "The Northstar tray launcher task principal was not registered safely."
    }
} finally {
    Remove-Item -LiteralPath $xmlPath -Force -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE = 0
exit 0

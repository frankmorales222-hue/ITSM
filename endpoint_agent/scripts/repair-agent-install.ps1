[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\Northstar Endpoint Agent",
    [string]$DataRoot = "$env:ProgramData\NorthstarEndpointAgent",
    [Parameter(Mandatory=$true)][string]$ServerUrl,
    [string]$CurrentExecutable = ""
)

$ErrorActionPreference = "Stop"
trap {
    Write-Error (($_ | Out-String).Trim())
    exit 1
}
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
$powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not $CurrentExecutable) { $CurrentExecutable = Join-Path $InstallRoot "NorthstarEndpointAgent.exe" }
$CurrentExecutable = [IO.Path]::GetFullPath($CurrentExecutable)
$changes = New-Object Collections.Generic.List[string]

function Get-TaskXml([string]$Name) {
    $oldPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $text = (& $schtasks /Query /TN $Name /XML 2>$null | Out-String)
        if ($LASTEXITCODE -ne 0) {
            $global:LASTEXITCODE = 0
            return $null
        }
        return [xml]$text
    } finally { $ErrorActionPreference = $oldPreference }
}

function Ensure-AgentTask([string]$Name, [string]$TriggerXml, [string]$Arguments, [bool]$Watchdog = $false) {
    $existing = Get-TaskXml $Name
    $correct = $false
    if ($existing) {
        $ns = New-Object Xml.XmlNamespaceManager($existing.NameTable)
        $ns.AddNamespace("t", $existing.DocumentElement.NamespaceURI)
        $commandNode = $existing.SelectSingleNode("/t:Task/t:Actions/t:Exec/t:Command", $ns)
        $command = if ($commandNode) { [string]$commandNode.InnerText } else { "" }
        if ($command) {
            $expanded = [Environment]::ExpandEnvironmentVariables($command).Trim('"')
            $correct = [IO.Path]::GetFullPath($expanded) -ieq $CurrentExecutable
            if ($correct -and $Watchdog) {
                $restartInterval = $existing.SelectSingleNode("/t:Task/t:Settings/t:RestartOnFailure/t:Interval", $ns)
                $restartCount = $existing.SelectSingleNode("/t:Task/t:Settings/t:RestartOnFailure/t:Count", $ns)
                $repetition = $existing.SelectSingleNode("/t:Task/t:Triggers/t:TimeTrigger/t:Repetition/t:Interval", $ns)
                $correct = $restartInterval -and $restartInterval.InnerText -eq "PT1M" -and `
                    $restartCount -and $restartCount.InnerText -eq "999" -and `
                    $repetition -and $repetition.InnerText -eq "PT5M"
            }
        }
    }
    if ($correct) { return }
    $commandXml = [Security.SecurityElement]::Escape($CurrentExecutable)
    $argumentsXml = [Security.SecurityElement]::Escape($Arguments)
    $watchdogSettings = if ($Watchdog) { '<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>' } else { '' }
    $xmlText = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><RegistrationInfo><Author>Northstar Desk</Author></RegistrationInfo><Triggers>$TriggerXml</Triggers><Principals><Principal id="System"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><ExecutionTimeLimit>PT0S</ExecutionTimeLimit>$watchdogSettings</Settings><Actions Context="System"><Exec><Command>$commandXml</Command><Arguments>$argumentsXml</Arguments></Exec></Actions></Task>
"@
    $path = Join-Path $env:TEMP ("northstar-repair-" + [guid]::NewGuid().ToString("N") + ".xml")
    try {
        Set-Content -LiteralPath $path -Value $xmlText -Encoding Unicode
        $output = & $schtasks /Create /TN $Name /XML $path /F 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Could not repair task '$Name': $($output -join ' ')" }
    } finally { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    $changes.Add("Repaired scheduled task: $Name")
}

$escapedDataRoot = $DataRoot.Replace('"', '\"')
$watchdogStart = (Get-Date).AddMinutes(5).ToString("s")
$agentTriggers = '<BootTrigger><Enabled>true</Enabled></BootTrigger><TimeTrigger><Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>' + $watchdogStart + '</StartBoundary><Enabled>true</Enabled></TimeTrigger>'
Ensure-AgentTask "Northstar Endpoint Agent" $agentTriggers ('--data-dir "' + $escapedDataRoot + '"') $true
Ensure-AgentTask "Northstar Endpoint Agent - User Logon Inventory" '<LogonTrigger><Enabled>true</Enabled></LogonTrigger>' ('--data-dir "' + $escapedDataRoot + '" --once')

$trayConfig = Join-Path $InstallRoot "tray-config.json"
$wantedTrayConfig = @{ server_url = $ServerUrl.TrimEnd('/') } | ConvertTo-Json
$writeTrayConfig = -not (Test-Path -LiteralPath $trayConfig)
if (-not $writeTrayConfig) {
    try { $writeTrayConfig = [string]((Get-Content -LiteralPath $trayConfig -Raw | ConvertFrom-Json).server_url) -ne $ServerUrl.TrimEnd('/') }
    catch { $writeTrayConfig = $true }
}
if ($writeTrayConfig) {
    $wantedTrayConfig | Set-Content -LiteralPath $trayConfig -Encoding UTF8
    $changes.Add("Recreated tray-config.json")
}

$launcher = Join-Path $InstallRoot "launch-tray.ps1"
$startup = Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::CommonStartup)) "Northstar Endpoint Agent.lnk"
$shortcutCorrect = $false
if (Test-Path -LiteralPath $startup) {
    try {
        $existingShortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($startup)
        $shortcutCorrect = $existingShortcut.TargetPath -ieq $powerShell -and $existingShortcut.Arguments -like "*$launcher*"
    } catch { $shortcutCorrect = $false }
}
if (-not $shortcutCorrect) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($startup)
    $shortcut.TargetPath = $powerShell
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcher + '"'
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.IconLocation = (Join-Path $InstallRoot "northstar.ico") + ",0"
    $shortcut.Save()
    $changes.Add("Repaired Common Startup shortcut")
}

$migration = Join-Path $InstallRoot "migrate-legacy-x86-install.ps1"
if (Test-Path -LiteralPath $migration) {
    $legacyRoot = "${env:ProgramFiles(x86)}\Northstar Endpoint Agent"
    $hadLegacyInstall = Test-Path -LiteralPath $legacyRoot
    $migrationArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $migration)
    if ($InstallRoot) { $migrationArguments += @("-InstallRoot", $InstallRoot) }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $migrationOutput = & $powerShell @migrationArguments 2>&1
        $migrationExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($migrationExitCode -ne 0) {
        throw "Legacy installation migration failed (exit code $migrationExitCode): $($migrationOutput -join ' ')"
    }
    if ($hadLegacyInstall -and -not (Test-Path -LiteralPath $legacyRoot)) {
        $changes.Add("Removed legacy 32-bit installation")
    }
}

try {
    $trayInstaller = Join-Path $InstallRoot "install-tray-launcher-task.ps1"
    $trayArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $trayInstaller)
    if ($InstallRoot) { $trayArguments += @("-InstallRoot", $InstallRoot) }
    $trayPreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $trayOutput = & $powerShell @trayArguments 2>&1
        $trayExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $trayPreviousPreference
    }
    if ($trayExitCode -ne 0) { throw "The tray launcher task could not be registered (exit code $trayExitCode): $($trayOutput -join ' ')" }
    $trayState = Join-Path $DataRoot "tray-launch-state.json"
    $lastAttempt = [datetime]::MinValue
    if (Test-Path -LiteralPath $trayState) {
        try { $lastAttempt = [datetime]::Parse([string]((Get-Content -LiteralPath $trayState -Raw | ConvertFrom-Json).attempted_at)).ToUniversalTime() } catch {}
    }
    if (([datetime]::UtcNow - $lastAttempt).TotalHours -ge 1) {
        & $schtasks /Run /TN "Northstar Endpoint Tray Launcher" | Out-Null
        @{ attempted_at = [datetime]::UtcNow.ToString("o") } | ConvertTo-Json | Set-Content -LiteralPath $trayState -Encoding UTF8
    }
} catch {
    $changes.Add("Tray launcher repair warning: $($_.Exception.Message)")
    $global:LASTEXITCODE = 0
}

if ($changes.Count -eq 0) { Write-Output "Installation healthy; no changes required." }
else { $changes | ForEach-Object { Write-Output $_ } }
$global:LASTEXITCODE = 0
exit 0

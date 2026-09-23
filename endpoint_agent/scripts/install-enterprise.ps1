param(
    [Parameter(Mandatory=$true)][ValidateScript({ $_ -match '^https://' -or $_ -match '^http://(localhost|127\.0\.0\.1)(:\d+)?/?$' })][string]$ServerUrl,
    [string]$EnrollmentToken = "",
    [string]$EnrollmentTokenFile = "",
    [string]$UserEmail = "",
    [string]$TlsCertificateSha256 = "",
    [string]$InstallRoot = "$env:ProgramFiles\Northstar Endpoint Agent",
    [string]$DataRoot = "$env:ProgramData\NorthstarEndpointAgent",
    [string]$AgentExecutable = ""
)
$ErrorActionPreference = "Stop"
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated administrator session or a device-management system context."
}
$taskName = "Northstar Endpoint Agent"
$logonTaskName = "Northstar Endpoint Agent - User Logon Inventory"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
$installLog = Join-Path $DataRoot "install-error.log"
$packagedExecutable = Join-Path $PSScriptRoot "NorthstarEndpointAgent.exe"
$packagedTrayDirectory = Join-Path $PSScriptRoot "NorthstarEndpointTray"
$packagedTrayExecutable = Join-Path $packagedTrayDirectory "NorthstarEndpointTray.exe"
$sourceExecutable = if ($AgentExecutable) { $AgentExecutable } elseif (Test-Path -LiteralPath $packagedExecutable) { $packagedExecutable } else { Join-Path (Split-Path -Parent $PSScriptRoot) "dist\NorthstarEndpointAgent.exe" }
if (-not (Test-Path -LiteralPath $sourceExecutable)) {
    throw "NorthstarEndpointAgent.exe was not found. Build the enterprise package first."
}
if (-not (Test-Path -LiteralPath $packagedTrayExecutable)) {
    throw "NorthstarEndpointTray runtime was not found. Build the enterprise package first."
}
New-Item -ItemType Directory -Force -Path $InstallRoot,$DataRoot | Out-Null
& icacls.exe $InstallRoot /inheritance:r /grant:r "SYSTEM:(OI)(CI)(F)" "Administrators:(OI)(CI)(F)" "Users:(OI)(CI)(RX)" | Out-Null
& icacls.exe $DataRoot /inheritance:r /grant:r "SYSTEM:(OI)(CI)(F)" "Administrators:(OI)(CI)(F)" | Out-Null
# The service keeps credentials in $DataRoot. The tray receives only this
# separate, non-secret signal directory.
$traySignalRoot = Join-Path $DataRoot "tray"
New-Item -ItemType Directory -Force -Path $traySignalRoot | Out-Null
# The tray companion runs as the signed-in user and needs to create only the
# non-secret refresh.request signal. Credentials remain protected at $DataRoot.
& icacls.exe $traySignalRoot /inheritance:r /grant:r "SYSTEM:(OI)(CI)(F)" "Administrators:(OI)(CI)(F)" "Users:(OI)(CI)(M)" | Out-Null
$targetExecutable = Join-Path $InstallRoot "NorthstarEndpointAgent.exe"
$targetTrayDirectory = Join-Path $InstallRoot "NorthstarEndpointTray"
$targetTrayExecutable = Join-Path $targetTrayDirectory "NorthstarEndpointTray.exe"
$trayConfigPath = Join-Path $InstallRoot "tray-config.json"

# A clean installation has no existing scheduled tasks. schtasks writes that
# normal "not found" result to stderr; with ErrorActionPreference=Stop,
# PowerShell converts it into a terminating NativeCommandError. Stop old tasks
# best-effort so clean installs and repairs both follow the same path.
function Stop-NorthstarTaskIfPresent {
    param([Parameter(Mandatory=$true)][string]$Name)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $schtasks /End /TN $Name *> $null
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}
Stop-NorthstarTaskIfPresent -Name $taskName
Stop-NorthstarTaskIfPresent -Name $logonTaskName
Get-Process -Name "NorthstarEndpointAgent" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process -Name "NorthstarEndpointTray" -ErrorAction SilentlyContinue | Stop-Process -Force
if ((Resolve-Path -LiteralPath $sourceExecutable).Path -ne [IO.Path]::GetFullPath($targetExecutable)) {
    Copy-Item -LiteralPath $sourceExecutable -Destination $targetExecutable -Force
}
if ((Resolve-Path -LiteralPath $packagedTrayDirectory).Path -ne [IO.Path]::GetFullPath($targetTrayDirectory)) {
    Remove-Item -LiteralPath $targetTrayDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $packagedTrayDirectory -Destination $targetTrayDirectory -Recurse -Force
}

$configPath = Join-Path $DataRoot "config.json"
if (-not (Test-Path -LiteralPath $configPath)) {
    if ($EnrollmentTokenFile) {
        $EnrollmentToken = (Get-Content -LiteralPath $EnrollmentTokenFile -Raw).Trim()
    } elseif (-not $EnrollmentToken -and $env:NORTHSTAR_ENROLLMENT_TOKEN) {
        $EnrollmentToken = $env:NORTHSTAR_ENROLLMENT_TOKEN
    }
    if (-not $EnrollmentToken) { throw "First installation requires -EnrollmentTokenFile or NORTHSTAR_ENROLLMENT_TOKEN." }
    $temporaryToken = Join-Path $DataRoot "enrollment.token"
    try {
        Set-Content -LiteralPath $temporaryToken -Value $EnrollmentToken -NoNewline -Encoding ascii
        & icacls.exe $temporaryToken /inheritance:r /grant:r "SYSTEM:(F)" "Administrators:(F)" | Out-Null
        $arguments = @("--data-dir",$DataRoot,"--server",$ServerUrl,"--credential-scope","machine","--enrollment-token-file",$temporaryToken,"--once")
        if ($TlsCertificateSha256) { $arguments += @("--tls-pin",$TlsCertificateSha256) }
        if ($UserEmail) { $arguments += @("--user-email",$UserEmail) }
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $agentOutput = & $targetExecutable @arguments 2>&1
        $agentExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousPreference
    } finally {
        Remove-Item -LiteralPath $temporaryToken -Force -ErrorAction SilentlyContinue
    }
    $EnrollmentToken = $null
    if ($agentExitCode -ne 0 -or -not (Test-Path -LiteralPath $configPath)) {
        $agentLog = Join-Path $DataRoot "agent.log"
        @(
            "Endpoint enrollment or first inventory failed (exit code $agentExitCode)."
            ($agentOutput | Out-String)
            $(if (Test-Path -LiteralPath $agentLog) { Get-Content -LiteralPath $agentLog -Tail 40 | Out-String })
        ) | Set-Content -LiteralPath $installLog -Encoding UTF8
        throw "Endpoint enrollment or first inventory failed. Diagnostic: $installLog"
    }
} else {
    # A repair/update must never be marked failed merely because the optional
    # immediate inventory check cannot reach the Help Desk yet.  The existing
    # machine-scoped enrollment is preserved and the scheduled agent performs
    # the next inventory cycle after Setup exits.
    Write-Host "Existing Northstar enrollment preserved; inventory will resume in the background."
}

@{ server_url = $ServerUrl.TrimEnd('/') } | ConvertTo-Json |
    Set-Content -LiteralPath $trayConfigPath -Encoding UTF8
# The per-user Startup shortcut installed by Inno is the sole tray launcher.
# Remove the legacy machine-wide Run value so it cannot race the new launcher
# or keep an older executable alive after an upgrade.
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "Northstar Endpoint Tray" -ErrorAction SilentlyContinue

function Register-NorthstarTask {
    param([string]$Name, [string]$TriggerXml, [string]$Arguments, [string]$XmlPath)
    $commandXml = [Security.SecurityElement]::Escape($targetExecutable)
    $argumentsXml = [Security.SecurityElement]::Escape($Arguments)
    $taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Author>Northstar Desk</Author></RegistrationInfo>
  <Triggers>$TriggerXml</Triggers>
  <Principals><Principal id="System"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden><RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>7</Priority></Settings>
  <Actions Context="System"><Exec><Command>$commandXml</Command><Arguments>$argumentsXml</Arguments></Exec></Actions>
</Task>
"@
    Set-Content -LiteralPath $XmlPath -Value $taskXml -Encoding Unicode
    $taskOutput = & $schtasks /Create /TN $Name /XML $XmlPath /F 2>&1
    $taskExitCode = $LASTEXITCODE
    Remove-Item -LiteralPath $XmlPath -Force -ErrorAction SilentlyContinue
    if ($taskExitCode -ne 0) { throw "Could not register '$Name' (exit code $taskExitCode): $($taskOutput -join ' ')" }
}

$escapedDataRoot = $DataRoot.Replace('"', '\"')
Register-NorthstarTask -Name $taskName -TriggerXml '<BootTrigger><Enabled>true</Enabled></BootTrigger>' `
    -Arguments ('--data-dir "' + $escapedDataRoot + '"') -XmlPath (Join-Path $env:TEMP "northstar-startup-task.xml")
Register-NorthstarTask -Name $logonTaskName -TriggerXml '<LogonTrigger><Enabled>true</Enabled></LogonTrigger>' `
    -Arguments ('--data-dir "' + $escapedDataRoot + '" --once') -XmlPath (Join-Path $env:TEMP "northstar-logon-task.xml")
& $schtasks /Run /TN $taskName | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Northstar was installed but its startup task could not be started." }
Write-Host "Northstar Endpoint Agent installed for all users and reporting to $ServerUrl"
Write-Host "The tray companion will start automatically in each user session. Existing sessions receive it at the next sign-in."

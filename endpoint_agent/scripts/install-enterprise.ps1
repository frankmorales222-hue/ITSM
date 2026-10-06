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
$errorLog = Join-Path $env:ProgramData "NorthstarEndpointAgent-install-error.log"
$warningLog = Join-Path $env:ProgramData "NorthstarEndpointAgent-install-warning.log"
Remove-Item -LiteralPath $errorLog,$warningLog -Force -ErrorAction SilentlyContinue
trap {
    $details = ($_ | Out-String).Trim()
    Set-Content -LiteralPath $errorLog -Value $details -Encoding UTF8
    Write-Error $details
    exit 1
}
function Write-InstallWarning([string]$Message) {
    Add-Content -LiteralPath $warningLog -Value $Message -Encoding UTF8
    Write-Warning $Message
}
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated administrator session or a device-management system context."
}
$taskName = "Northstar Endpoint Agent"
$logonTaskName = "Northstar Endpoint Agent - User Logon Inventory"
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
$packagedExecutable = Join-Path $PSScriptRoot "NorthstarEndpointAgent.exe"
$packagedTrayDirectory = Join-Path $PSScriptRoot "NorthstarEndpointTray"
$packagedTrayExecutable = Join-Path $packagedTrayDirectory "NorthstarEndpointTray.exe"
$packagedTrayLauncher = Join-Path $PSScriptRoot "launch-tray.ps1"
$packagedTrayTaskInstaller = Join-Path $PSScriptRoot "install-tray-launcher-task.ps1"
$packagedLegacyMigration = Join-Path $PSScriptRoot "migrate-legacy-x86-install.ps1"
$packagedRepair = Join-Path $PSScriptRoot "repair-agent-install.ps1"
$packagedIcon = Join-Path $PSScriptRoot "northstar.ico"
$sourceExecutable = if ($AgentExecutable) { $AgentExecutable } elseif (Test-Path -LiteralPath $packagedExecutable) { $packagedExecutable } else { Join-Path (Split-Path -Parent $PSScriptRoot) "dist\NorthstarEndpointAgent.exe" }
if (-not (Test-Path -LiteralPath $sourceExecutable)) {
    throw "NorthstarEndpointAgent.exe was not found. Build the enterprise package first."
}
if (-not (Test-Path -LiteralPath $packagedTrayExecutable)) {
    throw "NorthstarEndpointTray runtime was not found. Build the enterprise package first."
}
if (-not (Test-Path -LiteralPath $packagedTrayLauncher) -or
    -not (Test-Path -LiteralPath $packagedTrayTaskInstaller) -or
    -not (Test-Path -LiteralPath $packagedLegacyMigration) -or
    -not (Test-Path -LiteralPath $packagedRepair) -or
    -not (Test-Path -LiteralPath $packagedIcon)) {
    throw "Northstar tray launcher installation scripts were not found."
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
$targetTrayLauncher = Join-Path $InstallRoot "launch-tray.ps1"
$targetTrayTaskInstaller = Join-Path $InstallRoot "install-tray-launcher-task.ps1"
$targetLegacyMigration = Join-Path $InstallRoot "migrate-legacy-x86-install.ps1"
$targetRepair = Join-Path $InstallRoot "repair-agent-install.ps1"
$targetIcon = Join-Path $InstallRoot "northstar.ico"

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
        $global:LASTEXITCODE = 0
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
if ((Resolve-Path -LiteralPath $packagedTrayLauncher).Path -ne [IO.Path]::GetFullPath($targetTrayLauncher)) {
    Copy-Item -LiteralPath $packagedTrayLauncher -Destination $targetTrayLauncher -Force
}
if ((Resolve-Path -LiteralPath $packagedTrayTaskInstaller).Path -ne [IO.Path]::GetFullPath($targetTrayTaskInstaller)) {
    Copy-Item -LiteralPath $packagedTrayTaskInstaller -Destination $targetTrayTaskInstaller -Force
}
if ((Resolve-Path -LiteralPath $packagedLegacyMigration).Path -ne [IO.Path]::GetFullPath($targetLegacyMigration)) {
    Copy-Item -LiteralPath $packagedLegacyMigration -Destination $targetLegacyMigration -Force
}
if ((Resolve-Path -LiteralPath $packagedRepair).Path -ne [IO.Path]::GetFullPath($targetRepair)) {
    Copy-Item -LiteralPath $packagedRepair -Destination $targetRepair -Force
}
if ((Resolve-Path -LiteralPath $packagedIcon).Path -ne [IO.Path]::GetFullPath($targetIcon)) {
    Copy-Item -LiteralPath $packagedIcon -Destination $targetIcon -Force
}

$configPath = Join-Path $DataRoot "config.json"
if ($EnrollmentTokenFile) {
    $EnrollmentToken = (Get-Content -LiteralPath $EnrollmentTokenFile -Raw).Trim()
} elseif (-not $EnrollmentToken -and $env:NORTHSTAR_ENROLLMENT_TOKEN) {
    $EnrollmentToken = $env:NORTHSTAR_ENROLLMENT_TOKEN
}

# A new code after uninstall may accompany a retained but revoked credential.
# Test that credential once; preserve valid enrollment, otherwise back it up
# and perform a clean enrollment with the supplied code.
if ((Test-Path -LiteralPath $configPath) -and $EnrollmentToken) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $credentialOutput = & $targetExecutable --data-dir $DataRoot --heartbeat-once 2>&1
    $credentialExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($credentialExitCode -ne 0) {
        $backup = Join-Path $DataRoot ("config.json.bak-" + (Get-Date -Format "yyyyMMddHHmmss"))
        Move-Item -LiteralPath $configPath -Destination $backup
        Write-InstallWarning "The retained endpoint credential was rejected and was backed up to $backup before re-enrollment. $($credentialOutput -join ' ')"
        $global:LASTEXITCODE = 0
    }
}

if (-not (Test-Path -LiteralPath $configPath)) {
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
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "Endpoint enrollment failed (exit code $agentExitCode): $($agentOutput -join ' ')"
    }
    if ($agentExitCode -ne 0) {
        Write-InstallWarning "Endpoint enrollment succeeded, but the first inventory failed (exit code $agentExitCode). The scheduled agent will retry. $($agentOutput -join ' ')"
        $global:LASTEXITCODE = 0
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
# Remove the legacy machine-wide Run value so it cannot race the task/Startup
# launchers or keep an older executable alive after an upgrade.
Remove-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "Northstar Endpoint Tray" -ErrorAction SilentlyContinue

$startupFolder = [Environment]::GetFolderPath([Environment+SpecialFolder]::CommonStartup)
$startupShortcut = Join-Path $startupFolder "Northstar Endpoint Agent.lnk"
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($startupShortcut)
$shortcut.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $targetTrayLauncher + '"'
$shortcut.WorkingDirectory = $InstallRoot
$shortcut.IconLocation = (Join-Path $InstallRoot "northstar.ico") + ",0"
$shortcut.Save()

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
$powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$previousPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    $migrationOutput = & $powerShell -NoProfile -ExecutionPolicy Bypass -File $targetLegacyMigration -InstallRoot $InstallRoot 2>&1
    $migrationExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($migrationExitCode -ne 0) {
    throw "Legacy installation migration failed (exit code $migrationExitCode): $($migrationOutput -join ' ')"
}
$deadline = (Get-Date).AddSeconds(30)
do {
    $confirmed = @(Get-CimInstance Win32_Process -Filter "Name='NorthstarEndpointAgent.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq [IO.Path]::GetFullPath($targetExecutable)) }).Count -gt 0
    if (-not $confirmed) { Start-Sleep -Milliseconds 500 }
} while (-not $confirmed -and (Get-Date) -lt $deadline)
if (-not $confirmed) { throw "The new Northstar Endpoint Agent was not confirmed running from $targetExecutable within 30 seconds." }
try {
    try {
        $ErrorActionPreference = "Continue"
        $trayOutput = & $powerShell -NoProfile -ExecutionPolicy Bypass -File $targetTrayTaskInstaller -InstallRoot $InstallRoot 2>&1
        $trayExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($trayExitCode -ne 0) { throw "The tray launcher task could not be registered (exit code $trayExitCode): $($trayOutput -join ' ')" }
    & $schtasks /Run /TN "Northstar Endpoint Tray Launcher" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "The tray launcher task could not be started (exit code $LASTEXITCODE)." }
} catch {
    Write-InstallWarning "The endpoint agent is running, but tray startup needs attention: $($_.Exception.Message)"
    $global:LASTEXITCODE = 0
}
Write-Host "Northstar Endpoint Agent installed for all users and reporting to $ServerUrl"
Write-Host "The tray companion was requested for signed-in users and will also start at future sign-ins."
$global:LASTEXITCODE = 0
exit 0

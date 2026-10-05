[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\Northstar Endpoint Agent",
    [string]$LegacyInstallRoot = "${env:ProgramFiles(x86)}\Northstar Endpoint Agent",
    [int]$StartupTimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$taskNames = @("Northstar Endpoint Agent", "Northstar Endpoint Agent - User Logon Inventory")
$schtasks = Join-Path $env:SystemRoot "System32\schtasks.exe"
$targetExecutable = [IO.Path]::GetFullPath((Join-Path $InstallRoot "NorthstarEndpointAgent.exe"))
$legacyRoot = [IO.Path]::GetFullPath($LegacyInstallRoot).TrimEnd('\')
$newRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')

if ($legacyRoot -ieq $newRoot -or
    [IO.Path]::GetFileName($legacyRoot) -ine "Northstar Endpoint Agent" -or
    -not $legacyRoot.StartsWith([IO.Path]::GetFullPath(${env:ProgramFiles(x86)}).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe legacy agent migration path: $legacyRoot"
}

function Get-NorthstarTaskXml {
    param([Parameter(Mandatory=$true)][string]$Name)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $xmlText = (& $schtasks /Query /TN $Name /XML 2>$null | Out-String)
        if ($LASTEXITCODE -ne 0) { return $null }
        [xml]$xml = $xmlText
        return $xml
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Set-NorthstarTaskExecutable {
    param([Parameter(Mandatory=$true)][string]$Name)
    $xml = Get-NorthstarTaskXml -Name $Name
    if (-not $xml) { return $false }
    $namespace = New-Object Xml.XmlNamespaceManager($xml.NameTable)
    $namespace.AddNamespace("t", $xml.DocumentElement.NamespaceURI)
    $exec = $xml.SelectSingleNode("/t:Task/t:Actions/t:Exec", $namespace)
    if (-not $exec -or -not $exec.Command) { throw "Task '$Name' has no executable action." }
    $existingCommand = [Environment]::ExpandEnvironmentVariables([string]$exec.Command).Trim('"')
    if ([IO.Path]::GetFullPath($existingCommand) -ieq $targetExecutable) { return $false }
    $exec.Command = $targetExecutable
    $xmlPath = Join-Path $env:TEMP ("northstar-migrate-" + [guid]::NewGuid().ToString("N") + ".xml")
    try {
        $xml.Save($xmlPath)
        $output = & $schtasks /Create /TN $Name /XML $xmlPath /F 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Could not repoint '$Name': $($output -join ' ')" }
    } finally {
        Remove-Item -LiteralPath $xmlPath -Force -ErrorAction SilentlyContinue
    }
    return $true
}

$newTrayConfig = Join-Path $newRoot "tray-config.json"
$legacyTrayConfig = Join-Path $legacyRoot "tray-config.json"
if (-not (Test-Path -LiteralPath $newTrayConfig) -and (Test-Path -LiteralPath $legacyTrayConfig)) {
    Copy-Item -LiteralPath $legacyTrayConfig -Destination $newTrayConfig -Force
}

$repointed = $false
foreach ($taskName in $taskNames) {
    if (Set-NorthstarTaskExecutable -Name $taskName) { $repointed = $true }
}

if ($repointed -or (Test-Path -LiteralPath $legacyRoot)) {
    & $schtasks /Run /TN $taskNames[0] | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "The migrated Northstar Endpoint Agent task could not be started." }
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    $confirmed = $false
    do {
        $confirmed = @(Get-CimInstance Win32_Process -Filter "Name='NorthstarEndpointAgent.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.ExecutablePath -and ([IO.Path]::GetFullPath($_.ExecutablePath) -ieq $targetExecutable) }).Count -gt 0
        if (-not $confirmed) { Start-Sleep -Milliseconds 500 }
    } while (-not $confirmed -and (Get-Date) -lt $deadline)
    if (-not $confirmed) { throw "The new Northstar Endpoint Agent executable was not confirmed running; the legacy installation was preserved." }
}

if (Test-Path -LiteralPath $legacyRoot) {
    Remove-Item -LiteralPath $legacyRoot -Recurse -Force
}

$uninstallRoot = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
if (Test-Path -LiteralPath $uninstallRoot) {
    Get-ChildItem -LiteralPath $uninstallRoot | ForEach-Object {
        $entry = Get-ItemProperty -LiteralPath $_.PSPath
        $location = [Environment]::ExpandEnvironmentVariables([string]$entry.InstallLocation).TrimEnd('\')
        if ($entry.DisplayName -eq "Northstar Endpoint Agent" -and
            (($location -and $location -ieq $legacyRoot) -or ([string]$entry.UninstallString -like "*$legacyRoot*"))) {
            Remove-Item -LiteralPath $_.PSPath -Recurse -Force
        }
    }
}

Write-Host "Northstar Endpoint Agent task paths and legacy x86 installation are current."

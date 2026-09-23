param(
    [Parameter(Mandatory=$true)][string]$ServerUrl,
    [string]$EnrollmentToken = "",
    [string]$UserEmail = ""
)
$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $agentRoot
$dataRoot = Join-Path $env:LOCALAPPDATA "NorthstarEndpointAgent"
$configPath = Join-Path $dataRoot "config.json"
$venv = Join-Path $dataRoot "venv"
$python = Join-Path $venv "Scripts\python.exe"
$pythonw = Join-Path $venv "Scripts\pythonw.exe"
New-Item -ItemType Directory -Force -Path $dataRoot | Out-Null
$alreadyEnrolled = Test-Path $configPath
if (-not $alreadyEnrolled -and -not $EnrollmentToken) {
    $secureToken = Read-Host "Paste the one-time enrollment token" -AsSecureString
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try { $EnrollmentToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer) }
}
if (-not $alreadyEnrolled -and -not $EnrollmentToken) { throw "An enrollment token is required for first-time installation." }
if (-not (Test-Path $python)) {
    $projectPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path $projectPython) {
        $bootstrapPython = $projectPython
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python is not available. Install Northstar Desk first, or install Python 3.12 or later."
        }
        $bootstrapPython = $pythonCommand.Source
    }
    & $bootstrapPython -m venv $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) {
        throw "The endpoint-agent Python environment could not be created using $bootstrapPython."
    }
}
& $python -m pip install --disable-pip-version-check --force-reinstall $agentRoot
if ($LASTEXITCODE -ne 0) { throw "The endpoint-agent package could not be installed." }
$arguments = @("-m", "asset_agent", "--data-dir", $dataRoot, "--server", $ServerUrl, "--once")
if (-not $alreadyEnrolled) { $arguments += @("--enrollment-token", $EnrollmentToken) }
if ($UserEmail) { $arguments += @("--user-email", $UserEmail) }
& $python @arguments
$EnrollmentToken = $null
if ($LASTEXITCODE -ne 0) { throw "The first endpoint inventory did not complete." }
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "Northstar Endpoint Agent.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "-m asset_agent --data-dir `"$dataRoot`""
$shortcut.WorkingDirectory = $dataRoot
$shortcut.Description = "Northstar Windows inventory agent"
$shortcut.WindowStyle = 7
$shortcut.Save()
Start-Process -FilePath $pythonw -ArgumentList "-m","asset_agent","--data-dir",$dataRoot -WorkingDirectory $dataRoot -WindowStyle Hidden
Write-Host "Northstar Endpoint Agent installed and reporting to $ServerUrl"

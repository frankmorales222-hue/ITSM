param(
    [string]$Python = "",
    [string]$OutputDirectory = "",
    [string]$CertificateThumbprint = ""
)
$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent $agentRoot
if (-not $Python) { $Python = Join-Path $projectRoot ".venv\Scripts\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime not found: $Python" }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $agentRoot "artifacts\NorthstarEndpointAgent-enterprise" }
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is required in the build environment. Install it with: .venv\Scripts\python.exe -m pip install pyinstaller" }
$buildRoot = Join-Path $agentRoot "build\enterprise"
$distRoot = Join-Path $agentRoot "dist"
$iconPath = Join-Path $agentRoot "assets\northstar.ico"
if (-not (Test-Path -LiteralPath $iconPath)) { throw "Northstar tray icon was not found: $iconPath" }
Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $OutputDirectory -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $distRoot "NorthstarEndpointAgent.exe") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $distRoot "NorthstarEndpointTray") -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $buildRoot,$distRoot,$OutputDirectory | Out-Null
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Python -m PyInstaller --noconfirm --clean --onefile --icon $iconPath --name NorthstarEndpointAgent --paths $agentRoot --distpath $distRoot --workpath $buildRoot --specpath $buildRoot (Join-Path $agentRoot "enterprise_entry.py")
$agentBuildExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($agentBuildExitCode -ne 0) { throw "Endpoint executable build failed." }
$ErrorActionPreference = "Continue"
# The tray companion is deliberately an onedir build.  A onefile PyInstaller
# executable has to unpack runtime DLLs into a temporary directory each time a
# user signs in; endpoint security and profile ACLs can block that extraction
# before the tray has a chance to start.  Keeping its signed runtime beside the
# executable removes that fragile extraction step.
& $Python -m PyInstaller --noconfirm --clean --onedir --noconsole --icon $iconPath --name NorthstarEndpointTray --paths $agentRoot --distpath $distRoot --workpath $buildRoot --specpath $buildRoot (Join-Path $agentRoot "tray_entry.py")
$trayBuildExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($trayBuildExitCode -ne 0) { throw "Endpoint tray executable build failed." }
$exe = Join-Path $distRoot "NorthstarEndpointAgent.exe"
$trayDirectory = Join-Path $distRoot "NorthstarEndpointTray"
$trayExe = Join-Path $trayDirectory "NorthstarEndpointTray.exe"
if ($CertificateThumbprint) {
    $certificate = Get-Item "Cert:\CurrentUser\My\$CertificateThumbprint"
    $signature = Set-AuthenticodeSignature -FilePath $exe -Certificate $certificate -TimestampServer "http://timestamp.digicert.com"
    if ($signature.Status -ne "Valid") { throw "Code signing failed: $($signature.StatusMessage)" }
    $traySignature = Set-AuthenticodeSignature -FilePath $trayExe -Certificate $certificate -TimestampServer "http://timestamp.digicert.com"
    if ($traySignature.Status -ne "Valid") { throw "Tray code signing failed: $($traySignature.StatusMessage)" }
}
Copy-Item -LiteralPath $exe -Destination $OutputDirectory -Force
Copy-Item -LiteralPath $trayDirectory -Destination (Join-Path $OutputDirectory "NorthstarEndpointTray") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install-enterprise.ps1"),(Join-Path $PSScriptRoot "install-enterprise.cmd"),(Join-Path $PSScriptRoot "uninstall-enterprise.ps1"),(Join-Path $PSScriptRoot "uninstall-enterprise.cmd") -Destination $OutputDirectory -Force
$zip = "$OutputDirectory.zip"
Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $OutputDirectory "*") -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Set-Content -LiteralPath "$zip.sha256" -Value "$hash  $(Split-Path -Leaf $zip)" -Encoding ascii
Write-Host "Enterprise agent package created: $zip"

$ErrorActionPreference="Stop"
$installerRoot=$PSScriptRoot
$projectRoot=Split-Path -Parent $installerRoot
$compilerCandidates=@(
  "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$compiler=$compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if(-not $compiler){throw "Inno Setup 6 compiler is not installed."}
& (Join-Path $installerRoot "invoke-release-gate.ps1") -RequirePostgreSQL
if($LASTEXITCODE -ne 0){throw "Mandatory release gate failed; no installer was built."}
& (Join-Path $installerRoot "prepare-assetpilot.ps1")
& (Join-Path $installerRoot "prepare-caddy.ps1")
if($LASTEXITCODE -ne 0){throw "Verified Caddy staging failed."}
# Always rebuild so an installer can never silently contain stale backend or
# frontend files from an earlier evaluation build.
& (Join-Path $installerRoot "build-server-bundle.ps1")
if($LASTEXITCODE -ne 0){throw "Northstar Desk server bundle failed."}
Push-Location $installerRoot
try {
  & $compiler "NorthstarDesk.iss"
  if($LASTEXITCODE -ne 0){throw "Evaluation installer compilation failed."}
  & $compiler "NorthstarDeskServer.iss"
} finally { Pop-Location }
if($LASTEXITCODE -ne 0){throw "Installer compilation failed."}
$setup=Join-Path $installerRoot "artifacts\NorthstarDesk-Setup-0.1.0.exe"
$hash=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
Set-Content -LiteralPath "$setup.sha256" -Value "$hash  $(Split-Path -Leaf $setup)" -Encoding ascii
Write-Host "Installer created: $setup"
$serverSetup=Get-ChildItem -LiteralPath (Join-Path $installerRoot "artifacts") -Filter "NorthstarDesk-Server-Setup-*.exe" -File |
  Where-Object { $_.BaseName -match '^NorthstarDesk-Server-Setup-(\d+)\.(\d+)\.(\d+)$' } |
  Sort-Object @{ Expression={ [version]$_.BaseName.Substring('NorthstarDesk-Server-Setup-'.Length) }; Descending=$true } |
  Select-Object -First 1 -ExpandProperty FullName
if(-not $serverSetup){throw "Server installer was not produced."}
$serverHash=(Get-FileHash -LiteralPath $serverSetup -Algorithm SHA256).Hash
Set-Content -LiteralPath "$serverSetup.sha256" -Value "$serverHash  $(Split-Path -Leaf $serverSetup)" -Encoding ascii
Write-Host "Server installer created: $serverSetup"
$env:NORTHSTAR_VERIFY_RELEASE_ARTIFACT="1"
& (Join-Path $projectRoot ".venv\Scripts\python.exe") -m pytest -q tests\test_server_installer.py -k final_server_installer_exists
if($LASTEXITCODE -ne 0){throw "Compiled server installer artifact verification failed."}

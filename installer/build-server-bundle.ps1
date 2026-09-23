param([string]$Python="")
$ErrorActionPreference="Stop"
$projectRoot=Split-Path -Parent $PSScriptRoot
if(-not $Python){$Python=Join-Path $projectRoot ".venv\Scripts\python.exe"}
if(-not (Test-Path $Python)){throw "Project Python runtime not found."}
$frontendIndex=Join-Path $projectRoot "frontend\dist\index.html"
if(-not (Test-Path -LiteralPath $frontendIndex)){
  throw "Fresh frontend build not found. Run installer\invoke-release-gate.ps1 first."
}
$agentArtifacts=Join-Path $projectRoot "endpoint_agent\artifacts"
$agentInstaller=Get-ChildItem -LiteralPath $agentArtifacts -Filter "NorthstarEndpointAgent-Setup-*.exe" -File -ErrorAction SilentlyContinue |
  Where-Object { $_.BaseName -match '^NorthstarEndpointAgent-Setup-(\d+)\.(\d+)\.(\d+)$' } |
  Sort-Object @{ Expression={ [version]$_.BaseName.Substring('NorthstarEndpointAgent-Setup-'.Length) }; Descending=$true } |
  Select-Object -First 1 -ExpandProperty FullName
if(-not $agentInstaller){
  & (Join-Path $projectRoot "endpoint_agent\scripts\build-self-service-installer.ps1")
  $agentInstaller=Get-ChildItem -LiteralPath $agentArtifacts -Filter "NorthstarEndpointAgent-Setup-*.exe" -File |
    Where-Object { $_.BaseName -match '^NorthstarEndpointAgent-Setup-(\d+)\.(\d+)\.(\d+)$' } |
    Sort-Object @{ Expression={ [version]$_.BaseName.Substring('NorthstarEndpointAgent-Setup-'.Length) }; Descending=$true } |
    Select-Object -First 1 -ExpandProperty FullName
}
if(-not $agentInstaller){throw "Endpoint agent installer was not produced."}
Write-Host "Embedding endpoint agent: $agentInstaller"
$dist=Join-Path $PSScriptRoot "dist"
$work=Join-Path $PSScriptRoot "build"
Remove-Item -LiteralPath $dist,$work -Recurse -Force -ErrorAction SilentlyContinue
$previousErrorActionPreference=$ErrorActionPreference
$ErrorActionPreference="Continue"
& $Python -m PyInstaller --noconfirm --clean --onedir --name NorthstarDeskServer `
  --paths (Join-Path $projectRoot "backend") `
  --collect-all keyring --collect-all uvicorn --collect-all websockets `
  --add-data "$(Join-Path $projectRoot 'frontend\dist');frontend\dist" `
  --add-data "$(Join-Path $projectRoot 'migrations');migrations" `
  --add-data "$(Join-Path $projectRoot 'alembic.ini');." `
  --add-data "$agentInstaller;agent_installer" `
  --distpath $dist --workpath $work --specpath $work `
  (Join-Path $PSScriptRoot "server_entry.py")
$pyInstallerExitCode=$LASTEXITCODE
$ErrorActionPreference=$previousErrorActionPreference
if($pyInstallerExitCode -ne 0){throw "Northstar Desk server bundle failed."}
Write-Host "Server bundle created at $dist\NorthstarDeskServer"

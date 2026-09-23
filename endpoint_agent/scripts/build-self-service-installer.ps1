param([string]$CertificateThumbprint = "")
$ErrorActionPreference = "Stop"
$agentRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $PSScriptRoot "build-enterprise-package.ps1") -CertificateThumbprint $CertificateThumbprint
$compilerCandidates = @(
  "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
  "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw "Inno Setup 6 compiler is not installed." }
Push-Location $agentRoot
try { & $compiler "NorthstarEndpointAgent.iss" } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Self-service endpoint installer compilation failed." }
$version = (Select-String -LiteralPath (Join-Path $agentRoot "asset_agent\__init__.py") -Pattern '__version__\s*=\s*"([0-9.]+)"').Matches[0].Groups[1].Value
$setup = Join-Path $agentRoot ("artifacts\NorthstarEndpointAgent-Setup-" + $version + ".exe")
if (-not (Test-Path -LiteralPath $setup)) { throw "Expected endpoint installer was not produced: $setup" }
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
Set-Content -LiteralPath "$setup.sha256" -Value "$hash  $(Split-Path -Leaf $setup)" -Encoding ascii
Write-Host "Self-service endpoint installer created: $setup"

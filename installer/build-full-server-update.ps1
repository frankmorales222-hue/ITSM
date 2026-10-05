param(
    [string]$Version = "0.4.95",
    [string]$MinimumCurrentVersion = "0.4.86",
    [string]$CodeSigningThumbprint = $env:NORTHSTAR_CODESIGN_THUMBPRINT,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$installerRoot = $PSScriptRoot
$projectRoot = Split-Path -Parent $installerRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$compiler = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not (Test-Path -LiteralPath $python)) { throw "Project Python runtime not found." }
if (-not $compiler) { throw "Inno Setup 6 compiler is not installed." }

$signTool = Get-Command signtool.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
if (-not $signTool) {
    $signTool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" `
        -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.DirectoryName -like "*\x64" } |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $signTool) { throw "Windows SDK signtool.exe was not found." }

$codeSigningCertificates = @(Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
    Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt (Get-Date) })
if ($CodeSigningThumbprint) {
    $normalizedThumbprint = $CodeSigningThumbprint.Replace(" ", "").ToUpperInvariant()
    $codeSigningCertificates = @($codeSigningCertificates | Where-Object {
        $_.Thumbprint.ToUpperInvariant() -eq $normalizedThumbprint
    })
}
if ($codeSigningCertificates.Count -ne 1) {
    throw "Exactly one valid CurrentUser code-signing certificate is required. Set NORTHSTAR_CODESIGN_THUMBPRINT when more than one is installed."
}
$codeSigningCertificate = $codeSigningCertificates[0]

$packageText = Get-Content -LiteralPath (Join-Path $projectRoot "backend\itsm\__init__.py") -Raw
$packageMatch = [regex]::Match($packageText, '__version__\s*=\s*["'']([^"'']+)["'']')
if (-not $packageMatch.Success) { throw "Backend version could not be read." }
$packageVersion = $packageMatch.Groups[1].Value
if ($packageVersion -ne $Version) {
    throw "Backend version $packageVersion does not match requested release $Version."
}
$issText = Get-Content -LiteralPath (Join-Path $installerRoot "NorthstarDeskServer.iss") -Raw
if ($issText -notmatch ('#define MyAppVersion "' + [regex]::Escape($Version) + '"')) {
    throw "Server installer version does not match requested release $Version."
}
$notes = Join-Path $installerRoot "release-notes-$Version.txt"
if (-not (Test-Path -LiteralPath $notes)) { throw "Release notes are missing: $notes" }

Push-Location $projectRoot
try {
    & $python -m pytest -q tests
    if ($LASTEXITCODE -ne 0) { throw "Northstar test suite failed; release build stopped." }

    pnpm --dir frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }

    & (Join-Path $installerRoot "prepare-caddy.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Verified Caddy staging failed." }

    & (Join-Path $installerRoot "build-server-bundle.ps1") -Python $python
    if ($LASTEXITCODE -ne 0) { throw "Northstar Desk server bundle failed." }

    & $compiler (Join-Path $installerRoot "NorthstarDeskServer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Full server installer compilation failed." }

    $payload = Join-Path $installerRoot "artifacts\NorthstarDesk-Server-Setup-$Version.exe"
    & $signTool sign /sha1 $codeSigningCertificate.Thumbprint /fd SHA256 `
        /tr $TimestampUrl /td SHA256 /v $payload
    if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
    & $signTool verify /pa /all /v $payload
    if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed." }
    if ((Get-AuthenticodeSignature -LiteralPath $payload).Status -ne "Valid") {
        throw "The signed installer did not pass Windows Authenticode validation."
    }

    $privateKey = Join-Path $installerRoot "signing\private\northstar.update-private.pem"
    $passwordFile = Join-Path $installerRoot "signing\private\northstar.update-private.password.txt"
    $output = Join-Path $installerRoot "artifacts\NorthstarDesk-$Version.nsupdate"

    & $python (Join-Path $installerRoot "update-package.py") build `
        --private-key $privateKey --password-file $passwordFile --payload $payload `
        --version $Version --publisher "Northstar" --release-notes-file $notes `
        --minimum-current-version $MinimumCurrentVersion --output $output
    if ($LASTEXITCODE -ne 0) { throw "Signed full server update package build failed." }

    $deliverables = Join-Path $projectRoot "deliverables"
    New-Item -ItemType Directory -Path $deliverables -Force | Out-Null
    Copy-Item -LiteralPath $output,("$output.sha256"),$payload -Destination $deliverables -Force
    Write-Host "Full server update created at $output"
}
finally {
    Pop-Location
}

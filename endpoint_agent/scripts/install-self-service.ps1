param([string]$EnrollmentCode = "")
$ErrorActionPreference = "Stop"
$errorLog = Join-Path $env:ProgramData "NorthstarEndpointAgent-install-error.log"
Remove-Item -LiteralPath $errorLog -Force -ErrorAction SilentlyContinue
trap {
    $details = ($_ | Out-String).Trim()
    Set-Content -LiteralPath $errorLog -Value $details -Encoding UTF8
    Write-Error $details
    exit 1
}
$dataRoot = Join-Path $env:ProgramData "NorthstarEndpointAgent"
$configPath = Join-Path $dataRoot "config.json"
$enrollmentToken = ""
$tlsCertificateSha256 = ""
$rootCertificateBytes = $null
if (Test-Path -LiteralPath $configPath) {
    try { $serverUrl = [string]((Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).server_url) }
    catch { throw "The existing agent configuration could not be read. Repair the installation as an administrator." }
    if (-not $serverUrl) { throw "The existing agent configuration does not contain the Help Desk address." }
} else {
    $parts = $EnrollmentCode.Trim().Split('.')
    if (($parts.Count -lt 2 -or $parts.Count -gt 4) -or -not $parts[0] -or -not $parts[1]) {
        throw "The enrollment code is invalid. Generate a new code from Northstar Desk."
    }
    $encoded = $parts[0].Replace('-', '+').Replace('_', '/')
    switch ($encoded.Length % 4) { 2 {$encoded += '=='} 3 {$encoded += '='} 1 {throw "The enrollment code is invalid."} }
    try { $serverUrl = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded)) }
    catch { throw "The enrollment code is invalid." }
    $enrollmentToken = $parts[1]
    if ($parts.Count -eq 3) {
        $tlsCertificateSha256 = $parts[2].Replace(':', '').ToLowerInvariant()
        if ($tlsCertificateSha256 -notmatch '^[0-9a-f]{64}$') { throw "The enrollment TLS fingerprint is invalid." }
    }
    if ($parts.Count -eq 4) {
        $expectedRootSha256 = $parts[2].Replace(':', '').ToLowerInvariant()
        if ($expectedRootSha256 -notmatch '^[0-9a-f]{64}$') { throw "The enrollment CA fingerprint is invalid." }
        $rootEncoded = $parts[3].Replace('-', '+').Replace('_', '/')
        switch ($rootEncoded.Length % 4) { 2 {$rootEncoded += '=='} 3 {$rootEncoded += '='} 1 {throw "The enrollment CA certificate is invalid."} }
        try { $rootCertificateBytes = [Convert]::FromBase64String($rootEncoded) }
        catch { throw "The enrollment CA certificate is invalid." }
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try { $actualRootSha256 = ([BitConverter]::ToString($sha256.ComputeHash($rootCertificateBytes))).Replace('-', '').ToLowerInvariant() }
        finally { $sha256.Dispose() }
        if ($actualRootSha256 -ne $expectedRootSha256) { throw "The enrollment CA certificate failed integrity verification." }
    }
}
if ($serverUrl -notmatch '^https://' -and $serverUrl -notmatch '^http://(localhost|127\.0\.0\.1)(:\d+)?/?$') {
    throw "The enrollment server must use HTTPS. HTTP is allowed only for local testing."
}
try {
    if ($rootCertificateBytes) {
        $rootCertificatePath = Join-Path $env:TEMP "Northstar-Caddy-Root-$PID.cer"
        try {
            [IO.File]::WriteAllBytes($rootCertificatePath, $rootCertificateBytes)
            $certutil = Join-Path $env:SystemRoot "System32\certutil.exe"
            $previousPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $certutilOutput = & $certutil -addstore -f Root $rootCertificatePath 2>&1
            $certutilExitCode = $LASTEXITCODE
            $ErrorActionPreference = $previousPreference
            if ($certutilExitCode -ne 0) { throw "Windows could not trust the Northstar internal certificate (exit code $certutilExitCode): $($certutilOutput -join ' ')" }
        } finally {
            Remove-Item -LiteralPath $rootCertificatePath -Force -ErrorAction SilentlyContinue
        }
    }
    & (Join-Path $PSScriptRoot "install-enterprise.ps1") -ServerUrl $serverUrl -EnrollmentToken $enrollmentToken -TlsCertificateSha256 $tlsCertificateSha256
    if ($LASTEXITCODE -ne 0) { throw "Northstar Endpoint Agent installation failed with exit code $LASTEXITCODE." }
} catch {
    $details = ($_ | Out-String).Trim()
    Set-Content -LiteralPath $errorLog -Value $details -Encoding UTF8
    throw
}

# The elevated installation deliberately does not launch desktop UI. Inno
# Setup starts launch-tray.ps1 with the original interactive user's token after
# installation; HKLM Run handles subsequent Windows sign-ins.

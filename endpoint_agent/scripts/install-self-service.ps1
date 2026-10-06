param(
    [string]$EnrollmentCode = "",
    [string]$EnrollmentCodeFile = "",
    [string]$InstallRoot = "",
    [string]$DataRoot = ""
)
$ErrorActionPreference = "Stop"
$errorLog = Join-Path $env:ProgramData "NorthstarEndpointAgent-install-error.log"
Remove-Item -LiteralPath $errorLog -Force -ErrorAction SilentlyContinue
trap {
    $details = ($_ | Out-String).Trim()
    Set-Content -LiteralPath $errorLog -Value $details -Encoding UTF8
    Write-Error $details
    exit 1
}
$agentDataRoot = if ($DataRoot) { $DataRoot } else { Join-Path $env:ProgramData "NorthstarEndpointAgent" }
$configPath = Join-Path $agentDataRoot "config.json"
$enrollmentToken = ""
$tlsCertificateSha256 = ""
$rootCertificateBytes = $null
$stagedTokenPath = $null
if ($EnrollmentCodeFile) {
    try { $EnrollmentCode = (Get-Content -LiteralPath $EnrollmentCodeFile -Raw).Trim() }
    catch { throw "The staged enrollment code could not be read." }
}
if ($EnrollmentCode.Trim()) {
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
} elseif (Test-Path -LiteralPath $configPath) {
    try { $serverUrl = [string]((Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json).server_url) }
    catch { throw "The existing agent configuration could not be read. Repair the installation as an administrator." }
    if (-not $serverUrl) { throw "The existing agent configuration does not contain the Help Desk address." }
} else {
    throw "This computer is not enrolled. Supply an enrollment code from Northstar Desk."
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
    $powerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $enterpriseScript = Join-Path $PSScriptRoot "install-enterprise.ps1"
    $enterpriseArguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $enterpriseScript,
        "-ServerUrl", $serverUrl)
    if ($tlsCertificateSha256) { $enterpriseArguments += @("-TlsCertificateSha256", $tlsCertificateSha256) }
    if ($InstallRoot) { $enterpriseArguments += @("-InstallRoot", $InstallRoot) }
    if ($DataRoot) { $enterpriseArguments += @("-DataRoot", $DataRoot) }
    if ($enrollmentToken) {
        $stagingRoot = Join-Path $env:ProgramData "NorthstarEndpointAgent-staging"
        New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
        & icacls.exe $stagingRoot /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)(F)" "*S-1-5-32-544:(OI)(CI)(F)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "The enrollment staging directory could not be secured." }
        $stagedTokenPath = Join-Path $stagingRoot ("enrollment-" + $PID + "-" + [guid]::NewGuid().ToString("N") + ".token")
        Set-Content -LiteralPath $stagedTokenPath -Value $enrollmentToken -NoNewline -Encoding ascii
        & icacls.exe $stagedTokenPath /inheritance:r /grant:r "*S-1-5-18:(F)" "*S-1-5-32-544:(F)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "The staged enrollment token could not be secured." }
        $enterpriseArguments += @("-EnrollmentTokenFile", $stagedTokenPath)
    }
    $enrollmentToken = $null
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $enterpriseOutput = & $powerShell @enterpriseArguments 2>&1
        $enterpriseExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($enterpriseExitCode -ne 0) {
        throw "Northstar Endpoint Agent installation failed with exit code $enterpriseExitCode. $($enterpriseOutput -join ' ')"
    }
    $enterpriseOutput | Write-Output
} catch {
    $details = ($_ | Out-String).Trim()
    Set-Content -LiteralPath $errorLog -Value $details -Encoding UTF8
    throw
} finally {
    if ($stagedTokenPath) {
        Remove-Item -LiteralPath $stagedTokenPath -Force -ErrorAction SilentlyContinue
    }
}

# install-enterprise.ps1 registers and starts the on-demand BUILTIN\Users tray
# task. Inno invokes the same task after every update, including SYSTEM-driven
# automatic updates, while the Common Startup shortcut handles future sign-ins.
$global:LASTEXITCODE = 0
exit 0

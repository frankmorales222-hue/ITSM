[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $process = Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -Wait -PassThru
    exit $process.ExitCode
}

$certificatePath = Join-Path $PSScriptRoot "NorthstarDesk-Internal-Root-CA.cer"
$thumbprintPath = Join-Path $PSScriptRoot "NorthstarDesk-Internal-Root-CA.thumbprint.txt"
if (-not (Test-Path -LiteralPath $certificatePath) -or -not (Test-Path -LiteralPath $thumbprintPath)) {
    throw "The certificate or its verification thumbprint is missing. Extract the complete ZIP before running setup."
}

$expectedThumbprint = (Get-Content -LiteralPath $thumbprintPath -Raw).Trim().ToUpperInvariant()
if ($expectedThumbprint -notmatch '^[A-F0-9]{40}$') {
    throw "The certificate verification thumbprint is invalid."
}

$certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certificatePath)
try {
    if ($certificate.Thumbprint.ToUpperInvariant() -ne $expectedThumbprint) {
        throw "Certificate verification failed. The certificate does not match the server-exported thumbprint."
    }
    $basicConstraints = $certificate.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.19" } | Select-Object -First 1
    if (-not $basicConstraints -or -not $basicConstraints.CertificateAuthority) {
        throw "Certificate verification failed. This is not a certificate-authority root."
    }
    if ($certificate.Subject -ne $certificate.Issuer) {
        throw "Certificate verification failed. The root certificate is not self-signed."
    }
    $now = Get-Date
    if ($now -lt $certificate.NotBefore -or $now -gt $certificate.NotAfter) {
        throw "Certificate verification failed. The root certificate is not currently valid."
    }

    $existing = Get-ChildItem Cert:\LocalMachine\Root | Where-Object {
        $_.Thumbprint -eq $expectedThumbprint
    } | Select-Object -First 1
    if (-not $existing) {
        Import-Certificate -FilePath $certificatePath -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    }
    $installed = Get-ChildItem Cert:\LocalMachine\Root | Where-Object {
        $_.Thumbprint -eq $expectedThumbprint
    } | Select-Object -First 1
    if (-not $installed) {
        throw "Windows did not retain the Northstar root certificate in the Local Computer trusted-root store."
    }
    Write-Host "Trusted Northstar HTTPS root installed: $expectedThumbprint" -ForegroundColor Green
    Write-Host "Close every browser window, reopen the browser, and visit the Northstar Desk HTTPS address."
}
finally {
    $certificate.Dispose()
}


[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $env:PUBLIC "Desktop")
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -OutputDirectory `"$OutputDirectory`""
    $process = Start-Process powershell.exe -Verb RunAs -ArgumentList $arguments -Wait -PassThru
    exit $process.ExitCode
}

$knownRoots = @(
    (Join-Path $env:WINDIR "System32\config\systemprofile\AppData\Roaming\Caddy\pki\authorities\local\root.crt"),
    (Join-Path $env:WINDIR "SysWOW64\config\systemprofile\AppData\Roaming\Caddy\pki\authorities\local\root.crt"),
    (Join-Path $env:ProgramData "Caddy\pki\authorities\local\root.crt"),
    (Join-Path $env:ProgramData "NorthstarDesk\Caddy\pki\authorities\local\root.crt")
)

$rootPath = $knownRoots | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $rootPath) {
    throw @"
Northstar's Caddy root certificate was not found. Confirm that the "Northstar HTTPS"
scheduled task has run successfully, open the Northstar site once, and run this tool again.
"@
}

$certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($rootPath)
$basicConstraints = $certificate.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.19" } | Select-Object -First 1
if (-not $basicConstraints -or -not $basicConstraints.CertificateAuthority) {
    throw "The discovered certificate is not a certificate-authority root. No package was created."
}
if ($certificate.Subject -ne $certificate.Issuer) {
    throw "The discovered certificate is not self-signed. No package was created."
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$staging = Join-Path $env:TEMP ("NorthstarDesk-HTTPS-Trust-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $staging | Out-Null

try {
    $cerPath = Join-Path $staging "NorthstarDesk-Internal-Root-CA.cer"
    [IO.File]::WriteAllBytes(
        $cerPath,
        $certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert)
    )
    $thumbprint = $certificate.Thumbprint.ToUpperInvariant()
    Set-Content -LiteralPath (Join-Path $staging "NorthstarDesk-Internal-Root-CA.thumbprint.txt") `
        -Value $thumbprint -Encoding ASCII

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Install-NorthstarDesk-HTTPS-Trust.cmd") -Destination $staging
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "Install-NorthstarDesk-HTTPS-Trust.ps1") -Destination $staging
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.txt") -Destination $staging

    $sha256 = (Get-FileHash -LiteralPath $cerPath -Algorithm SHA256).Hash
    @"
Northstar Desk internal HTTPS root certificate
Subject: $($certificate.Subject)
Issuer: $($certificate.Issuer)
Thumbprint (SHA-1 certificate identifier): $thumbprint
Certificate file SHA-256: $sha256
Valid from (UTC): $($certificate.NotBefore.ToUniversalTime().ToString("u"))
Valid until (UTC): $($certificate.NotAfter.ToUniversalTime().ToString("u"))
Exported from: $rootPath
Created (UTC): $([DateTime]::UtcNow.ToString("u"))
"@ | Set-Content -LiteralPath (Join-Path $staging "certificate-manifest.txt") -Encoding UTF8

    $zipPath = Join-Path $OutputDirectory "NorthstarDesk-HTTPS-Client-Trust.zip"
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -CompressionLevel Optimal

    Write-Host "Created: $zipPath" -ForegroundColor Green
    Write-Host "Certificate thumbprint: $thumbprint"
    Write-Host "Deploy NorthstarDesk-Internal-Root-CA.cer through Group Policy, or run the included CMD on one test laptop."
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
    $certificate.Dispose()
}


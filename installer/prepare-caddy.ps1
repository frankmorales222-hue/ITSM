param([string]$Version = "2.11.4")

$ErrorActionPreference = "Stop"
$expectedSha512 = "cd5ccfd86a4b40732cf715890d0dca5bf3f63adefec5a7914de85adf240c60ce7e5d2791631b88ef9758e46b23bb1730e020b9c5d696889740b284ffd4788e35"
$expectedExecutableSha512 = "c2017a6042cb5daa6ff33bcb415411bb6fa07985e1f6c40cc632a3e10ae25fb921c98a7b16634b63dade43c3608474032f444514d46d654f630c7dd1fc1e0d62"
$destination = Join-Path $PSScriptRoot "vendor\Caddy"
$executable = Join-Path $destination "caddy.exe"
if (Test-Path -LiteralPath $executable) {
    $stagedHash = (Get-FileHash -LiteralPath $executable -Algorithm SHA512).Hash.ToLowerInvariant()
    if ($stagedHash -eq $expectedExecutableSha512) {
        Write-Host "Using verified staged Caddy $Version at $executable"
        exit 0
    }
    Remove-Item -LiteralPath $executable -Force
}

$archive = Join-Path ([System.IO.Path]::GetTempPath()) "caddy_$($Version)_windows_amd64.zip"
$uri = "https://github.com/caddyserver/caddy/releases/download/v$Version/caddy_$($Version)_windows_amd64.zip"
Invoke-WebRequest -Uri $uri -OutFile $archive
$actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToLowerInvariant()
if ($actual -ne $expectedSha512) {
    throw "Caddy archive checksum verification failed."
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
if (-not (Test-Path -LiteralPath $executable)) {
    throw "The verified Caddy archive did not contain caddy.exe."
}
$executableHash = (Get-FileHash -LiteralPath $executable -Algorithm SHA512).Hash.ToLowerInvariant()
if ($executableHash -ne $expectedExecutableSha512) {
    throw "The extracted Caddy executable checksum is invalid."
}
Write-Host "Verified Caddy $Version staged at $executable"

param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9.-]+$')][string]$DnsName,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9.-]+$')][string]$AssetDnsName,
    [Parameter(Mandatory=$true)][string]$PostgresServer,
    [string]$DatabaseName = "northstar_desk",
    [string]$DatabaseUser = "itsm_service",
    [int]$PostgresPort = 5432,
    [string]$ReverseProxyIp = "127.0.0.1",
    [string]$BackupDirectory = "D:\NorthstarDesk\backups"
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $envPath) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item -LiteralPath $envPath -Destination "$envPath.$stamp.bak"
}
$securePassword = Read-Host "PostgreSQL password for $DatabaseUser" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try { $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
$encodedUser = [Uri]::EscapeDataString($DatabaseUser)
$encodedPassword = [Uri]::EscapeDataString($plainPassword)
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Install Northstar Desk before configuring production." }
$secret = & $python -c "import secrets; print(secrets.token_urlsafe(48))"
if (-not $secret) { throw "Could not generate the application secret." }
$content = @"
ITSM_ENVIRONMENT=production
ITSM_DATABASE_URL=postgresql+psycopg://${encodedUser}:${encodedPassword}@${PostgresServer}:${PostgresPort}/${DatabaseName}
ITSM_SECRET_KEY=$secret
ITSM_SESSION_MINUTES=480
ITSM_COOKIE_SECURE=true
ITSM_PUBLIC_URL=https://$DnsName
ITSM_ALLOWED_ORIGINS=https://$DnsName
ITSM_TRUSTED_HOSTS=$DnsName
ITSM_FORWARDED_ALLOW_IPS=$ReverseProxyIp
ITSM_BIND_HOST=127.0.0.1
ITSM_PORT=8000
ITSM_OUTBOUND_EMAIL_ENABLED=false
ITSM_BACKUP_DIRECTORY=$BackupDirectory
ITSM_APP_VERSION=0.1.0
ITSM_AGENT_ALLOW_ACCOUNT_NAME_MATCH=true
ITSM_ASSETPILOT_URL=https://$AssetDnsName
ITSM_ASSETPILOT_INTERNAL_URL=http://127.0.0.1:5080
ITSM_ASSETPILOT_EXECUTABLE=C:/Program Files/Northstar Desk/AssetPilot/AssetPilot.exe
ITSM_ASSETPILOT_DATABASE_PATH=C:/ProgramData/NorthstarDesk/AssetPilot/Data/assetpilot.db
ITSM_ASSETPILOT_SYNC_MINUTES=5
"@
Set-Content -LiteralPath $envPath -Value $content -Encoding utf8
$plainPassword = $null
& icacls.exe $envPath /inheritance:r /grant:r "Administrators:(F)" "SYSTEM:(F)" | Out-Null
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$caddyPath = Join-Path $projectRoot "deployment\Caddyfile"
Set-Content -LiteralPath $caddyPath -Encoding utf8 -Value @"
$DnsName {
    tls internal
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}

$AssetDnsName {
    tls internal
    encode zstd gzip
    reverse_proxy 127.0.0.1:5080
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
"@
Write-Host "Shared deployment configuration created."
Write-Host "Outbound email is disabled for the pilot."
Write-Host "Next: point DNS $DnsName and $AssetDnsName to this server, start Caddy, migrate PostgreSQL, then run scripts\production-check.cmd."

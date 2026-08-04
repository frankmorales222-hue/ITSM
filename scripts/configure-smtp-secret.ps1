param([Parameter(Mandatory=$true)][string]$Username)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Application is not installed." }
$credential = Get-Credential -UserName $Username -Message "Enter the SMTP password or application password"
$password = $credential.GetNetworkCredential().Password
$env:ITSM_TEMP_SMTP_PASSWORD = $password
$env:ITSM_TEMP_SMTP_USERNAME = $Username
try {
    & ".venv\Scripts\python.exe" -c "import os,keyring; keyring.set_password('NorthstarDesk/smtp', os.environ['ITSM_TEMP_SMTP_USERNAME'], os.environ['ITSM_TEMP_SMTP_PASSWORD']); print('SMTP credential stored in Windows Credential Manager.')"
    if ($LASTEXITCODE -ne 0) { throw "SMTP credential could not be stored." }
} finally {
    Remove-Item Env:ITSM_TEMP_SMTP_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:ITSM_TEMP_SMTP_USERNAME -ErrorAction SilentlyContinue
}

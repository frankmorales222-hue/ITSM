param([Parameter(Mandatory=$true)][string]$Username,[string]$Target="NorthstarDesk/imap")
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run scripts\install.ps1 first." }
$secure = Read-Host "IMAP password or application password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr); & $python -c "import keyring,sys; keyring.set_password(sys.argv[1],sys.argv[2],sys.argv[3])" $Target $Username $plain }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $plain = $null }
Write-Host "Mailbox secret saved to Windows Credential Manager as $Target for $Username."

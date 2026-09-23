$ErrorActionPreference = "Continue"
$destination = "C:\Users\frank\Documents\ITSM\agent-installer-protected-log.txt"
$source = "C:\ProgramData\NorthstarEndpointAgent-install-error.log"

$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add("Collected: $(Get-Date -Format o)")
$lines.Add("Identity: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)")
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
$lines.Add("Administrator: $($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))")
$lines.Add("Log exists: $(Test-Path -LiteralPath $source)")
if (Test-Path -LiteralPath $source) {
    $lines.Add("--- INSTALLER ERROR ---")
    $lines.Add((Get-Content -LiteralPath $source -Raw))
}
$lines.Add("--- PROGRAMDATA ACL ---")
$lines.Add((& icacls.exe "C:\ProgramData\NorthstarEndpointAgent" 2>&1 | Out-String))
$lines | Set-Content -LiteralPath $destination -Encoding UTF8

$ErrorActionPreference = "Continue"
$destination = "C:\Users\frank\Documents\ITSM\agent-repair-result.txt"
$repair = "C:\Program Files\Northstar Endpoint Agent\install-self-service.ps1"

$output = & $repair *>&1 | Out-String
$exitCode = $LASTEXITCODE
@(
    "Completed: $(Get-Date -Format o)"
    "Exit code: $exitCode"
    "--- OUTPUT ---"
    $output
) | Set-Content -LiteralPath $destination -Encoding UTF8
if ($exitCode -ne 0) { exit $exitCode }

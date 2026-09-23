param(
    [string]$Project = (Join-Path $PSScriptRoot "..\integrations\AssetPilot\src\AssetPilot.Web\AssetPilot.Web.csproj"),
    [string]$Source = ""
)
$ErrorActionPreference = "Stop"
$destination = Join-Path $PSScriptRoot "vendor\AssetPilot"

Remove-Item -LiteralPath $destination -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $destination -Force | Out-Null

if ($Source) {
    $executable = Join-Path $Source "AssetPilot.exe"
    if (-not (Test-Path -LiteralPath $executable)) {
        throw "AssetPilot was not found at $Source."
    }
    Copy-Item -Path (Join-Path $Source "*") -Destination $destination -Recurse -Force
} else {
    if (-not (Test-Path -LiteralPath $Project)) {
        throw "The integrated AssetPilot project was not found at $Project."
    }
    dotnet publish $Project -c Release -r win-x64 --self-contained true -o $destination
    if ($LASTEXITCODE -ne 0) {
        throw "The integrated AssetPilot PostgreSQL build failed."
    }
}
# Runtime databases are deployment data and must never be embedded in the
# distributable application package, even if a source package was test-run.
$runtimeData = Join-Path $destination "App_Data"
if (Test-Path -LiteralPath $runtimeData) {
    Remove-Item -LiteralPath $runtimeData -Recurse -Force
}
if (-not (Test-Path -LiteralPath (Join-Path $destination "AssetPilot.exe"))) {
    throw "AssetPilot staging failed."
}
Write-Host "Integrated AssetPilot staged for the unified Northstar installer at $destination"

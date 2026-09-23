param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$solution = Join-Path $repositoryRoot "AssetPilot.slnx"

Push-Location $repositoryRoot
try {
    dotnet restore $solution -m:1
    if ($LASTEXITCODE -ne 0) { throw "Package restore failed." }

    dotnet build $solution --configuration $Configuration --no-restore -m:1
    if ($LASTEXITCODE -ne 0) { throw "Build failed." }

    dotnet test $solution --configuration $Configuration --no-build -m:1
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
}
finally {
    Pop-Location
}

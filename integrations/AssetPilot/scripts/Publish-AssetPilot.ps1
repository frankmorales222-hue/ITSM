param(
    [string[]]$RuntimeIdentifiers = @("win-x64"),
    [string]$Version = "3.6.0"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$webProject = Join-Path $repositoryRoot "src\AssetPilot.Web\AssetPilot.Web.csproj"
$artifactsDirectory = Join-Path $repositoryRoot "artifacts"

Push-Location $repositoryRoot
try {
    dotnet restore $webProject -m:1 -p:NuGetAudit=false
    if ($LASTEXITCODE -ne 0) { throw "Package restore failed." }

    dotnet build $webProject --configuration Release --no-restore -m:1
    if ($LASTEXITCODE -ne 0) { throw "Release build failed." }

    New-Item -ItemType Directory -Path $artifactsDirectory -Force | Out-Null

    foreach ($runtimeIdentifier in $RuntimeIdentifiers) {
        $packageName = "AssetPilot-$Version-$runtimeIdentifier"
        $publishDirectory = Join-Path $artifactsDirectory $packageName
        $archivePath = Join-Path $artifactsDirectory "$packageName.zip"

        if (Test-Path -LiteralPath $publishDirectory) {
            Remove-Item -LiteralPath $publishDirectory -Recurse -Force
        }
        if (Test-Path -LiteralPath $archivePath) {
            Remove-Item -LiteralPath $archivePath -Force
        }

        dotnet restore $webProject --runtime $runtimeIdentifier -m:1 -p:NuGetAudit=false
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime restore failed for $runtimeIdentifier."
        }

        dotnet publish $webProject `
            --configuration Release `
            --runtime $runtimeIdentifier `
            --self-contained true `
            --no-restore `
            -m:1 `
            -p:PublishSingleFile=false `
            -p:Version=$Version `
            --output $publishDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Publish failed for $runtimeIdentifier."
        }

        Copy-Item (Join-Path $repositoryRoot "DEPLOYMENT.md") $publishDirectory
        Copy-Item (Join-Path $repositoryRoot "PRODUCTION_CHECKLIST.md") $publishDirectory

        if ($runtimeIdentifier.StartsWith("win-")) {
            Copy-Item (Join-Path $repositoryRoot "deployment\windows\*") $publishDirectory
        }
        elseif ($runtimeIdentifier.StartsWith("linux-")) {
            Copy-Item (Join-Path $repositoryRoot "deployment\linux\*") $publishDirectory
        }

        Compress-Archive -Path $publishDirectory -DestinationPath $archivePath
        $hash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
        "$($hash.Hash)  $([IO.Path]::GetFileName($archivePath))" |
            Set-Content -LiteralPath "$archivePath.sha256" -Encoding ascii
    }
}
finally {
    Pop-Location
}


param(
    [string]$Token = $env:UV_PUBLISH_TOKEN,

    [string]$PublishUrl = "https://upload.pypi.org/legacy/",

    [string]$CheckUrl = "https://pypi.org/simple/",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Error "Missing PyPI token. Pass -Token or set UV_PUBLISH_TOKEN."
}
$env:UV_PUBLISH_TOKEN = $Token

if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}
New-Item "dist" -ItemType Directory -Force | Out-Null

uv build --all-packages --out-dir "dist" --no-create-gitignore
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$publishArgs = @("publish", "--publish-url", $PublishUrl, "--check-url", $CheckUrl)
if ($DryRun) {
    $publishArgs += "--dry-run"
}
$publishArgs += "dist/*"

uv @publishArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

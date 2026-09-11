param(
    [string]$Token = $env:UV_PUBLISH_TOKEN,
    [string]$PublishUrl = "https://upload.pypi.org/legacy/",
    [string]$CheckUrl = "https://pypi.org/simple/",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
# DryRun builds and validates without requiring a real publishing credential.
if (-not $DryRun -and [string]::IsNullOrWhiteSpace($Token)) {
    throw "Missing PyPI token. Pass -Token or set UV_PUBLISH_TOKEN."
}
if (-not [string]::IsNullOrWhiteSpace($Token)) {
    $env:UV_PUBLISH_TOKEN = $Token
}

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

# Resolve paths from this script, not the caller's current directory.
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    Invoke-Checked "uv" @("run", "--no-project", "--python", "3.13", "--with", "packaging", "python", "scripts/prepare_release.py", "--check-only")

    Push-Location "app/src/neobot_app/builtin_plugins/dashboard/frontend"
    try {
        # The repository uses pnpm-lock.yaml, so this is the npm ci equivalent.
        Invoke-Checked "pnpm" @("install", "--frozen-lockfile")
        foreach ($task in @("lint", "typecheck", "test", "build")) {
            Invoke-Checked "pnpm" @("run", $task)
        }
    }
    finally {
        Pop-Location
    }

    # Only clean dist after the frontend has successfully built.
    if (Test-Path "dist") {
        Remove-Item "dist" -Recurse -Force
    }
    New-Item "dist" -ItemType Directory -Force | Out-Null
    Invoke-Checked "uv" @("build", "--all-packages", "--out-dir", "dist", "--no-create-gitignore")

    $publishArgs = @("publish", "--publish-url", $PublishUrl, "--check-url", $CheckUrl)
    if ($DryRun) {
        $publishArgs += @("--dry-run", "--trusted-publishing", "never")
    }
    $publishArgs += "dist/*"
    Invoke-Checked "uv" $publishArgs
}
finally {
    Pop-Location
}

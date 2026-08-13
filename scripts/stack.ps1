[CmdletBinding()]
param(
    [ValidateSet("up", "status", "verify", "down")]
    [string]$Action = "status",
    [string]$Project = "northstar-g9"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    $dockerBin = Join-Path $env:LOCALAPPDATA "Programs\DockerDesktop\resources\bin"
    $dockerPath = Join-Path $dockerBin "docker.exe"
    if (-not (Test-Path -LiteralPath $dockerPath)) {
        throw "Docker CLI was not found on PATH or at $dockerPath"
    }
    $env:Path = "$dockerBin;$env:Path"
    $dockerExe = $dockerPath
} else {
    $dockerExe = $docker.Source
}

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Create it and install requirements.lock before running stack verification."
}
if (-not (Test-Path -LiteralPath (Join-Path $repo ".env"))) {
    throw "Missing .env. Copy .env.example to .env and replace every change-me value."
}

Push-Location $repo
try {
    switch ($Action) {
        "up" {
            & $dockerExe compose -p $Project up --build -d --wait
            if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
            & $python scripts\verify_stack.py --project $Project --no-smoke
            if ($LASTEXITCODE -ne 0) { throw "stack readiness verification failed" }
        }
        "status" { & $dockerExe compose -p $Project ps }
        "verify" {
            & $python scripts\verify_stack.py --project $Project
            if ($LASTEXITCODE -ne 0) { throw "stack verification failed" }
        }
        "down" { & $dockerExe compose -p $Project down }
    }
    if ($LASTEXITCODE -ne 0) { throw "stack command failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

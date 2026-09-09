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
            # Start the long-running dependencies first. Compose --wait treats
            # successful one-shot bootstrap containers as a failed project, so
            # those jobs are run separately below.
            & $dockerExe compose -p $Project up --build -d postgres api notification-sink metabase
            if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
            & $dockerExe compose -p $Project up -d --wait api notification-sink metabase
            if ($LASTEXITCODE -ne 0) { throw "stack dependencies did not become ready" }

            # The importer writes workflow definitions to n8n's database while
            # n8n is stopped. Importing against a live process can leave only a
            # subset of workflows published in n8n's in-memory registry.
            & $dockerExe compose -p $Project stop n8n frontend
            if ($LASTEXITCODE -ne 0) { throw "n8n workflow bootstrap failed" }
            & $dockerExe compose -p $Project up --no-deps --force-recreate n8n-bootstrap
            if ($LASTEXITCODE -ne 0) { throw "n8n workflow bootstrap failed" }
            & $dockerExe compose -p $Project up -d --no-deps --force-recreate --wait n8n
            if ($LASTEXITCODE -ne 0) { throw "n8n did not become ready after workflow bootstrap" }
            & $dockerExe compose -p $Project up --no-deps --force-recreate metabase-bootstrap
            if ($LASTEXITCODE -ne 0) { throw "Metabase bootstrap failed" }
            & $dockerExe compose -p $Project up -d --no-deps --wait frontend
            if ($LASTEXITCODE -ne 0) { throw "frontend did not become ready" }
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

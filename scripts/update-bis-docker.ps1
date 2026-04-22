<#
.SYNOPSIS
    Aktualisiert BIS per Git und baut/startet die Docker-Compose-Stack neu.

.DESCRIPTION
    - Wechselt ins Repository (Standard: ein Ordner ueber diesem Skript, wenn es unter scripts/ liegt).
    - Fuehrt optional `git pull` aus.
    - Fuehrt `docker compose up -d --build` aus (Images Application-Service + Proxy-Service).

    Voraussetzungen: Git im PATH, Docker Desktop / Docker CLI, im Projektroot eine `.env` mit SECRET_KEY
    und die Werte aus env_docker_example.txt (u.a. SECRET_KEY, BIS_*-Hostpfade), damit docker-compose die Substitution erfuellt.

.PARAMETER RepoRoot
    Absoluter Pfad zum BIS-Repository (Ordner mit docker-compose.yml).

.PARAMETER SkipGit
    Kein `git pull` (nur Docker neu bauen/starten).

.PARAMETER Branch
    Optional: vor dem Pull auf diesen Branch wechseln (z. B. main). Ohne Angabe bleibt der aktuelle Branch.

.EXAMPLE
    .\scripts\update-bis-docker.ps1

.EXAMPLE
    .\scripts\update-bis-docker.ps1 -RepoRoot "C:\DockerContainer\BIS"

.EXAMPLE
    .\scripts\update-bis-docker.ps1 -SkipGit
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $RepoRoot = "",

    [switch] $SkipGit,

    [Parameter(Mandatory = $false)]
    [string] $Branch = ""
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([string] $Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$composeFile = Join-Path $RepoRoot "docker-compose.yml"
if (-not (Test-Path -LiteralPath $composeFile)) {
    Write-Error "docker-compose.yml nicht gefunden unter: $RepoRoot"
}

if (-not (Test-CommandExists "git")) {
    Write-Error "Git wurde nicht gefunden (PATH pruefen)."
}

if (-not (Test-CommandExists "docker")) {
    Write-Error "Docker wurde nicht gefunden (Docker Desktop starten, PATH pruefen)."
}

Push-Location -LiteralPath $RepoRoot
try {
    Write-Host "Repository: $RepoRoot" -ForegroundColor Cyan

    if (-not $SkipGit) {
        if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot ".git"))) {
            Write-Error "Kein Git-Repository (.git fehlt) unter $RepoRoot"
        }

        if ($Branch) {
            Write-Host "Git: checkout $Branch ..." -ForegroundColor Yellow
            git checkout $Branch
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }

        Write-Host "Git: pull ..." -ForegroundColor Yellow
        git pull
        if ($LASTEXITCODE -ne 0) {
            Write-Error "git pull ist fehlgeschlagen (Konflikte loesen, dann erneut ausfuehren)."
        }
    }
    else {
        Write-Host "Git: uebersprungen (-SkipGit)." -ForegroundColor DarkYellow
    }

    $envFile = Join-Path $RepoRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) {
        Write-Warning "Keine .env im Repo-Root. docker compose benoetigt SECRET_KEY (siehe env_docker_example.txt)."
    }

    Write-Host "Docker: compose up -d --build ..." -ForegroundColor Yellow
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose ist fehlgeschlagen. Pruefen Sie SECRET_KEY in .env und Docker Desktop."
    }

    Write-Host "Docker: Status" -ForegroundColor Green
    docker compose ps
}
finally {
    Pop-Location
}

Write-Host "Fertig." -ForegroundColor Green

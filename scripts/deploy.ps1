# ============================================================
# MisMiss -- Deploy Script (Windows)
# ============================================================
# Usage:
#   powershell -File scripts/deploy.ps1
#   powershell -File scripts/deploy.ps1 -Mode Docker
#   powershell -File scripts/deploy.ps1 -Mode Native
# ============================================================

param(
    [ValidateSet("Docker", "Native")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."

function Write-I { Write-Host "[INFO]  $args" -ForegroundColor Green }
function Write-S { Write-Host "[STEP]  $args" -ForegroundColor Cyan }
function Write-W { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-E { Write-Host "[ERROR] $args" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------------ #
# Docker
# ------------------------------------------------------------------ #
function Deploy-Docker {
    Write-S "Docker deployment"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-E "Docker is required" }

    @("data", "logs", "plugins", "permissions") | ForEach-Object {
        if (-not (Test-Path "$ProjectRoot\$_")) {
            New-Item -ItemType Directory -Path "$ProjectRoot\$_" -Force | Out-Null
        }
    }

    Write-I "Building image..."
    docker build -t mismiss:latest "$ProjectRoot"
    if ($LASTEXITCODE -ne 0) { Write-E "Build failed" }

    docker rm -f mismiss 2>$null

    docker run -d --name mismiss --restart unless-stopped `
        -p 8080:8080 `
        -v "${ProjectRoot}\data:/app/data" `
        -v "${ProjectRoot}\logs:/app/logs" `
        -v "${ProjectRoot}\plugins:/app/plugins" `
        -v "${ProjectRoot}\permissions:/app/permissions" `
        -v "${ProjectRoot}\config.yml:/app/config.yml:ro" `
        -e TZ=Asia/Shanghai `
        mismiss:latest

    Write-I "Deployed -> http://localhost:8080"
    Write-I "Manage: docker logs -f mismiss  |  docker stop mismiss"
}

# ------------------------------------------------------------------ #
# Native
# ------------------------------------------------------------------ #
function Deploy-Native {
    Write-S "Native Windows deployment"
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-E "Python 3.13+ is required" }

    # venv
    if (-not (Test-Path "$ProjectRoot\.venv")) {
        Write-I "Creating virtualenv..."
        python -m venv "$ProjectRoot\.venv"
    }

    $venvPy = "$ProjectRoot\.venv\Scripts\python.exe"
    Write-I "Installing dependencies..."
    & $venvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { Write-E "pip upgrade failed" }
    & $venvPy -m pip install -r "$ProjectRoot\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Write-E "pip install requirements failed" }
    & $venvPy -m pip install -r "$ProjectRoot\web\backend\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Write-E "pip install web requirements failed" }

    # Frontend
    if (-not (Test-Path "$ProjectRoot\web\frontend\dist")) {
        if (Get-Command node -ErrorAction SilentlyContinue) {
            Write-I "Building frontend..."
            Push-Location "$ProjectRoot\web\frontend"
            if (-not (Test-Path node_modules)) { npm install --silent }
            npm run build
            Pop-Location
        }
        else {
            Write-W "Node.js not found, skipping frontend build"
        }
    }

    @("data", "logs", "plugins", "permissions") | ForEach-Object {
        if (-not (Test-Path "$ProjectRoot\$_")) {
            New-Item -ItemType Directory -Path "$ProjectRoot\$_" -Force | Out-Null
        }
    }

    Write-I "Deployment ready. Start command:"
    Write-Host ""
    Write-Host "  Production:"
    Write-Host "    .\.venv\Scripts\python.exe -m uvicorn web.backend.main:app --host 0.0.0.0 --port 8080"
    Write-Host ""
    Write-Host "  Development:"
    Write-Host "    .\scripts\start.bat"
}

# ------------------------------------------------------------------ #
# Entry
# ------------------------------------------------------------------ #
Write-Host ""
Write-Host "  === MisMiss Deploy Tool (Windows) ==="
Write-Host ""

if ($Mode -eq "") {
    Write-Host "Select deployment method:"
    Write-Host "  1) Docker  (recommended, isolated)"
    Write-Host "  2) Native  (venv)"
    $choice = Read-Host "Enter [1-2] (default=1)"
    switch ($choice) {
        ""   { $Mode = "Docker" }
        "1"  { $Mode = "Docker" }
        "2"  { $Mode = "Native" }
        default { Write-E "Invalid choice" }
    }
}

switch ($Mode) {
    "Docker" { Deploy-Docker }
    "Native" { Deploy-Native }
}

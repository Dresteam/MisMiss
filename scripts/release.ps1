# ============================================================
# MisMiss -- Release Build Script (Windows)
# ============================================================
# Builds all distribution formats for a GitHub release.
#
# Usage:
#   powershell -File scripts/release.ps1
#   powershell -File scripts/release.ps1 -Version 1.2.0
#   powershell -File scripts/release.ps1 -SkipPyInstaller
# ============================================================

param(
    [string]$Version = "",
    [switch]$SkipDocker,
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$DistDir    = "$ProjectRoot\dist"
$ReleaseDir = "$ProjectRoot\release"

# ------------------------------------------------------------------ #
# Version detection
# ------------------------------------------------------------------ #
if (-not $Version) {
    $Version = (Get-Date -Format "yyyy.M.d")
}

$ArchiveName = "mismiss-$Version"
$VersionClean = $Version -replace '[^0-9.]', ''

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host "   MisMiss Release Builder v$Version"         -ForegroundColor Cyan
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
function Write-Step { Write-Host "[$((Get-Date -Format 'HH:mm:ss'))] $args" -ForegroundColor Cyan }
function Write-OK   { Write-Host "         -> $args" -ForegroundColor Green }
function Write-ERR  { Write-Host "ERROR: $args" -ForegroundColor Red; exit 1 }

function Check([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-ERR "$Name is required but not found"
    }
}

# ------------------------------------------------------------------ #
# Prepare
# ------------------------------------------------------------------ #
Write-Step "Preparing release directory..."

if (Test-Path $ReleaseDir) { Remove-Item -Recurse -Force $ReleaseDir }
New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null

# Clean build cache but keep dist
if (Test-Path "$ProjectRoot\build") { Remove-Item -Recurse -Force "$ProjectRoot\build" }

# ------------------------------------------------------------------ #
# 1. Build frontend
# ------------------------------------------------------------------ #
Write-Step "[1/5] Building frontend ..."
Check node; Check npm

Push-Location "$ProjectRoot\web\frontend"
if (-not (Test-Path node_modules)) { npm ci --silent }
npm run build
if ($LASTEXITCODE -ne 0) { Write-ERR "Frontend build failed" }
Pop-Location

Write-OK "dist ready"

# ------------------------------------------------------------------ #
# 2. Source archives (.zip + .tar.gz)
# ------------------------------------------------------------------ #
Write-Step "[2/5] Building source archives ..."

$BuildDir = "$ProjectRoot\build\$ArchiveName"
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null

# Collect files
$copy = { param($src, $dst)
    if (Test-Path $src) {
        if ((Get-Item $src) -is [System.IO.DirectoryInfo]) {
            Copy-Item -Recurse $src $dst
        } else {
            Copy-Item $src $dst
        }
    }
}

# Source
& $copy "$ProjectRoot\src"               "$BuildDir\src"
& $copy "$ProjectRoot\web\backend"       "$BuildDir\web\backend"
& $copy "$ProjectRoot\web\frontend\dist" "$BuildDir\web\frontend\dist"
& $copy "$ProjectRoot\config.yml"        "$BuildDir\config.yml"
& $copy "$ProjectRoot\requirements.txt"  "$BuildDir\requirements.txt"
& $copy "$ProjectRoot\pyproject.toml"    "$BuildDir\pyproject.toml"
& $copy "$ProjectRoot\mismiss_cli.py"    "$BuildDir\mismiss_cli.py"
& $copy "$ProjectRoot\README.md"         "$BuildDir\README.md"

# Scripts
New-Item -ItemType Directory -Path "$BuildDir\scripts" -Force | Out-Null
Get-ChildItem "$ProjectRoot\scripts" | ForEach-Object {
    Copy-Item $_.FullName "$BuildDir\scripts\" -ErrorAction SilentlyContinue
}

# Runtime dirs
@("data", "logs", "plugins", "permissions") | ForEach-Object {
    New-Item -ItemType Directory -Path "$BuildDir\$_" -Force | Out-Null
}

# Clean caches
Get-ChildItem -Recurse -Directory -Filter "__pycache__" -Path $BuildDir -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

# Create archives
Push-Location "$ProjectRoot\build"
Compress-Archive -Path $ArchiveName -DestinationPath "$ReleaseDir\$ArchiveName.zip" -Force
if (Get-Command tar -ErrorAction SilentlyContinue) {
    tar -czf "$ReleaseDir\$ArchiveName.tar.gz" $ArchiveName
}
Pop-Location

$zipSize = (Get-Item "$ReleaseDir\$ArchiveName.zip").Length
Write-OK "source zip  ($('{0:N1}' -f ($zipSize / 1MB)) MB)"

# Clean up build dir for next step
Remove-Item -Recurse -Force $BuildDir

# ------------------------------------------------------------------ #
# 3. pip wheel
# ------------------------------------------------------------------ #
Write-Step "[3/5] Building pip wheel ..."
Check python

python -m pip install -q --upgrade pip build 2>$null
python -m build --wheel --outdir "$ReleaseDir" "$ProjectRoot"
if ($LASTEXITCODE -ne 0) { Write-ERR "Wheel build failed" }

$whl = Get-ChildItem "$ReleaseDir\mismiss-*.whl" | Select-Object -First 1
Write-OK "wheel  ($('{0:N1}' -f ($whl.Length / 1MB)) MB)"

# ------------------------------------------------------------------ #
# 4. PyInstaller standalone
# ------------------------------------------------------------------ #
if ($SkipPyInstaller) {
    Write-Step "[4/5] PyInstaller -- SKIPPED"
} else {
    Write-Step "[4/5] Building PyInstaller standalone exe ..."
    Check python

    python -m pip install -q pyinstaller 2>$null

    python -m PyInstaller `
        --distpath "$ReleaseDir" `
        --workpath "$ProjectRoot\build\pyinstaller" `
        --specpath "$ProjectRoot\build" `
        --name "mismiss" `
        --onefile `
        --console `
        --clean `
        --add-data "$ProjectRoot\web\frontend\dist;web\frontend\dist" `
        --add-data "$ProjectRoot\config.yml;." `
        --add-data "$ProjectRoot\src;src" `
        --add-data "$ProjectRoot\web\backend;web\backend" `
        --hidden-import "core" `
        --hidden-import "core.server" `
        --hidden-import "core.bot.mis_bot" `
        --hidden-import "core.events.bus" `
        --hidden-import "core.livestream.mis_livestream" `
        --hidden-import "core.plugin.plugin_manager" `
        --hidden-import "core.network.client" `
        --hidden-import "core.logging" `
        --hidden-import "core.config" `
        --hidden-import "interfaces" `
        --hidden-import "interfaces.server" `
        --hidden-import "interfaces.bot.bot" `
        --hidden-import "interfaces.event.event" `
        --hidden-import "interfaces.plugin.plugin" `
        --hidden-import "uvicorn" `
        --hidden-import "uvicorn.loops.auto" `
        --hidden-import "uvicorn.protocols.http.auto" `
        --hidden-import "fastapi" `
        --hidden-import "websockets" `
        --hidden-import "httpx" `
        --hidden-import "brotli" `
        --hidden-import "loguru" `
        --hidden-import "yaml" `
        --exclude-module "pip" `
        --exclude-module "pip._vendor" `
        --exclude-module "pip._internal" `
        --collect-all "fastapi" `
        --collect-all "uvicorn" `
        "$ProjectRoot\scripts\pyinstaller_entry.py"

    if ($LASTEXITCODE -ne 0) { Write-ERR "PyInstaller build failed" }

    $exe = Get-ChildItem "$ReleaseDir\mismiss.exe" | Select-Object -First 1
    Write-OK "exe  ($('{0:N1}' -f ($exe.Length / 1MB)) MB)"
}

# ------------------------------------------------------------------ #
# 5. Checksums
# ------------------------------------------------------------------ #
Write-Step "[5/5] Generating checksums ..."

Push-Location $ReleaseDir
$checksumFile = "checksums_${VersionClean}.txt"
Get-ChildItem -File | Where-Object { $_.Name -ne $checksumFile } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    "$hash  $($_.Name)" | Out-File -Append -Encoding utf8 $checksumFile
}
Pop-Location

Write-OK "SHA256 checksums"

# ------------------------------------------------------------------ #
# Done
# ------------------------------------------------------------------ #
$releaseSize = (Get-ChildItem -Recurse $ReleaseDir | Measure-Object -Property Length -Sum).Sum

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host "   RELEASE v$Version BUILD COMPLETE"           -ForegroundColor Green
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output: $ReleaseDir" -ForegroundColor White
Write-Host "  Size:   $('{0:N1}' -f ($releaseSize / 1MB)) MB" -ForegroundColor White
Write-Host ""
Get-ChildItem $ReleaseDir | ForEach-Object {
    $size = '{0:N1} MB' -f ($_.Length / 1MB)
    Write-Host "    $($_.Name.PadRight(36)) $size" -ForegroundColor White
}
Write-Host ""
Write-Host "  Draft release notes:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  ## v$Version" -ForegroundColor White

# Generate asset markdown
Get-ChildItem $ReleaseDir -File | Where-Object { $_.Name -match '\.(zip|gz|whl|exe)$' } | ForEach-Object {
    $size = '{0:N1} MB' -f ($_.Length / 1MB)
    Write-Host "  | $($_.Name) | $size |" -ForegroundColor White
}

# ============================================================
# MisMiss -- Release Build Script (Windows)
# ============================================================
# Builds all distribution formats for a GitHub release.
#
# Naming: mismiss-<version>[-<platform>].<ext>
#
# Usage:
#   powershell -File scripts/release.ps1
#   powershell -File scripts/release.ps1 -Version 1.1.0
#   powershell -File scripts/release.ps1 -SkipPyInstaller
#   powershell -File scripts/release.ps1 -SkipDocker
# ============================================================

param(
    [string]$Version = "",
    [switch]$SkipDocker,
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot  = Resolve-Path "$ScriptDir\.."
$DistDir      = "$ProjectRoot\dist"
$ReleaseDir   = "$ProjectRoot\release"

# ------------------------------------------------------------------ #
# Version detection
# ------------------------------------------------------------------ #
function Get-ProjectVersion {
    # 1. CLI parameter
    if ($Version) { return $Version }

    # 2. pyproject.toml
    $pyproject = "$ProjectRoot\pyproject.toml"
    if (Test-Path $pyproject) {
        $match = Select-String -Path $pyproject -Pattern 'version\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match -and $match.Matches.Count -gt 0) {
            return $match.Matches[0].Groups[1].Value
        }
    }

    # 3. Git tag
    $gitTag = git -C $ProjectRoot describe --tags --abbrev=0 2>$null
    if ($gitTag) { return $gitTag -replace '^v', '' }

    # 4. Date fallback
    return (Get-Date -Format "yyyy.M.d")
}

function Get-ShortHash {
    $hash = git -C $ProjectRoot rev-parse --short=7 HEAD 2>$null
    if ($hash) { return $hash }
    return ""
}

$Version = Get-ProjectVersion
$ShortHash = Get-ShortHash

# SemVer clean: strip leading 'v', preserve pre-release (-beta.2) and build (+hash)
$SemVer = $Version -replace '^v', '' -replace '\s', ''
$IsDev = $SemVer -notmatch '^\d+\.\d+\.\d+'  # non-SemVer = date-based dev build

# ------------------------------------------------------------------ #
# Platform detection (for PyInstaller)
# ------------------------------------------------------------------ #
if ($IsWindows) { $Platform = "win" }
elseif ($IsLinux) { $Platform = "linux" }
elseif ($IsMacOS) { $Platform = "macos" }
else { $Platform = "win" }

# ------------------------------------------------------------------ #
# Archive names
# ------------------------------------------------------------------ #
$SrcName     = "mismiss-$SemVer"
$ExeName     = if ($ShortHash) { "mismiss-${SemVer}-win-${ShortHash}" } else { "mismiss-${SemVer}-win" }
$WheelPrefix = "mismiss-$SemVer"

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Cyan
Write-Host "   MisMiss Release Builder"                   -ForegroundColor Cyan
Write-Host "   Version: $Version"                         -ForegroundColor Cyan
if ($ShortHash) { Write-Host "   Commit:  $ShortHash" -ForegroundColor Cyan }
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
if (Test-Path "$ProjectRoot\build") { Remove-Item -Recurse -Force "$ProjectRoot\build" }

# ------------------------------------------------------------------ #
# 1. Build frontend
# ------------------------------------------------------------------ #
Write-Step "[1/6] Building frontend ..."
Check node; Check npm

Push-Location "$ProjectRoot\web\frontend"
if (-not (Test-Path node_modules)) { npm ci --silent }
npm run build
if ($LASTEXITCODE -ne 0) { Write-ERR "Frontend build failed" }
Pop-Location
Write-OK "dist ready"

# ------------------------------------------------------------------ #
# 2. Source archives (.tar.gz + .zip)
# ------------------------------------------------------------------ #
Write-Step "[2/6] Building source archives ..."

$BuildDir = "$ProjectRoot\build\$SrcName"
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

& $copy "$ProjectRoot\src"               "$BuildDir\src"
& $copy "$ProjectRoot\web\backend"       "$BuildDir\web\backend"
& $copy "$ProjectRoot\web\frontend\dist" "$BuildDir\web\frontend\dist"
& $copy "$ProjectRoot\config.yml"        "$BuildDir\config.yml"
& $copy "$ProjectRoot\requirements.txt"  "$BuildDir\requirements.txt"
& $copy "$ProjectRoot\pyproject.toml"    "$BuildDir\pyproject.toml"
& $copy "$ProjectRoot\mismiss_cli.py"    "$BuildDir\mismiss_cli.py"
& $copy "$ProjectRoot\README.md"         "$BuildDir\README.md"

New-Item -ItemType Directory -Path "$BuildDir\scripts" -Force | Out-Null
Get-ChildItem "$ProjectRoot\scripts" | ForEach-Object {
    Copy-Item $_.FullName "$BuildDir\scripts\" -ErrorAction SilentlyContinue
}

@("data", "logs", "plugins", "permissions") | ForEach-Object {
    New-Item -ItemType Directory -Path "$BuildDir\$_" -Force | Out-Null
}

Get-ChildItem -Recurse -Directory -Filter "__pycache__" -Path $BuildDir -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

# Create archives
Push-Location "$ProjectRoot\build"
Compress-Archive -Path $SrcName -DestinationPath "$ReleaseDir\$SrcName.zip" -Force
if (Get-Command tar -ErrorAction SilentlyContinue) {
    tar -czf "$ReleaseDir\$SrcName.tar.gz" $SrcName
}
Pop-Location

$zipSize = (Get-Item "$ReleaseDir\$SrcName.zip").Length
Write-OK "source zip     $SrcName.zip  ($('{0:N1}' -f ($zipSize / 1MB)) MB)"

Remove-Item -Recurse -Force $BuildDir

# ------------------------------------------------------------------ #
# 3. pip wheel
# ------------------------------------------------------------------ #
Write-Step "[3/6] Building pip wheel ..."
Check python

python -m pip install -q --upgrade pip build 2>$null
python -m build --wheel --outdir "$ReleaseDir" "$ProjectRoot"
if ($LASTEXITCODE -ne 0) { Write-ERR "Wheel build failed" }

$whl = Get-ChildItem "$ReleaseDir\mismiss-*-py3-none-any.whl" | Select-Object -First 1

# PEP 427 normalizes 1.0.0-beta.2 → 1.0.0b2, rename to SemVer
$whlSemVer = "mismiss-${SemVer}-py3-none-any.whl"
if ($whl.Name -ne $whlSemVer) {
    Rename-Item -Path $whl.FullName -NewName $whlSemVer
    $whl = Get-Item "$ReleaseDir\$whlSemVer"
}

Write-OK "wheel          $($whl.Name)  ($('{0:N1}' -f ($whl.Length / 1MB)) MB)"

# ------------------------------------------------------------------ #
# 4. PyInstaller standalone
# ------------------------------------------------------------------ #
if ($SkipPyInstaller) {
    Write-Step "[4/5] PyInstaller -- SKIPPED"
} else {
    Write-Step "[4/6] Building PyInstaller standalone exe ..."
    Check python

    python -m pip install -q pyinstaller 2>$null

    python -m PyInstaller `
        --distpath "$ReleaseDir" `
        --workpath "$ProjectRoot\build\pyinstaller" `
        --specpath "$ProjectRoot\build" `
        --name "$ExeName" `
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

    $exe = Get-ChildItem "$ReleaseDir\$ExeName.exe" | Select-Object -First 1
    Write-OK "exe            $($exe.Name)  ($('{0:N1}' -f ($exe.Length / 1MB)) MB)"
}

# ------------------------------------------------------------------ #
# 5. Docker deploy package (via docker-release.ps1)
# ------------------------------------------------------------------ #
if ($SkipDocker) {
    Write-Step "[5/6] Docker package -- SKIPPED"
} else {
    Write-Step "[5/6] Building Docker deploy package ..."
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "         WARN: Docker not found, skipping" -ForegroundColor Yellow
    } else {
        & powershell -File "$ProjectRoot\scripts\docker-release.ps1" -Version $SemVer
        if ($LASTEXITCODE -ne 0) { Write-ERR "Docker package build failed" }

        foreach ($dockerFile in @("mismiss-${SemVer}-docker.zip", "mismiss-${SemVer}-docker.tar.gz")) {
            if (Test-Path "$ProjectRoot\dist\$dockerFile") {
                Copy-Item "$ProjectRoot\dist\$dockerFile" "$ReleaseDir\"
                $dockerSize = (Get-Item "$ReleaseDir\$dockerFile").Length
                Write-OK "docker pkg    $dockerFile  ($('{0:N1}' -f ($dockerSize / 1MB)) MB)"
            }
        }
    }
}

# ------------------------------------------------------------------ #
# 6. Checksums
# ------------------------------------------------------------------ #
Write-Step "[6/6] Generating checksums ..."

$ChecksumName = "checksums-${SemVer}.txt"
Push-Location $ReleaseDir
Get-ChildItem -File | Where-Object { $_.Name -ne $ChecksumName } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    "$hash  $($_.Name)" | Out-File -Append -Encoding utf8 $ChecksumName
}
Pop-Location
Write-OK "checksums     $ChecksumName"

# ------------------------------------------------------------------ #
# Done
# ------------------------------------------------------------------ #
$releaseSize = (Get-ChildItem -Recurse $ReleaseDir | Measure-Object -Property Length -Sum).Sum

Write-Host ""
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host "   RELEASE BUILD COMPLETE"                    -ForegroundColor Green
Write-Host "  ==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Output: $ReleaseDir" -ForegroundColor White
Write-Host "  Size:   $('{0:N1}' -f ($releaseSize / 1MB)) MB" -ForegroundColor White
Write-Host ""
Get-ChildItem $ReleaseDir -File | ForEach-Object {
    $size = '{0:N1} MB' -f ($_.Length / 1MB)
    Write-Host "    $($_.Name.PadRight(44)) $size" -ForegroundColor White
}
Write-Host ""

# Markdown table for GitHub Release
Write-Host "  --- Release notes table ---" -ForegroundColor Cyan
Get-ChildItem $ReleaseDir -File | Where-Object { $_.Name -notmatch '^checksums' } | ForEach-Object {
    $size = '{0:N1} MB' -f ($_.Length / 1MB)
    Write-Host "  | $($_.Name) | $size |" -ForegroundColor White
}

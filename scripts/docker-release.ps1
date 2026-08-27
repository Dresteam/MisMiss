# ============================================================
# MisMiss -- Docker image build & package (Windows)
# ============================================================
# Usage:
#   powershell -File scripts/docker-release.ps1
#   powershell -File scripts/docker-release.ps1 -Version 1.2.0
#
# Version detection (same as release.ps1): -Version -> pyproject.toml -> git tag -> date
#
# Output: dist/mismiss-<version>-docker.zip (naming matches release/ artifacts)
#   Contains: mismiss-docker.tar.gz (image), docker-compose.yml,
#             nginx.conf, config.yml.dist, deploy.sh
# ============================================================

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."

# ------------------------------------------------------------------ #
# Version detection (same priority as release.ps1)
# ------------------------------------------------------------------ #
if (-not $Version) {
    # pyproject.toml
    $pyproject = "$ProjectRoot\pyproject.toml"
    if (Test-Path $pyproject) {
        $match = Select-String -Path $pyproject -Pattern 'version\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($match -and $match.Matches.Count -gt 0) { $Version = $match.Matches[0].Groups[1].Value }
    }
}
if (-not $Version) {
    # Git tag
    $gitTag = git -C $ProjectRoot describe --tags --abbrev=0 2>$null
    if ($gitTag) { $Version = $gitTag -replace '^v', '' }
}
if (-not $Version) {
    # Date fallback
    $Version = Get-Date -Format "yyyy.M.d"
}

$SemVer = $Version -replace '^v', '' -replace '\s', ''
$PkgName = "mismiss-$SemVer-docker"
$BuildDir = "$ProjectRoot\build\docker\$PkgName"
$DistDir = "$ProjectRoot\dist"

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #
function Write-I { Write-Host "[INFO]  $args" -ForegroundColor Green }
function Write-S { Write-Host "[STEP]  $args" -ForegroundColor Cyan }
function Write-W { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-E { Write-Host "[ERROR] $args" -ForegroundColor Red; exit 1 }

function Get-Size($Path) {
    if (Test-Path $Path) { "{0:N1} MB" -f ((Get-Item $Path).Length / 1MB) } else { "N/A" }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-E "Docker is required" }

# ------------------------------------------------------------------ #
# 1. Build image + export classic docker archive
# ------------------------------------------------------------------ #
Write-S "Building image and exporting archive ..."
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

$tarPath = "$BuildDir\mismiss-docker.tar"

# 优先 buildx 导出经典 docker 格式归档：
# 不受 Docker Desktop "containerd 镜像存储" 影响，任何版本服务器 docker load 均可导入
$built = $false
docker buildx version 2>$null
if ($LASTEXITCODE -eq 0) {
    docker buildx build -t mismiss:latest --build-arg MISMISS_VERSION=$SemVer --output type=docker,dest=$tarPath "$ProjectRoot"
    $built = ($LASTEXITCODE -eq 0)
}
if (-not $built) {
    Write-W "buildx unavailable/failed, falling back to docker build + docker save"
    docker build -t mismiss:latest --build-arg MISMISS_VERSION=$SemVer "$ProjectRoot"
    if ($LASTEXITCODE -ne 0) { Write-E "Docker build failed" }
    docker save mismiss:latest -o $tarPath
    if ($LASTEXITCODE -ne 0) { Write-E "docker save failed" }
}

# 本地也保留镜像，便于 docker compose 快速测试
docker load -qi $tarPath 2>$null

# gzip 直接压缩 docker 归档（gz 内部即 docker save 格式，服务器 docker load 可直接读取）
Write-S "Compressing image archive ..."
$gzPath = "$BuildDir\mismiss-docker.tar.gz"
$inStream  = [System.IO.File]::OpenRead($tarPath)
$outStream = [System.IO.File]::Create($gzPath)
$gzip = New-Object System.IO.Compression.GZipStream($outStream, [System.IO.Compression.CompressionMode]::Compress)
$inStream.CopyTo($gzip)
$gzip.Dispose(); $outStream.Dispose(); $inStream.Dispose()
Remove-Item $tarPath

# ------------------------------------------------------------------ #
# 2. Collect deploy files
# ------------------------------------------------------------------ #
Write-S "Collecting deploy files ..."

Copy-Item "$ProjectRoot\docker-compose.yml"                $BuildDir
Copy-Item "$ProjectRoot\nginx.conf"                        $BuildDir
Copy-Item "$ProjectRoot\config.yml"                        "$BuildDir\config.yml.dist"
Copy-Item "$ProjectRoot\scripts\docker-server-deploy.sh"   "$BuildDir\deploy.sh"

Write-W "config.yml.dist comes from dev machine config - ensure no secrets inside"

# ------------------------------------------------------------------ #
# 3. Package zip
# ------------------------------------------------------------------ #
Write-S "Packaging -> $DistDir\$PkgName.zip"
if (Test-Path "$DistDir\$PkgName.zip") { Remove-Item -Force "$DistDir\$PkgName.zip" }
Compress-Archive -Path $BuildDir -DestinationPath "$DistDir\$PkgName.zip"

Write-Host ""
Write-I "Package ready: $DistDir\$PkgName.zip ($(Get-Size "$DistDir\$PkgName.zip"))"
Write-Host ""
Write-I "Server deployment:"
Write-Host ""
Write-Host "  # 1. Upload (scp / SFTP)"
Write-Host "  scp dist\$PkgName.zip user@server:/opt/mismiss/"
Write-Host ""
Write-Host "  # 2. Unzip and deploy on server"
Write-Host "  cd /opt/mismiss && unzip $PkgName.zip && cd $PkgName"
Write-Host "  bash deploy.sh"
Write-Host ""
Write-I "Update: overwrite deploy dir with new package, run bash deploy.sh again"

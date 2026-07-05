# ============================================================
# MisMiss -- Build Script (Windows)
# ============================================================
# Usage:
#   powershell -File scripts/build.ps1
#   powershell -File scripts/build.ps1 -Mode Archive
#   powershell -File scripts/build.ps1 -Mode Exe
# ============================================================

param(
    [ValidateSet("Archive", "Wheel", "Exe", "All", "Clean")]
    [string]$Mode = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."
$Version = if ($env:MISMISS_VERSION) { $env:MISMISS_VERSION } else { "1.0.0" }
$ReleaseName = "mismiss-$Version"
$BuildDir = "$ProjectRoot\build\$ReleaseName"
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

# ------------------------------------------------------------------ #
# Clean
# ------------------------------------------------------------------ #
function Invoke-Clean {
    if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
    New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
    if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir -Force | Out-Null }
}

# ------------------------------------------------------------------ #
# 1. Build frontend
# ------------------------------------------------------------------ #
function Build-Frontend {
    Write-S "Building frontend (React + Vite) ..."
    Push-Location "$ProjectRoot\web\frontend"

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-E "Node.js is required" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue))  { Write-E "npm is required" }

    if (-not (Test-Path "node_modules")) {
        Write-I "Installing frontend dependencies..."
        npm ci --silent 2>$null
        if ($LASTEXITCODE -ne 0) { npm install --silent }
    }

    npm run build
    if ($LASTEXITCODE -ne 0) { Write-E "Frontend build failed" }

    Pop-Location
    Write-I "Frontend built -> web\frontend\dist\"
}

# ------------------------------------------------------------------ #
# 2. Collect distribution files
# ------------------------------------------------------------------ #
function Collect-Files {
    Write-S "Collecting files -> $BuildDir\"

    # Python source
    Copy-Item -Recurse "$ProjectRoot\src"                "$BuildDir\src"

    # Web backend
    New-Item -ItemType Directory -Path "$BuildDir\web\backend" -Force | Out-Null
    Get-ChildItem "$ProjectRoot\web\backend" -Filter "*.py" -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item $_.FullName "$BuildDir\web\backend\" }
    if (Test-Path "$ProjectRoot\web\backend\api") {
        Copy-Item -Recurse "$ProjectRoot\web\backend\api" "$BuildDir\web\backend\api"
    }

    # Frontend dist (pre-built)
    New-Item -ItemType Directory -Path "$BuildDir\web\frontend\dist" -Force | Out-Null
    Copy-Item -Recurse "$ProjectRoot\web\frontend\dist\*" "$BuildDir\web\frontend\dist\"

    # Runtime files
    Copy-Item "$ProjectRoot\config.yml"                  "$BuildDir\"
    Copy-Item "$ProjectRoot\requirements.txt"            "$BuildDir\"
    Copy-Item "$ProjectRoot\pyproject.toml"              "$BuildDir\"
    Copy-Item "$ProjectRoot\mismiss_cli.py"              "$BuildDir\"

    # Scripts
    Copy-Item "$ProjectRoot\scripts\start.sh"            "$BuildDir\" -ErrorAction SilentlyContinue
    Copy-Item "$ProjectRoot\scripts\start.bat"           "$BuildDir\"
    Copy-Item "$ProjectRoot\scripts\deploy.sh"           "$BuildDir\" -ErrorAction SilentlyContinue
    Copy-Item "$ProjectRoot\scripts\deploy.ps1"          "$BuildDir\"

    # Docs
    Copy-Item "$ProjectRoot\README.md"                   "$BuildDir\"

    # Runtime empty dirs
    @("data", "logs", "plugins", "permissions") | ForEach-Object {
        New-Item -ItemType Directory -Path "$BuildDir\$_" -Force | Out-Null
    }

    # Clean Python cache
    Get-ChildItem -Recurse -Directory -Filter "__pycache__" -Path $BuildDir -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -Recurse -Force $_.FullName }

    Write-I "Files collected ($(Get-Size $BuildDir))"
}

# ------------------------------------------------------------------ #
# 3. Create archives
# ------------------------------------------------------------------ #
function New-Archives {
    Write-S "Creating archives -> $DistDir\"

    Push-Location "$ProjectRoot\build"

    Write-I "Creating ${ReleaseName}.zip ..."
    Compress-Archive -Path $ReleaseName -DestinationPath "$DistDir\${ReleaseName}.zip" -Force

    if (Get-Command tar -ErrorAction SilentlyContinue) {
        Write-I "Creating ${ReleaseName}.tar.gz ..."
        tar -czf "$DistDir\${ReleaseName}.tar.gz" $ReleaseName
    }

    Pop-Location

    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Green
    Write-Host "         BUILD SUCCESS"                   -ForegroundColor Green
    Write-Host "  ======================================" -ForegroundColor Green
    Get-ChildItem "$DistDir\${ReleaseName}.*" | ForEach-Object {
        Write-Host "  $($_.Name)  ($(Get-Size $_.FullName))" -ForegroundColor White
    }
    Write-Host ""

    Write-I "How to deploy:"
    Write-Host ""
    Write-Host "  1. Extract ${ReleaseName}.zip"
    Write-Host "  2. cd ${ReleaseName}"
    Write-Host "  3. pip install -r requirements.txt"
    Write-Host "     pip install fastapi `"uvicorn[standard]`" pydantic python-multipart"
    Write-Host "  4. start.bat prod"
    Write-Host "  5. Open http://localhost:8080"
}

# ------------------------------------------------------------------ #
# Helper: run external command, fail on non-zero exit
# ------------------------------------------------------------------ #
function Invoke-Cmd([string]$Cmd) {
    Write-I "Running: $Cmd"
    $script:ErrorActionPreference = "Continue"
    Invoke-Expression $Cmd
    if ($LASTEXITCODE -ne 0) { Write-E "Command failed (exit $LASTEXITCODE): $Cmd" }
    $script:ErrorActionPreference = "Stop"
}

# ------------------------------------------------------------------ #
# 4. pip wheel
# ------------------------------------------------------------------ #
function Build-Wheel {
    Write-S "Building pip wheel ..."

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-E "Python is required" }

    python -m pip install --upgrade pip build
    if ($LASTEXITCODE -ne 0) { Write-E "pip install build failed" }

    python -m build --wheel --outdir "$DistDir" "$ProjectRoot"
    if ($LASTEXITCODE -ne 0) { Write-E "wheel build failed" }

    $whl = Get-ChildItem "$DistDir\mismiss-*.whl" | Select-Object -First 1
    Write-Host ""
    Write-I "Wheel: $($whl.Name)  ($(Get-Size $whl.FullName))"
    Write-Host ""
    Write-I "Install: pip install mismiss-${Version}-py3-none-any.whl[web]"
}

# ------------------------------------------------------------------ #
# 5. PyInstaller standalone executable
# ------------------------------------------------------------------ #
function Build-PyInstaller {
    Write-S "Building PyInstaller standalone executable ..."

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-E "Python is required" }

    # Ensure frontend is built
    if (-not (Test-Path "$ProjectRoot\web\frontend\dist")) {
        Build-Frontend
    }

    Write-I "Installing PyInstaller..."
    python -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { Write-E "Failed to install PyInstaller" }

    Write-I "Running PyInstaller (spec file mode, this may take a while)..."
    Push-Location $ProjectRoot
    python -m PyInstaller --distpath "$DistDir" --workpath "$ProjectRoot\build\pyinstaller" --clean mismiss.spec
    if ($LASTEXITCODE -ne 0) { Write-E "PyInstaller build failed (exit $LASTEXITCODE)" }
    Pop-Location

    $exe = if (Test-Path "$DistDir\mismiss.exe") { "$DistDir\mismiss.exe" } else { "$DistDir\mismiss" }

    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Green
    Write-Host "     PYINSTALLER BUILD DONE"              -ForegroundColor Green
    Write-Host "  ======================================" -ForegroundColor Green
    Write-Host "  $(Split-Path $exe -Leaf)  ($(Get-Size $exe))" -ForegroundColor White
    Write-Host ""

    Write-I "No Python/Node.js needed on target machine:"
    Write-Host "  $exe"
    Write-Host "  $exe --port 9000"
}

# ------------------------------------------------------------------ #
# Entry
# ------------------------------------------------------------------ #
function Main {
    Write-Host ""
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host "     MisMiss Build Tool v$Version"        -ForegroundColor Cyan
    Write-Host "  ======================================" -ForegroundColor Cyan
    Write-Host ""

    if ($Mode -eq "") {
        Write-Host "Select build target:"
        Write-Host "  1) archive  -- .tar.gz + .zip distribution"
        Write-Host "  2) wheel    -- pip wheel (.whl)"
        Write-Host "  3) exe      -- PyInstaller standalone executable"
        Write-Host "  4) all      -- archive + wheel"
        $choice = Read-Host "Enter number [1-4] (default=1)"
        switch ($choice) {
            ""   { $Mode = "Archive" }
            "1"  { $Mode = "Archive" }
            "2"  { $Mode = "Wheel" }
            "3"  { $Mode = "Exe" }
            "4"  { $Mode = "All" }
            default { Write-E "Invalid choice" }
        }
    }

    switch ($Mode) {
        "Archive" { Invoke-Clean; Build-Frontend; Collect-Files; New-Archives }
        "Wheel"   { Build-Wheel }
        "Exe"     { Build-PyInstaller }
        "All"     {
            Invoke-Clean; Build-Frontend; Collect-Files; New-Archives; Build-Wheel
            Write-W "Tip: PyInstaller build separately: .\scripts\build.ps1 -Mode Exe"
        }
        "Clean"   {
            Write-S "Cleaning build artifacts..."
            @("$ProjectRoot\build", "$ProjectRoot\dist") | ForEach-Object {
                if (Test-Path $_) { Remove-Item -Recurse -Force $_ }
            }
            Write-I "Cleaned build/ and dist/"
        }
    }
}

Main

@echo off
title MisMiss Web Console
cd /d "%~dp0"

:: ------------------------------------------------------------------ %
:: Ports (env var overrides)
:: ------------------------------------------------------------------ %
if not defined MISMISS_API_PORT set MISMISS_API_PORT=18080
if not defined MISMISS_WEB_PORT set MISMISS_WEB_PORT=15173

:: ------------------------------------------------------------------ %
:: Mode detection
:: ------------------------------------------------------------------ %
set MODE=dev
if /i "%1"=="prod"  set MODE=prod
if /i "%1"=="build" set MODE=build

echo ========================================
if "%MODE%"=="dev"   echo   MisMiss - Development Mode
if "%MODE%"=="prod"  echo   MisMiss - Production Mode
if "%MODE%"=="build" echo   MisMiss - Build & Run
echo ========================================
echo.

:: ------------------------------------------------------------------ %
:: [build] Build frontend
:: ------------------------------------------------------------------ %
if "%MODE%"=="build" (
    echo [*] Building frontend...
    cd web\frontend
    call npm install
    call npm run build
    if %errorlevel% neq 0 ( echo [ERROR] Build failed & pause & exit /b 1 )
    cd ..\..
    echo [OK] Frontend built
    set MODE=prod
)

:: ------------------------------------------------------------------ %
:: [prod] Production mode - single port
:: ------------------------------------------------------------------ %
if "%MODE%"=="prod" (
    echo [*] Starting MisMiss on port %MISMISS_API_PORT%...
    echo [*] Web UI: http://localhost:%MISMISS_API_PORT%
    echo [*] API docs: http://localhost:%MISMISS_API_PORT%/docs
    echo.
    set MISMISS_PROD=1
    python -m web.backend.main --port %MISMISS_API_PORT%
    pause
    exit /b
)

:: ------------------------------------------------------------------ %
:: [dev] Development mode
:: ------------------------------------------------------------------ %
echo [1/3] Checking runtimes...

python --version >nul 2>&1 || (
    echo [*] Python not found, trying winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo [OK] Please re-run start.bat
    pause & exit /b 0
)

node --version >nul 2>&1 || (
    echo [*] Node.js not found, trying winget...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    echo [OK] Please re-run start.bat
    pause & exit /b 0
)

echo [2/3] Starting API (port %MISMISS_API_PORT%)...
start "MisMiss API" cmd /c "python -m web.backend.main --port %MISMISS_API_PORT%"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Web UI (port %MISMISS_WEB_PORT%)...
start "MisMiss Web" cmd /c "cd /d %~dp0web\frontend && npx vite --host 0.0.0.0 --port %MISMISS_WEB_PORT%"

echo.
echo ========================================
echo   Dev mode ready!
echo   Web UI: http://localhost:%MISMISS_WEB_PORT%
echo   API:    http://localhost:%MISMISS_API_PORT%/docs
echo ========================================
echo.
pause

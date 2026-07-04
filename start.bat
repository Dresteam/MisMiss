@echo off
title MisMiss Web Console
setlocal enabledelayedexpansion

echo ========================================
echo   MisMiss Web Console Launcher
echo ========================================
echo.

:: Check winget
winget --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] winget not found, cannot auto-install runtimes
)

:: Check / Install Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Python not found, installing via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Python install failed, please install manually
        pause
        exit /b 1
    )
    echo [OK] Python installed, please re-run this script
    pause
    exit /b 0
)

:: Check / Install Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Node.js not found, installing via winget...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Node.js install failed, please install manually
        pause
        exit /b 1
    )
    echo [OK] Node.js installed, please re-run this script
    pause
    exit /b 0
)

:: Ports (customize via env vars)
if not defined MISMISS_API_PORT set MISMISS_API_PORT=8000
if not defined MISMISS_WEB_PORT set MISMISS_WEB_PORT=5173

:: Install backend deps
echo [1/4] Checking backend dependencies...
pip show fastapi >nul 2>&1
if %errorlevel% neq 0 (
    echo    Installing backend dependencies...
    pip install -r web\backend\requirements.txt
)

:: Install frontend deps
echo [2/4] Checking frontend dependencies...
if not exist "web\frontend\node_modules" (
    echo    Installing frontend dependencies...
    cd web\frontend
    call npm install
    cd ..\..
)

:: Check if ports already in use
netstat -ano 2>nul | findstr ":%MISMISS_API_PORT% " | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [SKIP] Port %MISMISS_API_PORT% is already in use, backend may be running
    goto :start_frontend
)

:: Start backend
echo [3/4] Starting backend API (port %MISMISS_API_PORT%)...
start "MisMiss API" cmd /c "python -m web.backend.main --port %MISMISS_API_PORT%"
timeout /t 3 /nobreak >nul

:start_frontend
netstat -ano 2>nul | findstr ":%MISMISS_WEB_PORT% " | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [SKIP] Port %MISMISS_WEB_PORT% is already in use, frontend may be running
    goto :done
)

:: Start frontend
echo [4/4] Starting frontend (port %MISMISS_WEB_PORT%)...
start "MisMiss Web" cmd /c "cd web\frontend && npx vite --host 0.0.0.0 --port %MISMISS_WEB_PORT%"

:done

echo.
echo ========================================
echo   Startup complete!
echo   API : http://localhost:%MISMISS_API_PORT%/docs
echo   Web : http://localhost:%MISMISS_WEB_PORT%
echo ========================================
echo.
echo Close this window to keep services running.
pause >nul

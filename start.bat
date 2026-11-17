@echo off
title MisMiss Launcher
cd /d "%~dp0"

:: ------------------------------------------------------------------ %
:: Python interpreter - prefer the project venv
::   Using the system `python` can silently hit a Windows Store stub or a
::   clean interpreter without FastAPI. The venv is the supported runtime.
:: ------------------------------------------------------------------ %
set "PYTHON=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"

:: ------------------------------------------------------------------ %
:: Python / dependencies preflight
:: ------------------------------------------------------------------ %
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
    echo [*] Python not found, trying winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo [OK] Please re-run start.bat
    pause & exit /b 0
)
"%PYTHON%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python dependencies are missing for:
    echo         %PYTHON%
    echo [*] Install them with:
    echo         "%PYTHON%" -m pip install -r requirements.txt
    pause & exit /b 1
)

:: ------------------------------------------------------------------ %
:: Ports (env var overrides)
:: ------------------------------------------------------------------ %
if not defined MISMISS_API_PORT set MISMISS_API_PORT=18080
if not defined MISMISS_WEB_PORT set MISMISS_WEB_PORT=15173

:: ------------------------------------------------------------------ %
:: Port cleanup - 启动前清理占用端口的旧进程，防止重复启动
:: ------------------------------------------------------------------ %
call :cleanup_port %MISMISS_API_PORT% "MisMiss API"
call :cleanup_port %MISMISS_WEB_PORT% "MisMiss Web"

echo.

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
    if errorlevel 1 ( echo [ERROR] Build failed & pause & exit /b 1 )
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
    "%PYTHON%" -m web.backend.main --port %MISMISS_API_PORT%
    pause
    exit /b
)

:: ------------------------------------------------------------------ %
:: [dev] Development mode
:: ------------------------------------------------------------------ %
echo [1/3] Checking runtimes...

node --version >nul 2>&1 || (
    echo [*] Node.js not found, trying winget...
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
    echo [OK] Please re-run start.bat
    pause & exit /b 0
)

echo [2/3] Starting API (port %MISMISS_API_PORT%)...
start "MisMiss API" /d "%~dp0" cmd /c ""%PYTHON%" -m web.backend.main --port %MISMISS_API_PORT%"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Web UI (port %MISMISS_WEB_PORT%)...
start "MisMiss Web" /d "%~dp0web\frontend" cmd /c "npx vite --host 0.0.0.0 --port %MISMISS_WEB_PORT%"

echo.
echo ========================================
echo   Dev mode ready!
echo   Web UI: http://localhost:%MISMISS_WEB_PORT%
echo   API:    http://localhost:%MISMISS_API_PORT%/docs
echo ========================================
echo.
pause
exit /b 0

:: ------------------------------------------------------------------ %
:: cleanup_port <port> <window_title>
::   1. 按窗口标题关闭旧进程窗口
::   2. 查找占用端口的 LISTENING 进程并强制结束
:: ------------------------------------------------------------------ %
:cleanup_port
setlocal
set _PORT=%~1
set _TITLE=%~2

:: 1. 关闭同名窗口的旧进程
taskkill /f /fi "WINDOWTITLE eq %_TITLE%*" >nul 2>&1

:: 2. 查找占用端口的 PID 并结束
set _KILLED=0
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":%_PORT%" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%p >nul 2>&1
    if not errorlevel 1 set _KILLED=1
)
if "%_KILLED%"=="1" (
    echo [OK] Port %_PORT% cleared ^(old process stopped^)
) else (
    echo [OK] Port %_PORT% is free
)
endlocal & exit /b 0


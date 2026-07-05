@echo off
title MisMiss Web Console
setlocal enabledelayedexpansion

:: ============================================================
:: MisMiss — 启动脚本 (Windows)
:: ============================================================
:: 用法:
::   scripts\start.bat             开发模式
::   scripts\start.bat prod        生产模式
::   scripts\start.bat backend     仅后端
:: ============================================================

:: 切换到项目根目录
cd /d "%~dp0\.."

:: 参数解析
if /i "%~1"=="--prod"   goto :start_prod
if /i "%~1"=="prod"     goto :start_prod
if /i "%~1"=="--backend" goto :start_backend
if /i "%~1"=="backend"  goto :start_backend
goto :start_dev

:: ================================================================== %
:: 生产模式
:: ================================================================== %
:start_prod
echo [MODE] 生产模式
echo.

python --version >nul 2>&1 || (echo [ERROR] Python not found & pause & exit /b 1)

:: 安装依赖
echo [1/3] 安装后端依赖...
pip show fastapi >nul 2>&1 || (
    pip install -r requirements.txt
    pip install -r web\backend\requirements.txt
)
echo        Done.

:: 构建前端
echo [2/3] 构建前端...
cd web\frontend
if not exist "node_modules" (echo        安装前端依赖... & call npm install)
call npm run build
cd ..\..
echo        Done -^> web\frontend\dist\

:: 启动
set PORT=%MISMISS_API_PORT%
if "%PORT%"=="" set PORT=8080

echo [3/3] 启动服务 (port %PORT%)...
echo.
echo ========================================
echo   Web : http://localhost:%PORT%
echo   API : http://localhost:%PORT%/docs
echo ========================================
echo.
set MISMISS_PROD=1
python -m uvicorn web.backend.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:: ================================================================== %
:: 仅后端
:: ================================================================== %
:start_backend
echo [MODE] 仅后端 API
echo.

python --version >nul 2>&1 || (echo [ERROR] Python not found & pause & exit /b 1)

echo [*] 安装依赖...
pip show fastapi >nul 2>&1 || (
    pip install -r requirements.txt
    pip install -r web\backend\requirements.txt
)

set PORT=%MISMISS_API_PORT%
if "%PORT%"=="" set PORT=8080

echo [*] 启动 API (port %PORT%, --reload)...
echo ========================================
echo   API : http://localhost:%PORT%/docs
echo ========================================
python -m uvicorn web.backend.main:app --host 0.0.0.0 --port %PORT% --reload
goto :eof

:: ================================================================== %
:: 开发模式
:: ================================================================== %
:start_dev
echo [MODE] 开发模式
echo.

python --version >nul 2>&1 || (echo [ERROR] Python not found & pause & exit /b 1)
node  --version >nul 2>&1 || (echo [ERROR] Node.js not found & pause & exit /b 1)

set API_PORT=%MISMISS_API_PORT%
if "%API_PORT%"=="" set API_PORT=8080
set WEB_PORT=%MISMISS_WEB_PORT%
if "%WEB_PORT%"=="" set WEB_PORT=5173

:: 后端依赖
echo [1/4] 安装后端依赖...
pip show fastapi >nul 2>&1 || (
    pip install -r requirements.txt
    pip install -r web\backend\requirements.txt
)

:: 前端依赖
echo [2/4] 检查前端依赖...
if not exist "web\frontend\node_modules" (
    echo        安装前端依赖...
    cd web\frontend & call npm install & cd ..\..
)

:: 后端（检测端口）
netstat -ano 2>nul | findstr ":%API_PORT% " | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [SKIP] 端口 %API_PORT% 已占用，后端可能已运行
    goto :start_frontend
)

echo [3/4] 启动后端 (port %API_PORT%, --reload)...
start "MisMiss API" cmd /c "cd /d %CD% && python -m uvicorn web.backend.main:app --host 0.0.0.0 --port %API_PORT% --reload"
timeout /t 3 /nobreak >nul

:start_frontend
netstat -ano 2>nul | findstr ":%WEB_PORT% " | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [SKIP] 端口 %WEB_PORT% 已占用，前端可能已运行
    goto :done
)

echo [4/4] 启动前端 (port %WEB_PORT%)...
start "MisMiss Web" cmd /c "cd /d %CD%\web\frontend && npx vite --host 0.0.0.0 --port %WEB_PORT%"

:done
echo.
echo ========================================
echo   开发模式已启动
echo   API : http://localhost:%API_PORT%/docs
echo   Web : http://localhost:%WEB_PORT%
echo ========================================
echo.
echo 关闭此窗口不影响服务运行。
pause >nul

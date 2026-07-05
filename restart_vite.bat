@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":25173" ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
cd /d "E:\Projects\PyCharmProjects\MisMiss\web\frontend"
start "MisMiss Web" cmd /c "npx vite --host 0.0.0.0 --port 25173"

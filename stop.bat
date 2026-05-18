@echo off
title Auto-AT Stopper

echo.
echo  +--------------------------------------+
echo  ^|        Auto-AT Dev Stopper           ^|
echo  +--------------------------------------+
echo.

:: -- Kill backend (uvicorn on port 8000) -------------------------------------
echo [1/3] Stopping Backend   (port 8000) ...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo       Done.

:: -- Kill admin-app (Next.js on port 3001) ------------------------------------
echo [2/3] Stopping Admin App (port 3001) ...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo       Done.

:: -- Kill user-app (Next.js on port 3002) -------------------------------------
echo [3/3] Stopping User App  (port 3002) ...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3002 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo       Done.

echo.
echo  All Auto-AT services stopped.
echo.
pause

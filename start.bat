@echo off
title Auto-AT Launcher

echo.
echo  +--------------------------------------+
echo  ^|       Auto-AT Dev Launcher           ^|
echo  +--------------------------------------+
echo.

:: -- Paths -------------------------------------------------------------------
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"

:: -- Backend (conda activate + uv run uvicorn) --------------------------------
echo [1/3] Starting Backend   (http://localhost:8000) ...
start "Auto-AT Backend" cmd /k "title Auto-AT Backend && cd /d "%BACKEND%" && call conda activate auto-at && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: Small delay so the terminal titles don't overlap on open
timeout /t 2 /nobreak >nul

:: -- Admin App (Next.js on port 3001) -----------------------------------------
echo [2/3] Starting Admin App (http://localhost:3001) ...
start "Auto-AT Admin App" cmd /k "title Auto-AT Admin App && cd /d "%ROOT%" && npm run dev:admin"

:: Small delay
timeout /t 2 /nobreak >nul

:: -- User App (Next.js on port 3002) ------------------------------------------
echo [3/3] Starting User App  (http://localhost:3002) ...
start "Auto-AT User App" cmd /k "title Auto-AT User App && cd /d "%ROOT%" && npm run dev:user"

echo.
echo  All services are starting in separate windows.
echo  Backend   -^> http://localhost:8000
echo  Admin App -^> http://localhost:3001
echo  User App  -^> http://localhost:3002
echo  API Docs  -^> http://localhost:8000/docs
echo.
echo  Close this window or press any key to exit the launcher.
pause >nul

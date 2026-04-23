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
set "FRONTEND=%ROOT%frontend"

:: -- Backend (conda activate + uv run uvicorn) --------------------------------
echo [1/2] Starting Backend  (http://localhost:8000) ...
start "Auto-AT Backend" cmd /k "title Auto-AT Backend && cd /d "%BACKEND%" && call conda activate auto-at && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

:: Small delay so the terminal titles don't overlap on open
timeout /t 2 /nobreak >nul

:: -- Frontend (Next.js) ------------------------------------------------------
echo [2/2] Starting Frontend (http://localhost:3001) ...
start "Auto-AT Frontend" cmd /k "title Auto-AT Frontend && cd /d "%FRONTEND%" && npm run dev"

echo.
echo  Both services are starting in separate windows.
echo  Backend  -^> http://localhost:8000
echo  Frontend -^> http://localhost:3001
echo  API Docs -^> http://localhost:8000/docs
echo.
echo  Close this window or press any key to exit the launcher.
pause >nul

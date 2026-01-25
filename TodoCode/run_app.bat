@echo off
title My Focus - Starter
echo ==========================================
echo   Starting My Focus Application
echo ==========================================

echo.
echo [1/3] Starting Backend (Go)...
start "Backend" cmd /k "cd backend && go run main.go"

echo [2/3] Starting Frontend (Next.js)...
start "Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Waiting 5 seconds for servers to initialize...
timeout /t 5 /nobreak > nul

echo [3/3] Opening browser at http://localhost:3000...
start http://localhost:3000

echo.
echo ==========================================
echo   All systems GO! 
echo   Check the individual windows for logs.
echo ==========================================
pause

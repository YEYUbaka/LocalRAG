@echo off
setlocal

echo ========================================
echo   LocalRAG Startup
echo ========================================
echo.
echo   [1] Local Development (conda + npm)
echo   [2] Docker (docker-compose up)
echo.
set /p CHOICE="Select mode (1 or 2): "

if "%CHOICE%"=="2" goto :docker
if "%CHOICE%"=="1" goto :local
echo Invalid choice. Defaulting to local development.
goto :local

:local
echo.
echo Starting in local development mode...
echo.

set "PROJECT_DIR=%~dp0"

echo [1/2] Starting Backend (FastAPI)...
start "LocalRAG-Backend" cmd /k "cd /d "%PROJECT_DIR%backend" && conda run -n localrag --no-capture-output uvicorn app.main:app --reload --port 8000"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Frontend (Vite)...
start "LocalRAG-Frontend" cmd /k "cd /d "%PROJECT_DIR%frontend" && npm run dev"

echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo.
pause
goto :eof

:docker
echo.
echo Starting in Docker mode...
echo.

cd /d "%~dp0"

echo Building and starting containers...
docker-compose up --build -d

echo.
echo   Frontend: http://localhost
echo   Backend:  http://localhost:8000
echo.
echo Use "docker-compose logs -f" to view logs.
echo Use "docker-compose down" to stop.
echo.
pause
goto :eof

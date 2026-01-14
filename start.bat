@echo off
REM CARES Startup Script for Windows
REM Automatically manages PostgreSQL Docker, initializes database, and starts application

echo ============================================
echo CARES - Community Accounting System
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8 or later from:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking PostgreSQL Docker container...
docker ps -a --format "{{.Names}}" | findstr /C:"kofc-postgres" >nul 2>&1
if errorlevel 1 (
    echo Creating new PostgreSQL container...
    docker run --name kofc-postgres -e POSTGRES_PASSWORD=dev123 -e POSTGRES_DB=kofc_accounting -p 5432:5432 -d postgres:15-alpine
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create PostgreSQL container.
        echo.
        echo Please check:
        echo   1. Docker Desktop is installed and running
        echo   2. Port 5432 is not already in use
        echo.
        pause
        exit /b 1
    )
    echo PostgreSQL container created successfully!
) else (
    echo Starting existing PostgreSQL container...
    docker start kofc-postgres >nul 2>&1
    echo PostgreSQL container started!
)
echo.

echo [2/4] Waiting for PostgreSQL to be ready...
timeout /t 3 /nobreak >nul
echo PostgreSQL is ready!
echo.

echo [3/4] Initializing database...
python init_db.py
if errorlevel 1 (
    echo.
    echo ERROR: Database initialization failed.
    echo Please check the error messages above.
    echo.
    pause
    exit /b 1
)
echo.

echo [4/4] Starting Flask application...
echo.
echo ============================================
echo   CARES is running at:
echo   http://localhost:5000
echo.
echo   Default login credentials:
echo     Username: admin
echo     Password: admin123
echo.
echo   Press Ctrl+C to stop the server
echo ============================================
echo.

REM Set Flask environment variables
set FLASK_APP=app.py
set FLASK_ENV=development

REM Start Flask (using flask run to avoid double initialization)
python -m flask run --host=0.0.0.0 --port=5000

echo.
echo ============================================
echo Shutting down...
echo ============================================

REM Ask if user wants to stop PostgreSQL
echo.
set /p STOP_DB="Stop PostgreSQL container? (y/n): "
if /i "%STOP_DB%"=="y" (
    echo Stopping PostgreSQL container...
    docker stop kofc-postgres >nul 2>&1
    echo PostgreSQL container stopped.
) else (
    echo PostgreSQL container left running.
    echo To stop it later, run: docker stop kofc-postgres
)

echo.
echo Development session ended.
echo.
pause

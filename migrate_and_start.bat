@echo off
REM CARES Migrate and Start Script for Windows
REM Runs database migrations then starts the application
REM Safe to run multiple times - migrations are idempotent

echo ============================================
echo CARES - Community Accounting System
echo Migrate and Start
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

echo ============================================
echo Step 1: Managing PostgreSQL Database
echo ============================================
echo.

REM Check if PostgreSQL container exists
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
    echo Waiting for PostgreSQL to be ready...
    timeout /t 5 /nobreak >nul
) else (
    echo Starting existing PostgreSQL container...
    docker start kofc-postgres >nul 2>&1
    echo PostgreSQL container started!
    echo Waiting for PostgreSQL to be ready...
    timeout /t 3 /nobreak >nul
)

echo.

REM ============================================
REM Step 2: Run Database Migration
REM ============================================
echo ============================================
echo Step 2: Running database migrations...
echo ============================================
echo.

if exist migrate_production.py (
    python migrate_production.py
    if errorlevel 1 (
        echo.
        echo ERROR: Migration failed!
        echo Application will not start.
        echo Please check the error messages above.
        echo.
        pause
        exit /b 1
    )
    echo.
    echo Migration completed successfully
) else (
    echo WARNING: migrate_production.py not found
    echo   Skipping migration step
    echo   Database initialization will use init_db.py fallback
)

echo.

REM ============================================
REM Step 3: Initialize Database (if needed)
REM ============================================
echo ============================================
echo Step 3: Checking database initialization...
echo ============================================
echo.

if exist init_db.py (
    python init_db.py
    if errorlevel 1 (
        echo.
        echo ERROR: Database initialization failed!
        echo.
        pause
        exit /b 1
    )
) else (
    echo WARNING: init_db.py not found, skipping initialization
)

echo.

REM ============================================
REM Step 4: Start Application
REM ============================================
echo ============================================
echo Step 4: Starting Flask application...
echo ============================================
echo.
echo Application will be available at:
echo   http://localhost:5000
echo.
echo Default login credentials:
echo   Username: admin
echo   Password: admin123
echo.
echo Press Ctrl+C to stop the server
echo ============================================
echo.

REM Set Flask environment variables
set FLASK_APP=app.py
set FLASK_ENV=development

REM Start Flask (using flask run to avoid double initialization)
python -m flask run --host=0.0.0.0 --port=5000

REM ============================================
REM Cleanup on Exit
REM ============================================
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

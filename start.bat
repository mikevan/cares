@echo off
echo ========================================
echo CARES Development Environment Startup
echo ========================================
echo.

echo [1/3] Starting PostgreSQL Docker container...
docker start kofc-postgres 2>nul
if errorlevel 1 (
    echo Container doesn't exist. Creating new PostgreSQL container...
    docker run --name kofc-postgres -e POSTGRES_PASSWORD=dev123 -e POSTGRES_DB=kofc_accounting -p 5432:5432 -d postgres:15-alpine
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to start PostgreSQL container.
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
    echo PostgreSQL container started successfully!
)
echo.

echo [2/3] Waiting for PostgreSQL to be ready...
timeout /t 3 /nobreak >nul
echo PostgreSQL is ready!
echo.

echo [3/3] Starting Flask application...
echo.
echo ========================================
echo   CARES is running at:
echo   http://localhost:5000
echo.
echo   Press Ctrl+C to stop the server
echo ========================================
echo.

python app.py

echo.
echo ========================================
echo Shutting down...
echo ========================================
echo Stopping PostgreSQL container...
docker stop kofc-postgres >nul 2>&1
echo PostgreSQL container stopped.
echo.
echo Development session ended.
echo.
pause

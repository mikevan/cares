#!/bin/bash
# CARES Migrate and Start Script for Linux/Mac/Production
# Runs database migrations then starts the application
# Safe to run multiple times - migrations are idempotent

echo "============================================"
echo "CARES - Community Accounting System"
echo "Migrate and Start"
echo "============================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null
then
    echo "❌ Error: Python is not installed or not in PATH"
    exit 1
fi

# Use python3 if available, otherwise python
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "Using Python: $PYTHON_CMD"
echo ""

# ============================================
# STEP 1: Run Database Migration
# ============================================
echo "Step 1: Running database migrations..."
echo "----------------------------------------"

if [ -f "migrate_production.py" ]; then
    $PYTHON_CMD migrate_production.py
    MIGRATION_EXIT_CODE=$?
    
    if [ $MIGRATION_EXIT_CODE -ne 0 ]; then
        echo ""
        echo "❌ ERROR: Migration failed with exit code $MIGRATION_EXIT_CODE"
        echo "Application will not start. Please check the error messages above."
        exit $MIGRATION_EXIT_CODE
    fi
    
    echo ""
    echo "✓ Migration completed successfully"
else
    echo "⚠ Warning: migrate_production.py not found"
    echo "  Skipping migration step"
    echo "  Database initialization will use init_db.py fallback"
fi

echo ""

# ============================================
# STEP 2: Initialize Database (if needed)
# ============================================
echo "Step 2: Checking database initialization..."
echo "----------------------------------------"

if [ -f "init_db.py" ]; then
    $PYTHON_CMD init_db.py
    INIT_EXIT_CODE=$?
    
    if [ $INIT_EXIT_CODE -ne 0 ]; then
        echo ""
        echo "❌ ERROR: Database initialization failed"
        exit $INIT_EXIT_CODE
    fi
else
    echo "⚠ Warning: init_db.py not found, skipping initialization"
fi

echo ""

# ============================================
# STEP 3: Start Application
# ============================================

# Check if we're in production (Render.com or other hosting)
if [ "$RENDER" = "true" ] || [ "$PRODUCTION" = "true" ]; then
    echo "============================================"
    echo "Production Mode - Starting with Gunicorn"
    echo "============================================"
    echo ""
    
    # Check if gunicorn is available
    if ! command -v gunicorn &> /dev/null; then
        echo "❌ ERROR: gunicorn not found"
        echo "Install with: pip install gunicorn"
        exit 1
    fi
    
    # Start with gunicorn for production
    echo "Starting application..."
    echo "Port: ${PORT:-5000}"
    echo "Workers: 2"
    echo ""
    
    python migrate_production.py && python load_comprehensive_data.py && exec gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120
    
else
    # Development mode
    echo "============================================"
    echo "Development Mode - Starting Flask Server"
    echo "============================================"
    echo ""
    
    # Check if virtual environment exists
    if [ -d "venv" ]; then
        echo "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    echo "Application will be available at:"
    echo "  http://localhost:5000"
    echo ""
    echo "Default login credentials:"
    echo "  Username: admin"
    echo "  Password: admin123"
    echo ""
    echo "Press Ctrl+C to stop the server"
    echo "============================================"
    echo ""
    
    # Set Flask environment variables
    export FLASK_APP=app.py
    export FLASK_ENV=development
    
    # Start Flask development server
    $PYTHON_CMD -m flask run --host=0.0.0.0 --port=5000
fi

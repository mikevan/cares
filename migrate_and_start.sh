#!/bin/bash
# CARES Migrate and Start Script for Linux/Mac/Production
# Runs database migrations then starts the application
# Safe to run multiple times - migrations are idempotent
# Demo data is loaded ONLY when DEMO_MODE=true. A production update
# never reloads data -- see demo_guard.py.

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
    echo "⚠ Warning: migrate_production.py not found — skipping migration"
fi

echo ""

# ============================================
# STEP 2: Load Demo Data (blocking)
# ============================================
echo "Step 2: Loading demo data..."
echo "----------------------------------------"
echo "Loaded only when DEMO_MODE=true. A production update never reloads data."
echo ""

if [ "$DEMO_MODE" = "true" ]; then
    # Which demo dataset: the generic nonprofit book, or the Knights of
    # Columbus council book. Matches init_db.py's DEMO_DATASET handling.
    DEMO_LOADER="load_comprehensive_data.py"
    if [ "$DEMO_DATASET" = "kofc" ]; then
        DEMO_LOADER="load_kofc_form1295_demo_data.py"
    fi

    if [ -f "$DEMO_LOADER" ]; then
        echo "DEMO_MODE=true — loading $DEMO_LOADER (this WIPES existing data)."
        $PYTHON_CMD "$DEMO_LOADER"
        LOAD_EXIT_CODE=$?

        if [ $LOAD_EXIT_CODE -ne 0 ]; then
            echo ""
            echo "❌ ERROR: Demo data load failed with exit code $LOAD_EXIT_CODE"
            echo "Application will not start. Please check the error messages above."
            exit $LOAD_EXIT_CODE
        fi

        echo ""
        echo "✓ Demo data loaded successfully"
    else
        echo "⚠ Warning: $DEMO_LOADER not found — skipping demo data load"
    fi
else
    echo "Demo data load SKIPPED — DEMO_MODE is not \"true\"."
    echo "This is treated as a production update, and a production update never"
    echo "reloads data. Migrations above have been applied; existing data is"
    echo "untouched. Set DEMO_MODE=true (and DEMO_DATASET=kofc for the council"
    echo "book) on an instance that really is a demo."
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

    echo "Starting application..."
    echo "Port: ${PORT:-5000}"
    echo "Workers: 2"
    echo ""

    exec gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120

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

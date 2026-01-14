#!/bin/bash
# CARES Startup Script for Linux/Mac
# Automatically initializes database and loads sample data if needed

echo "============================================"
echo "CARES - Community Accounting System"
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

# Check if we're in production (Render.com or other hosting)
if [ "$RENDER" = "true" ] || [ "$PRODUCTION" = "true" ]; then
    echo "Production mode detected"
    
    # Initialize database (smart - only does what's needed)
    echo "Initializing database..."
    $PYTHON_CMD init_db.py
    
    # Start with gunicorn for production
    echo ""
    echo "Starting application with gunicorn..."
    exec gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 2
else
    # Development mode
    echo "Development mode"
    
    # Check if virtual environment exists
    if [ -d "venv" ]; then
        echo "Activating virtual environment..."
        source venv/bin/activate
    fi
    
    # Initialize database (smart - only does what's needed)
    echo "Initializing database..."
    $PYTHON_CMD init_db.py
    
    # Start Flask development server
    echo ""
    echo "============================================"
    echo "Starting development server..."
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
    
    # Start Flask
    $PYTHON_CMD -m flask run --host=0.0.0.0 --port=5000
fi

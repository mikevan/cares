#!/bin/bash
# Startup script for Render.com deployment
# Initializes database if needed, then starts the app

echo "Starting Knights of Columbus Accounting System..."

# Initialize database
python init_db.py

# Start the application
exec gunicorn app:app


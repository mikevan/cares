#!/bin/bash
set -euo pipefail
# Startup script for Render.com deployment
# Runs startup checks/migrations, initializes DB if needed, then starts the app

echo "Starting CARES - Community Accounting & Resource Engagement System..."

# Run startup migration script to ensure required schema exists
python scripts/startup_check_and_migrate.py

# Initialize database (create tables if missing)
python init_db.py

# Load the database if it is empty
python load_sample_data.py

# Start the application
exec gunicorn app:app


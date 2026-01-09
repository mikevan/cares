#!/bin/bash
# Startup script for Render.com deployment
# Initializes database if needed, then starts the app

echo "Starting CARES - Community Accounting & Resource Engagement System..."

# Initialize database
python init_db.py

# load the database if it is empty
python load_sample_data.py

# Start the application
exec gunicorn app:app


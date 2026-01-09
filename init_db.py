#!/usr/bin/env python3
"""
Database Initialization Script for Production
Safe to run on every deployment - only creates tables/data if needed
"""

from app import app, db, User
from sqlalchemy import inspect

if __name__ == '__main__':
    with app.app_context():
        # Check if tables exist
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        if not tables:
            print("No tables found. Initializing database...")
            from app import init_database
            init_database(app)
            print("✓ Database initialization complete!")
            print("✓ Tables created and default data loaded.")
        else:
            print("✓ Database tables already exist. Skipping initialization.")
            print(f"  Found {len(tables)} tables: {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")

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

        # --- One-time users table update: add default_report_year column if missing ---
        if 'users' in tables:
            user_cols = [col['name'] for col in inspector.get_columns('users')]
            if 'default_report_year' not in user_cols:
                print("Adding 'default_report_year' column to users table...")
                engine = db.engine
                dialect = engine.dialect.name
                with engine.connect() as conn:
                    if dialect == 'sqlite':
                        # SQLite: ALTER TABLE ADD COLUMN (if not exists is not supported, so just try)
                        try:
                            conn.execute('ALTER TABLE users ADD COLUMN default_report_year INTEGER')
                            print("✓ Column added (SQLite)")
                        except Exception as e:
                            print(f"! Error adding column (SQLite): {e}")
                    elif dialect == 'postgresql':
                        try:
                            conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS default_report_year INTEGER')
                            print("✓ Column added (Postgres)")
                        except Exception as e:
                            print(f"! Error adding column (Postgres): {e}")
                    else:
                        print(f"! Unknown DB dialect: {dialect}. Please add column manually.")
            else:
                print("✓ 'default_report_year' column already exists in users table.")
        else:
            print("! 'users' table not found. No column update performed.")

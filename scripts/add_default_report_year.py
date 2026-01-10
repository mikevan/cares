"""
One-off script to add users.default_report_year column if missing.
Run this before starting the server if the startup migration fails or if you want to apply it now.
"""
from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    try:
        res = db.session.execute(text("PRAGMA table_info('users')"))
        cols = [r[1] for r in res.fetchall()]
        if 'default_report_year' in cols:
            print('Column already exists: users.default_report_year')
        else:
            print('Adding column users.default_report_year ...')
            db.session.execute(text("ALTER TABLE users ADD COLUMN default_report_year INTEGER"))
            db.session.commit()
            print('Done.')
    except Exception as e:
        print('Failed to add column:', e)
        raise
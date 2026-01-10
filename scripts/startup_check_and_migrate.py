#!/usr/bin/env python3
"""
Startup migration utility
- Ensures the `users.default_report_year` column exists (works for SQLite and PostgreSQL).
- Exits with non-zero if it cannot ensure the column exists (so deployments fail fast and visible).

Usage: python scripts/startup_check_and_migrate.py
"""
import logging
import sys
import os
# Ensure repository root is on sys.path so this script works when invoked from scripts/ or CI
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import app
from models import db
from sqlalchemy import inspect, text

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def ensure_default_report_year_column():
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            cols = [c['name'] for c in inspector.get_columns('users')]
        except Exception as e:
            logger.exception('Could not inspect "users" table: %s', e)
            return False

        if 'default_report_year' in cols:
            logger.info('Column users.default_report_year already exists')
            return True

        logger.info('Column users.default_report_year not found; attempting to add it')

        dialect = db.engine.dialect.name
        try:
            if dialect in ('postgresql', 'mysql'):
                alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_report_year INTEGER"
            else:
                # SQLite (and others)
                alter_sql = "ALTER TABLE users ADD COLUMN default_report_year INTEGER"

            db.session.execute(text(alter_sql))
            db.session.commit()

            # Reinspect to verify
            inspector = inspect(db.engine)
            cols2 = [c['name'] for c in inspector.get_columns('users')]
            if 'default_report_year' in cols2:
                logger.info('Successfully added users.default_report_year')
                return True
            else:
                logger.error('Column still missing after ALTER')
                return False

        except Exception:
            logger.exception('ALTER TABLE to add users.default_report_year failed')
            # re-inspect in case of concurrent add
            try:
                inspector = inspect(db.engine)
                cols2 = [c['name'] for c in inspector.get_columns('users')]
                if 'default_report_year' in cols2:
                    logger.info('Column now exists (likely added by another process)')
                    return True
            except Exception:
                logger.exception('Failed to re-inspect users table after failing to ALTER')
            return False


if __name__ == '__main__':
    ok = ensure_default_report_year_column()
    if not ok:
        logger.error('Startup migration FAILED. Exiting with non-zero exit code to prevent a broken startup.')
        sys.exit(1)
    logger.info('Startup migration complete.')
    sys.exit(0)

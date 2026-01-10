"""CI/Deploy smoke check: verify migrations applied and schema is present."""
import os
import sys
from sqlalchemy import create_engine, inspect

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print('DATABASE_URL not set; cannot perform smoke check')
    sys.exit(2)

print(f'Connecting to database: {DATABASE_URL}')
try:
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if 'users' not in tables:
        print("ERROR: 'users' table not found in database")
        sys.exit(1)

    cols = [c['name'] for c in inspector.get_columns('users')]
    if 'default_report_year' in cols:
        print("OK: users.default_report_year exists")
        sys.exit(0)
    else:
        print("ERROR: users.default_report_year missing")
        print(f"Columns found: {cols}")
        sys.exit(1)
except Exception as e:
    print('ERROR: Exception while checking database schema:', str(e))
    sys.exit(3)

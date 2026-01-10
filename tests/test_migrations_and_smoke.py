import os
import tempfile
import unittest
import subprocess
import sys
from sqlalchemy import create_engine, inspect

class TestMigrationsAndSmoke(unittest.TestCase):
    def setUp(self):
        # Temporary SQLite file
        fd, self.db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.db_url = f'sqlite:///{self.db_path}'
        # Ensure the env var is set so alembic env.py uses it
        self.orig_db = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = self.db_url

        # Create a minimal `users` table to simulate existing schema so migrations can ALTER it
        from sqlalchemy import create_engine, text
        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR, email VARCHAR)'))
            conn.commit()

    def tearDown(self):
        if self.orig_db is not None:
            os.environ['DATABASE_URL'] = self.orig_db
        else:
            os.environ.pop('DATABASE_URL', None)
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_run_migrations_and_smoke(self):
        # Run migrations programmatically via the script (subprocess to get fresh process)
        subprocess.check_call([sys.executable, 'scripts/run_migrations.py'])

        # Now inspect the DB to ensure the column exists
        engine = create_engine(self.db_url)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        self.assertIn('users', tables)
        cols = [c['name'] for c in inspector.get_columns('users')]
        self.assertIn('default_report_year', cols)

if __name__ == '__main__':
    unittest.main()

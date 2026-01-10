"""
Programmatically run Alembic migrations (upgrade head)
Usage: python scripts/run_migrations.py
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from alembic.config import Config
from alembic import command

alembic_cfg = Config(os.path.join(REPO_ROOT, 'alembic.ini'))
command.upgrade(alembic_cfg, 'head')
print('Alembic upgrade head completed')
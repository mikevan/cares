import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from blueprints.auth_routes import init_database

print('Initializing database...')
init_database(app)
print('Done')

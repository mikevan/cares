import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

with app.test_client() as c:
    r = c.post('/login', data={'username':'admin','password':'admin123'}, follow_redirects=True)
    print('login status', r.status_code)
    r2 = c.get('/reports/balance-sheet?debug=1')
    print('debug endpoint status', r2.status_code)
    print('Content-Type:', r2.content_type)
    j = r2.get_json()
    print('JSON keys:', list(j.keys()))
    print('assets count:', len(j['assets']['accounts']))

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

with app.test_client() as c:
    r = c.post('/login', data={'username':'admin','password':'admin123'}, follow_redirects=True)
    r2 = c.get('/reports/income-statement?debug=1')
    print('status:', r2.status_code)
    print('content-type:', r2.content_type)
    j = r2.get_json()
    print('json keys:', list(j.keys()))
    print('revenues count:', len(j['revenues']['accounts']))
    print('expenses count:', len(j['expenses']['accounts']))

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

with app.test_client() as client:
    r = client.post('/login', data={'username':'admin','password':'admin123'}, follow_redirects=True)
    r2 = client.get('/reports/balance-sheet?banner=1')
    html = r2.get_data(as_text=True)
    start = html.find('Debug:')
    print('Banner present:', start != -1)
    if start != -1:
        snippet = html[start:start+200]
        print('Snippet:', snippet)

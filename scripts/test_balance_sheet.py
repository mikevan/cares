import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from models import db

with app.test_client() as client:
    # login as admin
    r = client.post('/login', data={'username':'admin','password':'admin123'}, follow_redirects=True)
    print('Login status code:', r.status_code)
    # get balance sheet page
    r2 = client.get('/reports/balance-sheet')
    print('Balance sheet status code:', r2.status_code)
    html = r2.get_data(as_text=True)
    # quick checks
    print('\n-- contains "Statement of Financial Position" ->', 'Statement of Financial Position' in html)
    print('-- contains "Operating Checking Account" ->', 'Operating Checking Account' in html)
    # show a small portion
    start = html.find('ASSETS')
    print('\nSnippet around ASSETS:')
    print(html[start:start+400])

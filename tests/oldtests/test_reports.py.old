import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from app import app
from models import db, Project, ChartOfAccounts, JournalEntry, JournalEntryLine, User
from datetime import date

@pytest.fixture(autouse=True)
def app_ctx():
    with app.app_context():
        yield

def login(client, username='admin', password='admin123'):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=True)

def test_income_statement_defaults_to_latest_year(tmp_path):
    # Create a new posted journal entry in a future year (2027) for org=1
    project = Project.query.filter_by(organization_id=1).first()
    assert project is not None

    revenue_account = ChartOfAccounts.query.filter_by(account_type='Revenue').first()
    assert revenue_account is not None

    # Insert a temporary journal entry and line
    je = JournalEntry(entry_date=date(2027,1,1), description='Test JE 2027', project_id=project.id, created_by=1, status='Posted')
    db.session.add(je)
    db.session.commit()

    jel = JournalEntryLine(journal_entry_id=je.id, account_id=revenue_account.id, credit_amount=123.45)
    db.session.add(jel)
    db.session.commit()

    # Use test client to hit income-statement with no year provided
    with app.test_client() as client:
        assert login(client).status_code == 200
        r = client.get('/reports/income-statement?debug=1')
        assert r.status_code == 200
        data = r.get_json()
        # The route should have defaulted to 2027 (the latest year we've added)
        assert 'period' in data
        assert '2027' in data['period']
        # Revenues should include our test credit
        total_revenue = data['revenues']['total']
        assert total_revenue >= 123.45

    # Cleanup
    JournalEntryLine.query.filter_by(journal_entry_id=je.id).delete()
    JournalEntry.query.filter_by(id=je.id).delete()
    db.session.commit()

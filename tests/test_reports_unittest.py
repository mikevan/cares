import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import unittest
from app import app
from models import db, Project, ChartOfAccounts, JournalEntry, JournalEntryLine
from datetime import date
from sqlalchemy import text

class TestReports(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.client = self.app.test_client()
        # ensure users.default_report_year column exists in DB for test runs
        try:
            db.session.execute(text('SELECT default_report_year FROM users LIMIT 1'))
        except Exception:
            # sqlite: add column if missing
            db.session.execute(text('ALTER TABLE users ADD COLUMN default_report_year INTEGER'))
            db.session.commit()

        # login
        self.client.post('/login', data={'username':'admin','password':'admin123'}, follow_redirects=True)

    def tearDown(self):
        self.ctx.pop()

    def test_income_statement_defaults_to_latest_year(self):
        project = Project.query.filter_by(organization_id=1).first()
        self.assertIsNotNone(project)
        revenue_account = ChartOfAccounts.query.filter_by(account_type='Revenue').first()
        self.assertIsNotNone(revenue_account)

        # create temporary posted JE in year 2097
        je = JournalEntry(entry_date=date(2097,1,1), description='Test JE 2097', project_id=project.id, created_by=1, status='Posted')
        db.session.add(je)
        db.session.commit()

        jel = JournalEntryLine(journal_entry_id=je.id, account_id=revenue_account.id, credit_amount=123.45)
        db.session.add(jel)
        db.session.commit()

        # call endpoint with debug json
        r = self.client.get('/reports/income-statement?debug=1')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('2097', data['period'])
        self.assertGreaterEqual(data['revenues']['total'], 123.45)

        # cleanup
        JournalEntryLine.query.filter_by(journal_entry_id=je.id).delete()
        JournalEntry.query.filter_by(id=je.id).delete()
        db.session.commit()

    def test_cash_flow_defaults_to_latest_year(self):
        project = Project.query.filter_by(organization_id=1).first()
        self.assertIsNotNone(project)
        cash_account = ChartOfAccounts.query.filter(ChartOfAccounts.account_number.between('1010','1030')).first()
        self.assertIsNotNone(cash_account)
        revenue_account = ChartOfAccounts.query.filter_by(account_type='Revenue').first()
        self.assertIsNotNone(revenue_account)

        # create temporary posted JE in year 2098 which increases cash
        je = JournalEntry(entry_date=date(2098,6,1), description='Test Cash JE 2098', project_id=project.id, created_by=1, status='Posted')
        db.session.add(je)
        db.session.commit()

        jel1 = JournalEntryLine(journal_entry_id=je.id, account_id=cash_account.id, debit_amount=200)
        jel2 = JournalEntryLine(journal_entry_id=je.id, account_id=revenue_account.id, credit_amount=200)
        db.session.add_all([jel1, jel2])
        db.session.commit()

        r = self.client.get('/reports/cash-flow?debug=1')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('2098', data['period'])
        self.assertNotEqual(data['net_change_in_cash'], 0)

        # cleanup
        JournalEntryLine.query.filter_by(journal_entry_id=je.id).delete()
        JournalEntry.query.filter_by(id=je.id).delete()
        db.session.commit()

    def test_functional_expenses_defaults_to_latest_year(self):
        project = Project.query.filter_by(organization_id=1).first()
        self.assertIsNotNone(project)
        cash_account = ChartOfAccounts.query.filter(ChartOfAccounts.account_number.between('1010','1030')).first()
        self.assertIsNotNone(cash_account)
        expense_account = ChartOfAccounts.query.filter_by(account_type='Expense').first()
        self.assertIsNotNone(expense_account)

        # create temporary posted JE in year 2099 which records an expense
        je = JournalEntry(entry_date=date(2099,7,1), description='Test Expense JE 2099', project_id=project.id, created_by=1, status='Posted')
        db.session.add(je)
        db.session.commit()

        jel1 = JournalEntryLine(journal_entry_id=je.id, account_id=expense_account.id, debit_amount=500)
        jel2 = JournalEntryLine(journal_entry_id=je.id, account_id=cash_account.id, credit_amount=500)
        db.session.add_all([jel1, jel2])
        db.session.commit()

        r = self.client.get('/reports/functional-expenses?debug=1')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('2099', data['period'])
        self.assertGreaterEqual(data['totals']['total'], 500)

        # cleanup
        JournalEntryLine.query.filter_by(journal_entry_id=je.id).delete()
        JournalEntry.query.filter_by(id=je.id).delete()
        db.session.commit()

if __name__ == '__main__':
    unittest.main()

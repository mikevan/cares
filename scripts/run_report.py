import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import traceback
try:
    from app import app
    from services.reports import FinancialReports
    from models import db
    import json

    with app.app_context():
        fr = FinancialReports(db.session, organization_id=1)
        bs = fr.balance_sheet()
        print('Balance Sheet summary:')
        print(json.dumps(bs, indent=2))
        is_stmt = fr.income_statement('2025-01-01','2025-12-31')
        print('\nIncome Statement summary:')
        print(json.dumps(is_stmt, indent=2))
except Exception as e:
    print('Error importing or running report:')
    traceback.print_exc()

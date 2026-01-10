from app import app
from models import db, ChartOfAccounts, JournalEntry
from sqlalchemy import inspect

with app.app_context():
    print('Engine URL:', str(db.engine.url))
    insp = inspect(db.engine)
    print('Tables:', insp.get_table_names())
    try:
        print('ChartCount:', ChartOfAccounts.query.count())
    except Exception as e:
        print('ChartCount error:', e)
    try:
        print('JournalCount:', JournalEntry.query.count())
    except Exception as e:
        print('JournalCount error:', e)

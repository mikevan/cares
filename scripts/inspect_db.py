import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import sqlite3
from decimal import Decimal

DB_PATH = 'kofc_accounting.db'

def rows(cur, q, params=()):
    cur.execute(q, params)
    return cur.fetchall()

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print('Tables:')
    for r in rows(cur, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"):
        print(' -', r['name'])

    print('\nCounts:')
    for tbl in ['chart_of_accounts','journal_entries','journal_entry_lines']:
        try:
            c = rows(cur, f"SELECT COUNT(*) as cnt FROM {tbl}")[0]['cnt']
        except Exception as e:
            c = f'err: {e}'
        print(f' {tbl}:', c)

    print('\nSample Chart of Accounts:')
    coa = rows(cur, "SELECT id, account_number, account_name, account_type, normal_balance, active FROM chart_of_accounts ORDER BY account_number LIMIT 20")
    for a in coa:
        print(f" id={a['id']} {a['account_number']} {a['account_name']} ({a['account_type']}) active={a['active']} normal={a['normal_balance']}")

    print('\nRecent Journal Entries:')
    je = rows(cur, "SELECT id, entry_date, description, status FROM journal_entries ORDER BY entry_date DESC LIMIT 10")
    for j in je:
        print(f" id={j['id']} date={j['entry_date']} status={j['status']} desc={j['description'][:50]}")

    print('\nSample Journal Entry Lines (first 20):')
    jlines = rows(cur, "SELECT id, journal_entry_id, account_id, debit_amount, credit_amount FROM journal_entry_lines LIMIT 20")
    for l in jlines:
        print(f" id={l['id']} je={l['journal_entry_id']} acc={l['account_id']} debit={l['debit_amount']} credit={l['credit_amount']}")

    # Compute balances for first few accounts
    print('\nComputed balances (using Posted entries, no date limit):')
    for a in coa[:10]:
        aid = a['id']
        deb = rows(cur, "SELECT SUM(debit_amount) as s FROM journal_entry_lines l JOIN journal_entries j ON j.id = l.journal_entry_id WHERE l.account_id = ? AND j.status = 'Posted'", (aid,))[0]['s']
        cred = rows(cur, "SELECT SUM(credit_amount) as s FROM journal_entry_lines l JOIN journal_entries j ON j.id = l.journal_entry_id WHERE l.account_id = ? AND j.status = 'Posted'", (aid,))[0]['s']
        deb = Decimal(str(deb)) if deb is not None else Decimal('0')
        cred = Decimal(str(cred)) if cred is not None else Decimal('0')
        if a['normal_balance'] and a['normal_balance'].lower().startswith('d'):
            bal = deb - cred
        else:
            bal = cred - deb
        print(f" acc {a['account_number']} ({a['account_name']}) -> debit={deb} credit={cred} balance={bal}")

    print('\nDone')

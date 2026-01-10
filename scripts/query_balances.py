import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import sqlite3
from decimal import Decimal

DB = 'instance/kofc_accounting.db'

sql = '''
SELECT coa.id,
       coa.account_number,
       coa.account_name,
       coa.account_type,
       coa.normal_balance,
       IFNULL(SUM(jel.debit_amount),0) AS debits,
       IFNULL(SUM(jel.credit_amount),0) AS credits,
       CASE WHEN lower(coa.normal_balance) LIKE 'd%' THEN IFNULL(SUM(jel.debit_amount),0)-IFNULL(SUM(jel.credit_amount),0)
            ELSE IFNULL(SUM(jel.credit_amount),0)-IFNULL(SUM(jel.debit_amount),0) END as balance
FROM chart_of_accounts coa
LEFT JOIN journal_entry_lines jel ON jel.account_id = coa.id
LEFT JOIN journal_entries je ON je.id = jel.journal_entry_id AND je.status = 'Posted'
WHERE coa.active = 1
GROUP BY coa.id
HAVING (CASE WHEN lower(coa.normal_balance) LIKE 'd%' THEN SUM(jel.debit_amount)-SUM(jel.credit_amount) ELSE SUM(jel.credit_amount)-SUM(jel.debit_amount) END) != 0
ORDER BY coa.account_number
LIMIT 200;
'''

with sqlite3.connect(DB) as conn:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        print('Tables:', [r[0] for r in cur.fetchall()])
    except Exception as e:
        print('Error listing tables:', e)
        raise

    try:
        cur.execute('SELECT COUNT(*) FROM chart_of_accounts')
        print('chart_of_accounts count:', cur.fetchone()[0])
    except Exception as e:
        print('chart_of_accounts count: ERROR', e)

    print('\nRunning balance query...')
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        if not rows:
            print('No non-zero balances found (query returned zero rows).')
        else:
            print(f'Found {len(rows)} rows with non-zero balances:\n')
            for r in rows:
                print(f"{r['account_number']} - {r['account_name']}: balance={r['balance']} (debits={r['debits']} credits={r['credits']})")
    except Exception as e:
        print('Error running balance SQL:', e)
        raise

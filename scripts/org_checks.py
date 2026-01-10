import sqlite3
DB='instance/kofc_accounting.db'
org_id=1
con=sqlite3.connect(DB)
cur=con.cursor()
cur.execute("SELECT COUNT(*) FROM journal_entries j JOIN projects p ON j.project_id = p.id WHERE p.organization_id = ? AND j.status='Posted'", (org_id,))
print('Posted journal entries for org',org_id,':',cur.fetchone()[0])

sql = '''
SELECT coa.account_number, coa.account_name,
CASE WHEN lower(coa.normal_balance) LIKE 'd%' THEN IFNULL(SUM(jel.debit_amount),0)-IFNULL(SUM(jel.credit_amount),0)
     ELSE IFNULL(SUM(jel.credit_amount),0)-IFNULL(SUM(jel.debit_amount),0) END as balance
FROM chart_of_accounts coa
JOIN journal_entry_lines jel ON jel.account_id = coa.id
JOIN journal_entries je ON je.id = jel.journal_entry_id AND je.status = 'Posted'
JOIN projects p ON je.project_id = p.id AND p.organization_id = ?
GROUP BY coa.id
HAVING balance != 0
ORDER BY coa.account_number
LIMIT 200;
'''
cur.execute(sql, (org_id,))
rows=cur.fetchall()
print('\nOrg-scoped balances (count):', len(rows))
for r in rows:
    print(r[0],'-',r[1],':',r[2])
con.close()

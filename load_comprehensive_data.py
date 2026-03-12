"""
CARES Demo Data Loader
Fiscal years 2025 (complete) and 2026 (YTD March)

Demonstrates:
  - Membership dues as primary operating revenue (with member names in memo)
  - Full AR accrual cycle: grant/fee earned → receivable → cash collected
  - Full AP cycle: expense incurred → payable → cash paid
  - Direct cash transactions (cash flow report works correctly)
  - Individual/corporate donations, foundation/government grants
  - Program service fees, special event revenue
  - Monthly depreciation
  - Restricted vs unrestricted net assets with releases
  - Open AR and open AP in 2026 for balance sheet aging demo

No payroll - chapter volunteer model.
"""

from app import app, db
from models import Organization, User, Project, Member, JournalEntry, JournalEntryLine, ChartOfAccounts
from datetime import date
from decimal import Decimal
from sqlalchemy import text

# ==================== ACCOUNT CACHE ====================

_acct = {}

def _load_accounts():
    for a in ChartOfAccounts.query.all():
        _acct[a.account_number] = a

def acct(number):
    a = _acct.get(number)
    if not a:
        raise ValueError(f"Account {number} not found in chart of accounts")
    return a

# ==================== JOURNAL ENTRY HELPER ====================

def je(project, entry_date, description, reference, lines, user_id):
    """
    Create a posted journal entry.
    lines = list of (account_number, debit_amount, credit_amount, memo)
    """
    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project.id,
        reference_number=reference,
        created_by=user_id,
        status='Posted'
    )
    db.session.add(entry)
    db.session.flush()

    total_debits = Decimal('0')
    total_credits = Decimal('0')

    for account_number, debit, credit, memo in lines:
        d = Decimal(str(debit))
        c = Decimal(str(credit))
        total_debits += d
        total_credits += c
        line = JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=acct(account_number).id,
            debit_amount=d,
            credit_amount=c,
            memo=memo
        )
        db.session.add(line)

    if abs(total_debits - total_credits) >= Decimal('0.01'):
        raise ValueError(
            f"Unbalanced entry '{reference}': debits={total_debits} credits={total_credits}"
        )

    return entry

# ==================== CLEAR DATA ====================

def clear_existing_data():
    print("  Clearing existing transaction data...")
    # TRUNCATE CASCADE handles all FK dependencies automatically
    db.session.execute(text(
        "TRUNCATE journal_entries, journal_entry_lines, members, projects "
        "RESTART IDENTITY CASCADE"
    ))
    User.query.filter(User.id > 1).delete()
    db.session.commit()
    print("  ✓ Cleared.")

# ==================== MEMBERS ====================

MEMBERS = [
    ('James Kowalski',      'james.kowalski@example.com',     '555-0201'),
    ('Thomas Brennan',      'thomas.brennan@example.com',     '555-0202'),
    ('Patrick Sullivan',    'patrick.sullivan@example.com',   '555-0203'),
    ('Michael O\'Brien',    'michael.obrien@example.com',     '555-0204'),
    ('Robert Callahan',     'robert.callahan@example.com',    '555-0205'),
    ('William Fitzgerald',  'william.fitzgerald@example.com', '555-0206'),
    ('Joseph Donovan',      'joseph.donovan@example.com',     '555-0207'),
    ('Edward Murphy',       'edward.murphy@example.com',      '555-0208'),
    ('Francis Gallagher',   'francis.gallagher@example.com',  '555-0209'),
    ('Daniel Shea',         'daniel.shea@example.com',        '555-0210'),
    ('John Rafferty',       'john.rafferty@example.com',      '555-0211'),
    ('Paul Hennessy',       'paul.hennessy@example.com',      '555-0212'),
    ('Kevin Flanagan',      'kevin.flanagan@example.com',     '555-0213'),
    ('Brian Malone',        'brian.malone@example.com',       '555-0214'),
    ('Christopher Dolan',   'christopher.dolan@example.com',  '555-0215'),
    ('Gerard Casey',        'gerard.casey@example.com',       '555-0216'),
    ('Anthony Nolan',       'anthony.nolan@example.com',      '555-0217'),
    ('Timothy Walsh',       'timothy.walsh@example.com',      '555-0218'),
    ('Raymond Costello',    'raymond.costello@example.com',   '555-0219'),
    ('Lawrence Higgins',    'lawrence.higgins@example.com',   '555-0220'),
]

# Annual dues payers (pay once in January): first 15
# Quarterly dues payers (pay each quarter): last 5
ANNUAL_DUES = 150.00
QUARTERLY_DUES = 37.50

def create_members(org_id):
    print("  Creating members...")
    members = []
    for name, email, phone in MEMBERS:
        m = Member(
            name=name,
            email=email,
            phone=phone,
            join_date=date(2023, 1, 1),
            active=True,
            organization_id=org_id
        )
        db.session.add(m)
        members.append(m)
    db.session.commit()
    print(f"  ✓ Created {len(members)} members.")
    return members

# ==================== PROJECTS ====================

def create_projects(org_id):
    print("  Creating projects...")
    project_defs = [
        ('General Operations',      'Chapter administration, overhead, and general activities',        50000,  'Active'),
        ('Youth Education Program', 'Academic tutoring, scholarships, and youth mentorship',           75000,  'Active'),
        ('Community Food Bank',     'Weekly food distribution and emergency pantry',                   60000,  'Active'),
        ('Senior Wellness Program', 'Health screenings, social activities, and home visits',           45000,  'Active'),
        ('Annual Charity Gala',     'Annual fundraising dinner and auction event',                    120000,  'Active'),
        ('Community Outreach',      'Neighborhood service projects and volunteer coordination',        30000,  'Active'),
    ]
    projects = {}
    for name, desc, budget, status in project_defs:
        p = Project(
            name=name,
            description=desc,
            start_date=date(2025, 1, 1),
            status=status,
            budget=Decimal(str(budget)),
            organization_id=org_id
        )
        db.session.add(p)
        db.session.flush()
        projects[name] = p
    db.session.commit()
    print(f"  ✓ Created {len(projects)} projects.")
    return projects

# ==================== 2025 TRANSACTIONS ====================

def load_2025(projects, members, user_id):
    print("  Loading 2025 transactions...")
    ops  = projects['General Operations']
    yep  = projects['Youth Education Program']
    cfb  = projects['Community Food Bank']
    swp  = projects['Senior Wellness Program']
    gala = projects['Annual Charity Gala']
    out  = projects['Community Outreach']

    annual_payers     = members[:15]
    quarterly_payers  = members[15:]

    # ------------------------------------------------------------------
    # JANUARY 2025
    # ------------------------------------------------------------------

    # Opening balances: Cash, Fixed Assets, Loan, Net Assets
    je(ops, date(2025, 1, 1), 'Opening balances - Jan 1 2025', 'OB-2025',
       [('1010', 180000, 0,      'Opening cash balance'),
        ('1410', 15000,  0,      'Computer equipment'),
        ('1420', 8000,   0,      'Furniture and fixtures'),
        ('1430', 35000,  0,      'Chapter vehicle'),
        ('2310', 0,      25000,  'Vehicle loan balance'),
        ('3100', 0,      213000, 'Net assets without donor restrictions')],
       user_id)

    # Annual dues - 15 members pay in January
    for m in annual_payers:
        je(ops, date(2025, 1, 15),
           f'Annual membership dues - {m.name}',
           f'DUES-2025-{m.id}',
           [('1010', ANNUAL_DUES, 0,            f'Annual dues - {m.name}'),
            ('4110', 0,           ANNUAL_DUES,  f'Annual dues - {m.name}')],
           user_id)

    # Quarterly dues Q1 - 5 members
    for m in quarterly_payers:
        je(ops, date(2025, 1, 20),
           f'Q1 membership dues - {m.name}',
           f'DUES-Q1-2025-{m.id}',
           [('1010', QUARTERLY_DUES, 0,              f'Q1 dues - {m.name}'),
            ('4110', 0,              QUARTERLY_DUES, f'Q1 dues - {m.name}')],
           user_id)

    # January rent - direct cash
    je(ops, date(2025, 1, 1), 'January office rent', 'RENT-2501',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # January utilities - direct cash
    je(ops, date(2025, 1, 15), 'January utilities', 'UTIL-2501',
       [('5220', 380, 0,   'Electric, gas, water'),
        ('1010', 0,   380, 'Cash payment')],
       user_id)

    # Annual insurance - AP accrual
    je(ops, date(2025, 1, 1), 'Annual general liability insurance invoice', 'INV-INS-2025',
       [('5610', 4800, 0,    'Annual GL insurance premium'),
        ('2110', 0,    4800, 'Accounts payable - Reliable Insurance Co')],
       user_id)

    # Pay insurance invoice
    je(ops, date(2025, 1, 31), 'Pay insurance invoice', 'CHK-INS-2025',
       [('2110', 4800, 0,    'Clear AP - Reliable Insurance Co'),
        ('1010', 0,    4800, 'Cash payment')],
       user_id)

    # Individual donation - direct cash
    je(ops, date(2025, 1, 28), 'Individual donor contributions - January', 'DON-2501',
       [('1010', 5000, 0,    'Cash donations received'),
        ('4010', 0,    5000, 'Individual contributions')],
       user_id)

    # January depreciation
    je(ops, date(2025, 1, 31), 'January depreciation', 'DEP-2501',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # FEBRUARY 2025
    # ------------------------------------------------------------------

    # February rent
    je(ops, date(2025, 2, 1), 'February office rent', 'RENT-2502',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # February utilities
    je(ops, date(2025, 2, 15), 'February utilities', 'UTIL-2502',
       [('5220', 410, 0,   'Electric, gas, water'),
        ('1010', 0,   410, 'Cash payment')],
       user_id)

    # Office supplies AP invoice
    je(ops, date(2025, 2, 5), 'Office supplies order', 'INV-SUP-2501',
       [('5310', 650, 0,   'Office supplies'),
        ('2110', 0,   650, 'Accounts payable - Office Depot')],
       user_id)

    # Pay office supplies
    je(ops, date(2025, 2, 20), 'Pay office supplies invoice', 'CHK-SUP-2501',
       [('2110', 650, 0,   'Clear AP - Office Depot'),
        ('1010', 0,   650, 'Cash payment')],
       user_id)

    # Food bank supplies - direct cash
    je(cfb, date(2025, 2, 10), 'Food bank supplies purchase', 'SUP-CFB-2501',
       [('5320', 2200, 0,    'Food and distribution supplies'),
        ('1010', 0,    2200, 'Cash payment')],
       user_id)

    # Corporate contribution
    je(ops, date(2025, 2, 14), 'Corporate contribution - First National Bank', 'CORP-2501',
       [('1010', 10000, 0,     'Corporate contribution cash'),
        ('4020', 0,     10000, 'Corporate contributions')],
       user_id)

    # February depreciation
    je(ops, date(2025, 2, 28), 'February depreciation', 'DEP-2502',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # MARCH 2025
    # ------------------------------------------------------------------

    # March rent
    je(ops, date(2025, 3, 1), 'March office rent', 'RENT-2503',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # March utilities
    je(ops, date(2025, 3, 15), 'March utilities', 'UTIL-2503',
       [('5220', 365, 0,   'Electric, gas, water'),
        ('1010', 0,   365, 'Cash payment')],
       user_id)

    # Government grant awarded - AR accrual (not yet received)
    je(yep, date(2025, 3, 1), 'State youth education grant awarded', 'GRANT-GOV-2501',
       [('1230', 50000, 0,     'Grants receivable - State Dept of Education'),
        ('4040', 0,     50000, 'Government grants revenue')],
       user_id)

    # Program service fees invoiced to partner org - AR
    je(swp, date(2025, 3, 15), 'Senior wellness program fees invoiced - Q1', 'AR-SWP-2501',
       [('1210', 3000, 0,    'Accounts receivable - City Senior Services'),
        ('4120', 0,    3000, 'Program service fees earned')],
       user_id)

    # Equipment maintenance - direct cash
    je(ops, date(2025, 3, 20), 'Computer equipment maintenance', 'MAINT-2501',
       [('5710', 480, 0,   'Equipment maintenance contract'),
        ('1010', 0,   480, 'Cash payment')],
       user_id)

    # March depreciation
    je(ops, date(2025, 3, 31), 'March depreciation', 'DEP-2503',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # APRIL 2025
    # ------------------------------------------------------------------

    # April rent
    je(ops, date(2025, 4, 1), 'April office rent', 'RENT-2504',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # April utilities
    je(ops, date(2025, 4, 15), 'April utilities', 'UTIL-2504',
       [('5220', 320, 0,   'Electric, gas, water'),
        ('1010', 0,   320, 'Cash payment')],
       user_id)

    # Collect government grant cash
    je(yep, date(2025, 4, 10), 'State youth education grant - cash received', 'GRANT-GOV-2501-PAY',
       [('1010', 50000, 0,     'Grant cash received'),
        ('1230', 0,     50000, 'Clear grants receivable')],
       user_id)

    # Collect senior wellness AR
    je(swp, date(2025, 4, 20), 'Collect senior wellness Q1 fees', 'AR-SWP-2501-PAY',
       [('1010', 3000, 0,    'Cash collected'),
        ('1210', 0,    3000, 'Clear accounts receivable')],
       user_id)

    # Foundation grant - direct cash
    je(yep, date(2025, 4, 15), 'Community foundation grant - youth literacy', 'GRANT-FDN-2501',
       [('1010', 25000, 0,     'Foundation grant cash'),
        ('4030', 0,     25000, 'Foundation grants')],
       user_id)

    # Individual donations
    je(ops, date(2025, 4, 30), 'April individual donor contributions', 'DON-2504',
       [('1010', 8500, 0,    'Cash donations'),
        ('4010', 0,    8500, 'Individual contributions')],
       user_id)

    # Food bank supplies - AP invoice
    je(cfb, date(2025, 4, 1), 'Food bank April supplies invoice', 'INV-CFB-2501',
       [('5320', 3500, 0,    'Monthly food and supplies'),
        ('2110', 0,    3500, 'Accounts payable - Regional Food Distributors')],
       user_id)

    # Pay food bank AP
    je(cfb, date(2025, 4, 25), 'Pay food bank supplies invoice', 'CHK-CFB-2501',
       [('2110', 3500, 0,    'Clear AP - Regional Food Distributors'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # April depreciation
    je(ops, date(2025, 4, 30), 'April depreciation', 'DEP-2504',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # MAY 2025
    # ------------------------------------------------------------------

    # May rent
    je(ops, date(2025, 5, 1), 'May office rent', 'RENT-2505',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # May utilities
    je(ops, date(2025, 5, 15), 'May utilities', 'UTIL-2505',
       [('5220', 295, 0,   'Electric, gas, water'),
        ('1010', 0,   295, 'Cash payment')],
       user_id)

    # Corporate contribution
    je(cfb, date(2025, 5, 5), 'Corporate sponsorship - Valley Grocery', 'CORP-2502',
       [('1010', 8000, 0,    'Corporate contribution cash'),
        ('4020', 0,    8000, 'Corporate contributions')],
       user_id)

    # Program service fees - direct cash
    je(yep, date(2025, 5, 20), 'Youth tutoring program fees - spring session', 'FEES-YEP-2501',
       [('1010', 2500, 0,    'Program fees cash'),
        ('4120', 0,    2500, 'Program service fees')],
       user_id)

    # Gala venue deposit - direct cash
    je(gala, date(2025, 5, 15), 'Annual gala venue deposit', 'GALA-DEP-2501',
       [('5520', 2000, 0,    'Venue deposit - Grand Ballroom'),
        ('1010', 0,    2000, 'Cash payment')],
       user_id)

    # Food bank supplies AP
    je(cfb, date(2025, 5, 1), 'Food bank May supplies invoice', 'INV-CFB-2502',
       [('5320', 3500, 0,    'Monthly food and supplies'),
        ('2110', 0,    3500, 'Accounts payable - Regional Food Distributors')],
       user_id)

    # Pay food bank AP
    je(cfb, date(2025, 5, 28), 'Pay food bank May supplies invoice', 'CHK-CFB-2502',
       [('2110', 3500, 0,    'Clear AP - Regional Food Distributors'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # May depreciation
    je(ops, date(2025, 5, 31), 'May depreciation', 'DEP-2505',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # JUNE 2025
    # ------------------------------------------------------------------

    # June rent
    je(ops, date(2025, 6, 1), 'June office rent', 'RENT-2506',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # June utilities
    je(ops, date(2025, 6, 15), 'June utilities', 'UTIL-2506',
       [('5220', 410, 0,   'Electric, gas, water - cooling season begins'),
        ('1010', 0,   410, 'Cash payment')],
       user_id)

    # Q2 quarterly dues
    for m in quarterly_payers:
        je(ops, date(2025, 6, 15),
           f'Q2 membership dues - {m.name}',
           f'DUES-Q2-2025-{m.id}',
           [('1010', QUARTERLY_DUES, 0,              f'Q2 dues - {m.name}'),
            ('4110', 0,              QUARTERLY_DUES, f'Q2 dues - {m.name}')],
           user_id)

    # Foundation grant - AR accrual (awarded, not yet received)
    je(out, date(2025, 6, 1), 'Community foundation outreach grant awarded', 'GRANT-FDN-2502',
       [('1230', 30000, 0,     'Grants receivable - Metro Community Foundation'),
        ('4030', 0,     30000, 'Foundation grants revenue')],
       user_id)

    # Program supplies - direct cash
    je(out, date(2025, 6, 10), 'Community outreach program materials', 'SUP-OUT-2501',
       [('5320', 1800, 0,    'Outreach program materials'),
        ('1010', 0,    1800, 'Cash payment')],
       user_id)

    # Gala marketing - AP invoice
    je(gala, date(2025, 6, 20), 'Gala marketing and promotional materials', 'INV-GALA-2501',
       [('5510', 3500, 0,    'Marketing - print, digital, mailing'),
        ('2110', 0,    3500, 'Accounts payable - Creative Marketing Group')],
       user_id)

    # June depreciation
    je(ops, date(2025, 6, 30), 'June depreciation', 'DEP-2506',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # JULY 2025
    # ------------------------------------------------------------------

    # July rent
    je(ops, date(2025, 7, 1), 'July office rent', 'RENT-2507',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # July utilities
    je(ops, date(2025, 7, 15), 'July utilities', 'UTIL-2507',
       [('5220', 520, 0,   'Electric, gas, water - peak cooling'),
        ('1010', 0,   520, 'Cash payment')],
       user_id)

    # Collect foundation grant (June AR)
    je(out, date(2025, 7, 5), 'Collect community foundation outreach grant', 'GRANT-FDN-2502-PAY',
       [('1010', 30000, 0,     'Grant cash received'),
        ('1230', 0,     30000, 'Clear grants receivable')],
       user_id)

    # Individual donations - direct cash
    je(ops, date(2025, 7, 20), 'July individual donor contributions', 'DON-2507',
       [('1010', 12000, 0,     'Cash donations'),
        ('4010', 0,     12000, 'Individual contributions')],
       user_id)

    # Program supplies food bank - direct cash
    je(cfb, date(2025, 7, 8), 'Food bank July supplies', 'SUP-CFB-2502',
       [('5320', 3200, 0,    'Monthly food supplies'),
        ('1010', 0,    3200, 'Cash payment')],
       user_id)

    # Pay gala marketing AP
    je(gala, date(2025, 7, 15), 'Pay gala marketing invoice', 'CHK-GALA-2501',
       [('2110', 3500, 0,    'Clear AP - Creative Marketing Group'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # July depreciation
    je(ops, date(2025, 7, 31), 'July depreciation', 'DEP-2507',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # AUGUST 2025
    # ------------------------------------------------------------------

    # August rent
    je(ops, date(2025, 8, 1), 'August office rent', 'RENT-2508',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # August utilities
    je(ops, date(2025, 8, 15), 'August utilities', 'UTIL-2508',
       [('5220', 495, 0,   'Electric, gas, water'),
        ('1010', 0,   495, 'Cash payment')],
       user_id)

    # Government grant - direct cash (workforce/outreach)
    je(out, date(2025, 8, 1), 'Federal community outreach grant', 'GRANT-GOV-2502',
       [('1010', 40000, 0,     'Federal grant cash received'),
        ('4040', 0,     40000, 'Government grants')],
       user_id)

    # Corporate gala sponsorship - direct cash
    je(gala, date(2025, 8, 15), 'Platinum gala sponsor - Tri-State Industries', 'CORP-GALA-2501',
       [('1010', 15000, 0,     'Sponsorship cash'),
        ('4020', 0,     15000, 'Corporate contributions')],
       user_id)

    # Consulting fees - AP invoice
    je(ops, date(2025, 8, 10), 'Strategic planning consulting - Phase 1', 'INV-CONS-2501',
       [('5410', 4500, 0,    'Consulting fees - Phase 1'),
        ('2110', 0,    4500, 'Accounts payable - Peterson Consulting')],
       user_id)

    # Food bank supplies - direct cash
    je(cfb, date(2025, 8, 5), 'Food bank August supplies', 'SUP-CFB-2503',
       [('5320', 3500, 0,    'Monthly food supplies'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # August depreciation
    je(ops, date(2025, 8, 31), 'August depreciation', 'DEP-2508',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # SEPTEMBER 2025
    # ------------------------------------------------------------------

    # September rent
    je(ops, date(2025, 9, 1), 'September office rent', 'RENT-2509',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # September utilities
    je(ops, date(2025, 9, 15), 'September utilities', 'UTIL-2509',
       [('5220', 440, 0,   'Electric, gas, water'),
        ('1010', 0,   440, 'Cash payment')],
       user_id)

    # Q3 quarterly dues
    for m in quarterly_payers:
        je(ops, date(2025, 9, 15),
           f'Q3 membership dues - {m.name}',
           f'DUES-Q3-2025-{m.id}',
           [('1010', QUARTERLY_DUES, 0,              f'Q3 dues - {m.name}'),
            ('4110', 0,              QUARTERLY_DUES, f'Q3 dues - {m.name}')],
           user_id)

    # Program fees - direct cash (senior wellness Q3)
    je(swp, date(2025, 9, 10), 'Senior wellness program fees - Q3', 'FEES-SWP-2502',
       [('1010', 4500, 0,    'Program fees cash'),
        ('4120', 0,    4500, 'Program service fees')],
       user_id)

    # Pay consulting AP
    je(ops, date(2025, 9, 5), 'Pay consulting invoice Phase 1', 'CHK-CONS-2501',
       [('2110', 4500, 0,    'Clear AP - Peterson Consulting'),
        ('1010', 0,    4500, 'Cash payment')],
       user_id)

    # In-kind donation (non-cash - food supplies donated)
    je(cfb, date(2025, 9, 20), 'In-kind food donation - Valley Grocery', 'INKIND-2501',
       [('5320', 5000, 0,    'In-kind food supplies received and distributed'),
        ('4310', 0,    5000, 'In-kind donations')],
       user_id)

    # Vehicle expenses - direct cash
    je(yep, date(2025, 9, 25), 'Chapter vehicle fuel and maintenance', 'VEH-2501',
       [('5720', 650, 0,   'Vehicle fuel and oil change'),
        ('1010', 0,   650, 'Cash payment')],
       user_id)

    # September depreciation
    je(ops, date(2025, 9, 30), 'September depreciation', 'DEP-2509',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # OCTOBER 2025 - Annual Charity Gala
    # ------------------------------------------------------------------

    # October rent
    je(ops, date(2025, 10, 1), 'October office rent', 'RENT-2510',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # October utilities
    je(ops, date(2025, 10, 15), 'October utilities', 'UTIL-2510',
       [('5220', 380, 0,   'Electric, gas, water'),
        ('1010', 0,   380, 'Cash payment')],
       user_id)

    # Gala ticket sales - direct cash
    je(gala, date(2025, 10, 18), 'Annual gala ticket sales', 'GALA-TIX-2501',
       [('1010', 38000, 0,     'Ticket sales cash'),
        ('4210', 0,     38000, 'Special event revenue')],
       user_id)

    # Gala auction proceeds - direct cash
    je(gala, date(2025, 10, 18), 'Annual gala silent auction proceeds', 'GALA-AUC-2501',
       [('1010', 22000, 0,     'Auction proceeds cash'),
        ('4220', 0,     22000, 'Auction revenue')],
       user_id)

    # Gala catering - AP invoice
    je(gala, date(2025, 10, 20), 'Gala catering invoice', 'INV-GALA-2502',
       [('5520', 14000, 0,     'Catering - Grand Ballroom Catering Co'),
        ('2110', 0,     14000, 'Accounts payable - Grand Ballroom Catering Co')],
       user_id)

    # Gala AV and entertainment - direct cash
    je(gala, date(2025, 10, 18), 'Gala AV equipment and entertainment', 'GALA-AV-2501',
       [('5520', 3500, 0,    'AV and entertainment'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # Individual donations October
    je(ops, date(2025, 10, 31), 'October individual donations', 'DON-2510',
       [('1010', 6500, 0,    'Cash donations'),
        ('4010', 0,    6500, 'Individual contributions')],
       user_id)

    # Pay gala catering AP
    je(gala, date(2025, 10, 31), 'Pay gala catering invoice', 'CHK-GALA-2502',
       [('2110', 14000, 0,     'Clear AP - Grand Ballroom Catering Co'),
        ('1010', 0,     14000, 'Cash payment')],
       user_id)

    # October depreciation
    je(ops, date(2025, 10, 31), 'October depreciation', 'DEP-2510',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # NOVEMBER 2025
    # ------------------------------------------------------------------

    # November rent
    je(ops, date(2025, 11, 1), 'November office rent', 'RENT-2511',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # November utilities
    je(ops, date(2025, 11, 15), 'November utilities', 'UTIL-2511',
       [('5220', 420, 0,   'Electric, gas, water - heating season'),
        ('1010', 0,   420, 'Cash payment')],
       user_id)

    # Restricted grant received - time-restricted for 2026 programs
    je(ops, date(2025, 11, 1), 'Multi-year foundation grant - restricted for 2026 programs', 'GRANT-RESTRICT-2501',
       [('1010', 100000, 0,      'Restricted grant cash received'),
        ('3200', 0,      100000, 'Net assets with donor restrictions - time')],
       user_id)

    # Food bank supplies - direct cash
    je(cfb, date(2025, 11, 8), 'Food bank November supplies', 'SUP-CFB-2504',
       [('5320', 3800, 0,    'Monthly food supplies - Thanksgiving prep'),
        ('1010', 0,    3800, 'Cash payment')],
       user_id)

    # Consulting Phase 2 - AP invoice
    je(ops, date(2025, 11, 15), 'Strategic planning consulting - Phase 2', 'INV-CONS-2502',
       [('5410', 4500, 0,    'Consulting fees - Phase 2'),
        ('2110', 0,    4500, 'Accounts payable - Peterson Consulting')],
       user_id)

    # Pay consulting Phase 2
    je(ops, date(2025, 11, 30), 'Pay consulting invoice Phase 2', 'CHK-CONS-2502',
       [('2110', 4500, 0,    'Clear AP - Peterson Consulting'),
        ('1010', 0,    4500, 'Cash payment')],
       user_id)

    # Year-end individual donations - early givers
    je(ops, date(2025, 11, 28), 'Year-end individual donations - November', 'DON-2511',
       [('1010', 9000, 0,    'Cash donations'),
        ('4010', 0,    9000, 'Individual contributions')],
       user_id)

    # November depreciation
    je(ops, date(2025, 11, 30), 'November depreciation', 'DEP-2511',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # DECEMBER 2025
    # ------------------------------------------------------------------

    # December rent
    je(ops, date(2025, 12, 1), 'December office rent', 'RENT-2512',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # December utilities
    je(ops, date(2025, 12, 15), 'December utilities', 'UTIL-2512',
       [('5220', 480, 0,   'Electric, gas, water - peak heating'),
        ('1010', 0,   480, 'Cash payment')],
       user_id)

    # Q4 quarterly dues
    for m in quarterly_payers:
        je(ops, date(2025, 12, 1),
           f'Q4 membership dues - {m.name}',
           f'DUES-Q4-2025-{m.id}',
           [('1010', QUARTERLY_DUES, 0,              f'Q4 dues - {m.name}'),
            ('4110', 0,              QUARTERLY_DUES, f'Q4 dues - {m.name}')],
           user_id)

    # Year-end major donations
    je(ops, date(2025, 12, 15), 'Year-end individual donations - December', 'DON-2512',
       [('1010', 18000, 0,     'Cash donations - year-end giving'),
        ('4010', 0,     18000, 'Individual contributions')],
       user_id)

    # Release restricted net assets (2025 programs completed)
    je(ops, date(2025, 12, 31), 'Release donor restrictions - programs completed', 'REL-RESTRICT-2501',
       [('3200', 40000, 0,     'Release from donor restrictions'),
        ('3100', 0,     40000, 'Net assets without donor restrictions')],
       user_id)

    # Investment income - savings account interest
    je(ops, date(2025, 12, 31), 'Annual investment income - savings account interest', 'INT-2501',
       [('1010', 2200, 0,    'Interest income cash'),
        ('4410', 0,    2200, 'Investment income - interest')],
       user_id)

    # Food bank December supplies
    je(cfb, date(2025, 12, 5), 'Food bank December supplies - holiday distribution', 'SUP-CFB-2505',
       [('5320', 5500, 0,    'Holiday food distribution supplies'),
        ('1010', 0,    5500, 'Cash payment')],
       user_id)

    # Vehicle expenses year-end
    je(yep, date(2025, 12, 10), 'Chapter vehicle annual registration and inspection', 'VEH-2502',
       [('5720', 320, 0,   'Registration and inspection fees'),
        ('1010', 0,   320, 'Cash payment')],
       user_id)

    # December depreciation
    je(ops, date(2025, 12, 31), 'December depreciation', 'DEP-2512',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    db.session.commit()
    print("  ✓ 2025 transactions loaded.")


# ==================== 2026 TRANSACTIONS (YTD March) ====================

def load_2026(projects, members, user_id):
    print("  Loading 2026 YTD transactions...")
    ops  = projects['General Operations']
    yep  = projects['Youth Education Program']
    cfb  = projects['Community Food Bank']
    swp  = projects['Senior Wellness Program']
    out  = projects['Community Outreach']

    annual_payers    = members[:15]
    quarterly_payers = members[15:]

    # ------------------------------------------------------------------
    # JANUARY 2026
    # ------------------------------------------------------------------

    # Annual dues renewal - 15 members
    for m in annual_payers:
        je(ops, date(2026, 1, 15),
           f'Annual membership dues renewal - {m.name}',
           f'DUES-2026-{m.id}',
           [('1010', ANNUAL_DUES, 0,            f'2026 annual dues - {m.name}'),
            ('4110', 0,           ANNUAL_DUES,  f'2026 annual dues - {m.name}')],
           user_id)

    # Q1 quarterly dues
    for m in quarterly_payers:
        je(ops, date(2026, 1, 20),
           f'Q1 2026 membership dues - {m.name}',
           f'DUES-Q1-2026-{m.id}',
           [('1010', QUARTERLY_DUES, 0,              f'Q1 2026 dues - {m.name}'),
            ('4110', 0,              QUARTERLY_DUES, f'Q1 2026 dues - {m.name}')],
           user_id)

    # January rent
    je(ops, date(2026, 1, 1), 'January 2026 office rent', 'RENT-2601',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # January utilities
    je(ops, date(2026, 1, 15), 'January 2026 utilities', 'UTIL-2601',
       [('5220', 490, 0,   'Electric, gas, water'),
        ('1010', 0,   490, 'Cash payment')],
       user_id)

    # Government grant awarded - AR accrual (NOT YET COLLECTED - stays open on balance sheet)
    je(yep, date(2026, 1, 10), 'State youth education grant 2026 - awarded', 'GRANT-GOV-2601',
       [('1230', 60000, 0,     'Grants receivable - State Dept of Education (pending)'),
        ('4040', 0,     60000, 'Government grants revenue')],
       user_id)

    # Program supplies - AP invoice (NOT YET PAID - stays open)
    je(cfb, date(2026, 1, 8), 'Food bank January 2026 supplies invoice', 'INV-CFB-2601',
       [('5320', 3800, 0,    'Monthly food supplies'),
        ('2110', 0,    3800, 'Accounts payable - Regional Food Distributors (open)')],
       user_id)

    # Consulting 2026 - AP invoice (NOT YET PAID)
    je(ops, date(2026, 1, 20), '2026 annual audit consulting engagement', 'INV-CONS-2601',
       [('5410', 5500, 0,    'Annual audit consulting fee'),
        ('2110', 0,    5500, 'Accounts payable - Peterson Consulting (open)')],
       user_id)

    # Individual donations January
    je(ops, date(2026, 1, 31), 'January 2026 individual donations', 'DON-2601',
       [('1010', 6000, 0,    'Cash donations'),
        ('4010', 0,    6000, 'Individual contributions')],
       user_id)

    # January depreciation
    je(ops, date(2026, 1, 31), 'January 2026 depreciation', 'DEP-2601',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # FEBRUARY 2026
    # ------------------------------------------------------------------

    # February rent
    je(ops, date(2026, 2, 1), 'February 2026 office rent', 'RENT-2602',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # February utilities
    je(ops, date(2026, 2, 15), 'February 2026 utilities', 'UTIL-2602',
       [('5220', 460, 0,   'Electric, gas, water'),
        ('1010', 0,   460, 'Cash payment')],
       user_id)

    # Individual donations
    je(ops, date(2026, 2, 14), 'February 2026 individual donations', 'DON-2602',
       [('1010', 8000, 0,    'Cash donations - Valentines Day appeal'),
        ('4010', 0,    8000, 'Individual contributions')],
       user_id)

    # Program fees invoiced - AR (NOT YET COLLECTED - stays open)
    je(swp, date(2026, 2, 15), 'Senior wellness program fees Q1 2026 - invoiced', 'AR-SWP-2601',
       [('1210', 4500, 0,    'Accounts receivable - City Senior Services (open)'),
        ('4120', 0,    4500, 'Program service fees earned')],
       user_id)

    # Food bank supplies - direct cash
    je(cfb, date(2026, 2, 10), 'Food bank February 2026 supplies', 'SUP-CFB-2601',
       [('5320', 3500, 0,    'Monthly food supplies'),
        ('1010', 0,    3500, 'Cash payment')],
       user_id)

    # February depreciation
    je(ops, date(2026, 2, 28), 'February 2026 depreciation', 'DEP-2602',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # ------------------------------------------------------------------
    # MARCH 2026
    # ------------------------------------------------------------------

    # March rent
    je(ops, date(2026, 3, 1), 'March 2026 office rent', 'RENT-2603',
       [('5210', 1500, 0,    'Monthly office rent'),
        ('1010', 0,    1500, 'Cash payment')],
       user_id)

    # March utilities
    je(ops, date(2026, 3, 15), 'March 2026 utilities', 'UTIL-2603',
       [('5220', 395, 0,   'Electric, gas, water'),
        ('1010', 0,   395, 'Cash payment')],
       user_id)

    # Corporate contribution
    je(ops, date(2026, 3, 5), 'Corporate contribution - First National Bank Q1 2026', 'CORP-2601',
       [('1010', 12000, 0,     'Corporate contribution cash'),
        ('4020', 0,     12000, 'Corporate contributions')],
       user_id)

    # Partial AP payment for January food bank invoice
    je(cfb, date(2026, 3, 10), 'Partial payment - January food bank invoice', 'CHK-CFB-2601',
       [('2110', 2000, 0,    'Partial payment - Regional Food Distributors'),
        ('1010', 0,    2000, 'Cash payment')],
       user_id)

    # Vehicle expenses
    je(yep, date(2026, 3, 20), 'Chapter vehicle fuel and maintenance Q1 2026', 'VEH-2601',
       [('5720', 580, 0,   'Vehicle fuel and maintenance'),
        ('1010', 0,   580, 'Cash payment')],
       user_id)

    # March depreciation
    je(ops, date(2026, 3, 31), 'March 2026 depreciation', 'DEP-2603',
       [('5810', 450, 0,   'Monthly depreciation'),
        ('1590', 0,   450, 'Accumulated depreciation')],
       user_id)

    # Release portion of restricted funds for 2026 program use
    je(ops, date(2026, 3, 31), 'Release restricted funds - Q1 2026 programs', 'REL-RESTRICT-2601',
       [('3200', 15000, 0,     'Release from donor restrictions - Q1 programs'),
        ('3100', 0,     15000, 'Net assets without donor restrictions')],
       user_id)

    db.session.commit()
    print("  ✓ 2026 YTD transactions loaded.")


# ==================== MAIN ====================

def main():
    with app.app_context():
        print("\n" + "="*60)
        print("CARES Demo Data Loader")
        print("Fiscal Years 2025 (complete) + 2026 (YTD March)")
        print("="*60 + "\n")

        _load_accounts()

        org = Organization.query.first()
        if not org:
            raise RuntimeError("No organization found. Run init_db.py first.")

        user = User.query.filter_by(role='Admin').first()
        if not user:
            raise RuntimeError("No admin user found. Run init_db.py first.")

        clear_existing_data()

        members  = create_members(org.id)
        projects = create_projects(org.id)

        load_2025(projects, members, user.id)
        load_2026(projects, members, user.id)

        # Summary
        entry_count = JournalEntry.query.count()
        line_count  = JournalEntryLine.query.count()
        member_count = Member.query.count()

        print("\n" + "="*60)
        print("Demo Data Load Complete")
        print("="*60)
        print(f"  Members:         {member_count}")
        print(f"  Projects:        {len(projects)}")
        print(f"  Journal entries: {entry_count}")
        print(f"  Journal lines:   {line_count}")
        print("\nOpen items on balance sheet:")
        print("  AR - Grants Receivable:  $60,000 (2026 state grant)")
        print("  AR - Accounts Receivable: $4,500 (2026 senior wellness fees)")
        print("  AP - Accounts Payable:    $7,300 (food bank $1,800 + consulting $5,500)")
        print("="*60 + "\n")


if __name__ == '__main__':
    main()

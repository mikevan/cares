"""
Default Chart of Accounts
==========================

Single source of truth for the standard nonprofit chart of accounts
(FASB ASC 958 categories: assets, liabilities, net assets, revenue,
expenses).

This used to be duplicated: init_db.py's create_complete_chart_of_accounts()
kept the full, current list; blueprints/auth_routes.py's init_database() kept
a second, hand-copied, incomplete subset for standing up a fresh dev/test
database. They drifted -- the auth_routes.py copy was missing accounts
(e.g. 1410 Computer Equipment) that load_comprehensive_data.py's demo
transactions post to, which only surfaced once the test harness's Chart of
Accounts and its demo data load both correctly ran against the same
database. Both call sites now import this one list instead of maintaining
their own copy.

Each tuple is (account_number, account_name, account_type, account_subtype,
normal_balance, active).
"""

DEFAULT_CHART_OF_ACCOUNTS = [
        # ASSETS (1000-1999)
        # Cash & Cash Equivalents (1000-1099)
        ('1010', 'Operating Checking Account', 'Asset', 'Cash', 'Debit', True),
        ('1020', 'Savings Account', 'Asset', 'Cash', 'Debit', True),
        ('1030', 'Petty Cash', 'Asset', 'Cash', 'Debit', True),
        # Cash a Financial Secretary is holding/has collected but not yet
        # transferred to the Treasurer's bank account -- distinct from Petty
        # Cash above, which is a small reimbursable operating float. This is
        # what Knights of Columbus Form 1295's Schedule B reports as
        # "funds in the Financial Secretary's possession."
        ('1040', 'Financial Secretary Cash on Hand', 'Asset', 'Cash', 'Debit', True),
        
        # Receivables (1200-1299)
        ('1210', 'Accounts Receivable', 'Asset', 'Receivables', 'Debit', True),
        ('1220', 'Pledges Receivable', 'Asset', 'Receivables', 'Debit', True),
        ('1230', 'Grants Receivable', 'Asset', 'Receivables', 'Debit', True),
        
        # Investments (1300-1399)
        ('1310', 'Short-term Investments', 'Asset', 'Investments', 'Debit', True),
        ('1320', 'Long-term Investments', 'Asset', 'Investments', 'Debit', True),
        # Broken out separately (rather than folded into the two generic
        # accounts above) because Knights of Columbus Form 1295's Schedule C
        # asks for each of these by name.
        ('1330', 'Money Market Account', 'Asset', 'Investments', 'Debit', True),
        ('1340', 'Certificates of Deposit', 'Asset', 'Investments', 'Debit', True),
        ('1350', 'Mutual Fund Investments', 'Asset', 'Investments', 'Debit', True),
        
        # Fixed Assets (1400-1599)
        ('1410', 'Computer Equipment', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1420', 'Furniture & Fixtures', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1430', 'Vehicles', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1510', 'Land', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1520', 'Buildings', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1530', 'Leasehold Improvements', 'Asset', 'Fixed Assets', 'Debit', True),
        ('1590', 'Accumulated Depreciation', 'Asset', 'Contra-Asset', 'Credit', True),
        
        # LIABILITIES (2000-2999)
        # Current Liabilities (2100-2299)
        ('2110', 'Accounts Payable', 'Liability', 'Current Liabilities', 'Credit', True),
        ('2120', 'Credit Cards Payable', 'Liability', 'Current Liabilities', 'Credit', True),
        # Unpaid per capita amounts owed at period end -- Knights of Columbus
        # Form 1295's Schedule C lists these as their own liability lines,
        # separately from ordinary accounts payable.
        ('2130', 'Per Capita Payable - Supreme Council', 'Liability', 'Current Liabilities', 'Credit', True),
        ('2140', 'Per Capita Payable - State Council', 'Liability', 'Current Liabilities', 'Credit', True),
        ('2210', 'Accrued Salaries Payable', 'Liability', 'Accrued Liabilities', 'Credit', True),
        ('2220', 'Accrued Payroll Taxes', 'Liability', 'Accrued Liabilities', 'Credit', True),
        
        # Long-term Liabilities (2300-2499)
        ('2310', 'Notes Payable - Long-term', 'Liability', 'Long-term Liabilities', 'Credit', True),
        ('2320', 'Line of Credit', 'Liability', 'Long-term Liabilities', 'Credit', True),
        ('2330', 'Mortgage Payable', 'Liability', 'Long-term Liabilities', 'Credit', True),
        
        # Deferred Revenue (2400-2499)
        ('2410', 'Deferred Grant Revenue', 'Liability', 'Deferred Revenue', 'Credit', True),
        ('2420', 'Deferred Program Fees', 'Liability', 'Deferred Revenue', 'Credit', True),
        
        # NET ASSETS (3000-3999)
        ('3100', 'Net Assets Without Donor Restrictions', 'Net Asset', 'Unrestricted', 'Credit', True),
        ('3200', 'Net Assets With Donor Restrictions - Time', 'Net Asset', 'Restricted', 'Credit', True),
        ('3210', 'Net Assets With Donor Restrictions - Purpose', 'Net Asset', 'Restricted', 'Credit', True),
        ('3220', 'Net Assets With Donor Restrictions - Endowment', 'Net Asset', 'Restricted', 'Credit', True),
        
        # REVENUE (4000-4999)
        # Contributions (4000-4099)
        ('4010', 'Individual Contributions', 'Revenue', 'Contributions', 'Credit', True),
        ('4020', 'Corporate Contributions', 'Revenue', 'Contributions', 'Credit', True),
        ('4030', 'Foundation Grants', 'Revenue', 'Grants', 'Credit', True),
        ('4040', 'Government Grants', 'Revenue', 'Grants', 'Credit', True),
        
        # Membership & Fees (4100-4199)
        ('4110', 'Membership Dues', 'Revenue', 'Dues', 'Credit', True),
        # Knights of Columbus Form 1295 Schedule B's Financial Secretary
        # side reports 'dues, initiations' as a single combined line --
        # broken out here so dues and initiation fees each still report
        # correctly everywhere else in the app, then summed for that line.
        ('4115', 'Initiation Fees', 'Revenue', 'Dues', 'Credit', True),
        ('4120', 'Program Service Fees', 'Revenue', 'Program Revenue', 'Credit', True),
        
        # Special Events (4200-4299)
        ('4210', 'Special Event Revenue', 'Revenue', 'Events', 'Credit', True),
        ('4220', 'Auction Revenue', 'Revenue', 'Events', 'Credit', True),
        
        # In-Kind & Other (4300-4499)
        ('4310', 'In-Kind Donations', 'Revenue', 'In-Kind', 'Credit', True),
        # Form 1295 Schedule B's Treasurer side wants CHECKING-account
        # interest specifically -- interest earned directly inside a
        # savings/money-market/CD/mutual-fund account never passes through
        # the treasurer's hands as cash, so it belongs only in Schedule C's
        # balance, not in Schedule B's cash-received total. Post checking
        # interest to 4415 below; this account (4410) is for every other
        # kind of investment interest.
        ('4410', 'Investment Income - Interest', 'Revenue', 'Investment Income', 'Credit', True),
        ('4415', 'Interest Income - Checking Account', 'Revenue', 'Investment Income', 'Credit', True),
        ('4420', 'Investment Income - Dividends', 'Revenue', 'Investment Income', 'Credit', True),
        ('4430', 'Investment Income - Realized Gains', 'Revenue', 'Investment Income', 'Credit', True),
        
        # EXPENSES (5000-5999)
        # Personnel (5000-5099)
        ('5010', 'Salaries & Wages', 'Expense', 'Personnel', 'Debit', True),
        ('5020', 'Payroll Taxes', 'Expense', 'Personnel', 'Debit', True),
        ('5030', 'Employee Benefits', 'Expense', 'Personnel', 'Debit', True),
        ('5040', 'Retirement Plan Contributions', 'Expense', 'Personnel', 'Debit', True),
        
        # Administrative (5100-5199)
        ('5110', 'Administrative Salaries', 'Expense', 'Administrative', 'Debit', True),
        ('5120', 'Professional Fees - Legal', 'Expense', 'Administrative', 'Debit', True),
        ('5130', 'Professional Fees - Accounting', 'Expense', 'Administrative', 'Debit', True),
        
        # Occupancy (5200-5299)
        ('5210', 'Rent', 'Expense', 'Occupancy', 'Debit', True),
        ('5220', 'Utilities', 'Expense', 'Occupancy', 'Debit', True),
        ('5230', 'Property Insurance', 'Expense', 'Occupancy', 'Debit', True),
        ('5240', 'Repairs & Maintenance', 'Expense', 'Occupancy', 'Debit', True),
        
        # Supplies & Materials (5300-5399)
        ('5310', 'Office Supplies', 'Expense', 'Administrative', 'Debit', True),
        ('5320', 'Program Supplies', 'Expense', 'Program Services', 'Debit', True),
        ('5330', 'Postage & Shipping', 'Expense', 'Administrative', 'Debit', True),
        
        # Professional Services (5400-5499)
        ('5410', 'Consulting Fees', 'Expense', 'Professional Services', 'Debit', True),
        ('5420', 'Contract Services', 'Expense', 'Professional Services', 'Debit', True),
        
        # Marketing & Fundraising (5500-5599)
        ('5510', 'Marketing & Advertising', 'Expense', 'Fundraising', 'Debit', True),
        ('5520', 'Fundraising Events', 'Expense', 'Fundraising', 'Debit', True),
        ('5530', 'Printing & Publications', 'Expense', 'Fundraising', 'Debit', True),
        
        # Insurance & Licenses (5600-5699)
        ('5610', 'General Liability Insurance', 'Expense', 'Administrative', 'Debit', True),
        ('5620', 'Vehicle Insurance', 'Expense', 'Administrative', 'Debit', True),
        ('5630', 'Licenses & Permits', 'Expense', 'Administrative', 'Debit', True),
        
        # Depreciation & Equipment (5700-5799)
        ('5710', 'Equipment Maintenance', 'Expense', 'Administrative', 'Debit', True),
        ('5720', 'Vehicle Expenses', 'Expense', 'Program Services', 'Debit', True),
        
        # Other Operating Expenses (5800-5899)
        ('5810', 'Depreciation', 'Expense', 'Administrative', 'Debit', True),
        ('5820', 'Bank Fees', 'Expense', 'Administrative', 'Debit', True),
        ('5830', 'Dues & Subscriptions', 'Expense', 'Administrative', 'Debit', True),
        ('5840', 'Training & Development', 'Expense', 'Administrative', 'Debit', True),
        # Per Capita & Charitable Giving (5850-5879) -- broken out separately
        # from general council expenses because Knights of Columbus Form
        # 1295's Schedule B reports per capita to Supreme, per capita to the
        # state council, and charitable disbursements as their own lines,
        # distinct from ordinary operating expenses.
        ('5850', 'Per Capita - Supreme Council', 'Expense', 'Per Capita & Assessments', 'Debit', True),
        ('5860', 'Per Capita - State Council', 'Expense', 'Per Capita & Assessments', 'Debit', True),
        ('5870', 'Charitable Donations Given', 'Expense', 'Charitable Giving', 'Debit', True),
        
        # Interest & Financing (5900-5999)
        ('5910', 'Interest Expense', 'Expense', 'Other Expenses', 'Debit', True),
        ('5920', 'Realized Investment Losses', 'Expense', 'Other Expenses', 'Debit', True),
]

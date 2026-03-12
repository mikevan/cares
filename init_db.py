"""
Enhanced Database Initialization Script
Intelligently initializes database, chart of accounts, and sample data
"""

from app import app, db
from models import Organization, User, Project, Member, JournalEntry, ChartOfAccounts
from sqlalchemy import inspect

def check_tables_exist():
    """Check if database tables exist"""
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    required_tables = ['users', 'organizations', 'projects', 'members', 'journal_entries', 'chart_of_accounts']
    return all(table in tables for table in required_tables)

def check_chart_of_accounts_complete():
    """Check if chart of accounts has all required accounts"""
    required_accounts = [
        # Cash accounts
        '1010', '1020', '1030',
        # Receivables
        '1210',
        # Investments
        '1310',
        # Fixed Assets
        '1410', '1420', '1430', '1510', '1520', '1530',
        # Accumulated Depreciation (contra-asset)
        '1590',
        # Liabilities
        '2110', '2210', '2310', '2320', '2410',
        # Net Assets
        '3100', '3200', '3210',
        # Revenue
        '4010', '4020', '4030', '4040', '4110', '4120', '4210', '4310', '4410',
        # Expenses
        '5010', '5020', '5030', '5110', '5210', '5220', '5310', '5320',
        '5410', '5510', '5610', '5710', '5720', '5810', '5910'
    ]
    
    existing_accounts = [acc.account_number for acc in ChartOfAccounts.query.all()]
    return all(acc in existing_accounts for acc in required_accounts)

def check_comprehensive_data_loaded():
    """Check if comprehensive sample data is loaded"""
    # Check for specific projects from comprehensive data
    project_names = ['Youth Education Program', 'Community Food Bank', 'Senior Wellness Program']
    projects_exist = all(Project.query.filter_by(name=name).first() for name in project_names)
    
    # Check for reasonable number of transactions (comprehensive data has 100+)
    has_transactions = JournalEntry.query.count() > 100
    
    return projects_exist and has_transactions

def create_complete_chart_of_accounts():
    """Create complete chart of accounts for nonprofit accounting"""
    print("Creating comprehensive chart of accounts...")
    
    accounts = [
        # ASSETS (1000-1999)
        # Cash & Cash Equivalents (1000-1099)
        ('1010', 'Operating Checking Account', 'Asset', 'Cash', 'Debit', True),
        ('1020', 'Savings Account', 'Asset', 'Cash', 'Debit', True),
        ('1030', 'Petty Cash', 'Asset', 'Cash', 'Debit', True),
        
        # Receivables (1200-1299)
        ('1210', 'Accounts Receivable', 'Asset', 'Receivables', 'Debit', True),
        ('1220', 'Pledges Receivable', 'Asset', 'Receivables', 'Debit', True),
        ('1230', 'Grants Receivable', 'Asset', 'Receivables', 'Debit', True),
        
        # Investments (1300-1399)
        ('1310', 'Short-term Investments', 'Asset', 'Investments', 'Debit', True),
        ('1320', 'Long-term Investments', 'Asset', 'Investments', 'Debit', True),
        
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
        ('4120', 'Program Service Fees', 'Revenue', 'Program Revenue', 'Credit', True),
        
        # Special Events (4200-4299)
        ('4210', 'Special Event Revenue', 'Revenue', 'Events', 'Credit', True),
        ('4220', 'Auction Revenue', 'Revenue', 'Events', 'Credit', True),
        
        # In-Kind & Other (4300-4499)
        ('4310', 'In-Kind Donations', 'Revenue', 'In-Kind', 'Credit', True),
        ('4410', 'Investment Income - Interest', 'Revenue', 'Investment Income', 'Credit', True),
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
        
        # Interest & Financing (5900-5999)
        ('5910', 'Interest Expense', 'Expense', 'Other Expenses', 'Debit', True),
        ('5920', 'Realized Investment Losses', 'Expense', 'Other Expenses', 'Debit', True),
    ]
    
    for acc in accounts:
        # Check if account already exists
        existing = ChartOfAccounts.query.filter_by(account_number=acc[0]).first()
        if not existing:
            account = ChartOfAccounts(
                account_number=acc[0],
                account_name=acc[1],
                account_type=acc[2],
                account_subtype=acc[3],
                normal_balance=acc[4],
                active=acc[5]
            )
            db.session.add(account)
    
    db.session.commit()
    print(f"Chart of accounts created/updated with {len(accounts)} accounts.")

def init_database():
    """Initialize database with schema and default data"""
    print("=== Initializing CARES Database ===\n")
    
    with app.app_context():
        # Step 1: Create all tables
        print("Step 1: Creating database tables...")
        db.create_all()
        print("✓ Database tables created/verified.\n")

        from sqlalchemy import inspect, text
        _inspector = inspect(db.engine)
        _org_cols = [c['name'] for c in _inspector.get_columns('organizations')]
        if 'dues_amount' not in _org_cols:
            db.session.execute(text('ALTER TABLE organizations ADD COLUMN dues_amount NUMERIC(12,2)'))
            db.session.commit()
            print("  + Added dues_amount column to organizations\n")

        # Step 2: Create default organization
        print("Step 2: Creating default organization...")
        if not Organization.query.first():
            org = Organization(
                name=app.config.get('DEFAULT_ORGANIZATION', 'CARES - Example Chapter'),
                org_type='Chapter',
                fiscal_year_start=1
            )
            db.session.add(org)
            db.session.commit()
            print("✓ Default organization created.\n")
        else:
            print("✓ Organization already exists.\n")
        
        # Step 3: Create default admin user
        print("Step 3: Creating default admin user...")
        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@example.com',
                role='Admin',
                organization_id=1
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✓ Admin user created (username: admin, password: admin123).\n")
        else:
            print("✓ Admin user already exists.\n")
        
        # Step 4: Create complete chart of accounts
        print("Step 4: Creating chart of accounts...")
        if not check_chart_of_accounts_complete():
            create_complete_chart_of_accounts()
            print("✓ Chart of accounts created.\n")
        else:
            print("✓ Chart of accounts already complete.\n")
        
        # Step 5: Load comprehensive sample data
        print("Step 5: Loading comprehensive sample data...")
        if not check_comprehensive_data_loaded():
            print("Loading comprehensive data (this may take a moment)...")
            try:
                # Import and run the comprehensive data loader
                import load_comprehensive_data
                load_comprehensive_data.main()
                print("✓ Comprehensive sample data loaded.\n")
            except ImportError:
                print("⚠ load_comprehensive_data.py not found. Skipping sample data.\n")
            except Exception as e:
                print(f"⚠ Error loading comprehensive data: {e}\n")
        else:
            print("✓ Comprehensive data already loaded.\n")
        
        print("=== Database Initialization Complete ===\n")
        print("You can now start the application:")
        print("  • Windows: start.bat")
        print("  • Linux/Mac: ./start.sh")
        print("\nDefault login credentials:")
        print("  Username: admin")
        print("  Password: admin123")

if __name__ == '__main__':
    init_database()

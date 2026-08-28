"""
Enhanced Database Initialization Script
Intelligently initializes database, chart of accounts, and sample data
"""

from app import app, db
from models import Organization, User, Project, Member, JournalEntry, ChartOfAccounts
from default_chart_of_accounts import DEFAULT_CHART_OF_ACCOUNTS
from sqlalchemy import inspect
from audit_schema import install_audit_triggers

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
    
    accounts = DEFAULT_CHART_OF_ACCOUNTS
    
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

        with db.engine.begin() as connection:
            install_audit_triggers(connection)
        print("✓ Audit trail triggers installed/refreshed.\n")

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
                # Import and run the comprehensive data loader against
                # THIS script's app (the real dev/production app) --
                # target_app is required so this is never left ambiguous.
                import load_comprehensive_data
                load_comprehensive_data.main(target_app=app)
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

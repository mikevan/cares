"""
Enhanced Database Initialization Script
Intelligently initializes database, chart of accounts, and sample data
"""

import importlib
import os

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

# Which demo dataset a fresh database gets seeded with. Set the
# DEMO_DATASET environment variable before running init_db.py (or
# start.bat / start.sh, which call it).
#   generic (default) -- load_comprehensive_data.py: the mid-size generic
#                        nonprofit book the test suite also loads.
#   kofc              -- load_kofc_form1295_demo_data.py: six months of
#                        council-scale activity for the Regalia demo.
DEMO_DATASETS = {
    'generic': ('load_comprehensive_data', 'generic nonprofit'),
    'kofc':    ('load_kofc_form1295_demo_data', 'Knights of Columbus council'),
}

def selected_demo_dataset():
    """Name of the demo dataset to seed a fresh database with."""
    name = os.environ.get('DEMO_DATASET', 'generic').strip().lower()
    if name not in DEMO_DATASETS:
        print(f"! Unknown DEMO_DATASET={name!r} -- falling back to 'generic'.")
        name = 'generic'
    return name

def check_demo_data_loaded():
    """True if ANY demo dataset is already loaded.

    Deliberately dataset-agnostic. This check used to look for
    load_comprehensive_data.py's own project names plus >100 journal
    entries, which meant a database seeded by any OTHER loader -- the
    ~90-entry council book from load_kofc_form1295_demo_data.py, for
    instance -- read as "empty" here, and so got silently wiped and
    replaced with the generic data on the next init_db.py (and therefore
    start.bat) run.
    """
    return Project.query.first() is not None and JournalEntry.query.count() > 0

def _default_organization_id():
    org = Organization.query.first()
    return org.id if org else None


def create_complete_chart_of_accounts():
    """Create complete chart of accounts for nonprofit accounting"""
    print("Creating comprehensive chart of accounts...")

    accounts = DEFAULT_CHART_OF_ACCOUNTS
    organization_id = _default_organization_id()

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
                active=acc[5],
                # chart_of_accounts is a DIRECT organization table: unlike
                # journal entries or invoices it has no parent row to inherit
                # from, so nothing sets this but the code that creates the
                # account. Omitting it leaves organization_id NULL, and NULL
                # is invisible to every RLS policy -- permanently, and in
                # silence. See assign_accounts_to_organization() below.
                organization_id=organization_id,
            )
            db.session.add(account)

    db.session.commit()
    print(f"Chart of accounts created/updated with {len(accounts)} accounts.")


def assign_accounts_to_organization():
    """Give any organization-less account to the deployment's organization.

    Runs unconditionally, including when the chart is already "complete",
    because the damage this repairs is invisible from the application side.

    How it happens: chart_of_accounts only gained organization_id when
    multi-tenancy landed. migrate_production.py backfills the accounts that
    IT adds, but it runs before this script seeds DEFAULT_CHART_OF_ACCOUNTS,
    so the base accounts -- 1010 checking, 4110 dues revenue, the whole 5000
    expense range -- were created afterwards with no organization at all.

    The symptom is not an error. RLS simply omits those rows, so any query
    that joins through chart_of_accounts silently loses the join and reports
    zero: a Form 1295 showing 33 members paying $48 and $0.00 of dues
    collected, project spend of $0.00 on every project, a checking balance
    of $0.00 against real receipts. Every count correct, every amount wrong.
    That is a far worse failure than a crash on a document a trustee signs.
    """
    organization_id = _default_organization_id()
    if organization_id is None:
        print("  ! No organization exists yet -- cannot assign accounts.")
        return 0

    orphans = ChartOfAccounts.query.filter_by(organization_id=None).all()
    for account in orphans:
        account.organization_id = organization_id
    if orphans:
        db.session.commit()
        print(f"  + Assigned {len(orphans)} account(s) with no organization "
              f"to organization {organization_id}.")
    else:
        print("  All accounts belong to an organization.")
    return len(orphans)

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

        # Unconditional: an account can exist and still be invisible.
        assign_accounts_to_organization()
        print("")
        
        # Step 5: Load the selected demo dataset
        print("Step 5: Loading demo data...")
        if not check_demo_data_loaded():
            dataset = selected_demo_dataset()
            module_name, label = DEMO_DATASETS[dataset]
            print(f"Loading the {label} demo dataset (DEMO_DATASET={dataset})...")
            try:
                # Both loaders are destructive -- they wipe transactional
                # data and reload. load_comprehensive_data.main() takes an
                # explicit target_app (deliberately no default, so no call
                # site is ever ambiguous about which database it wipes);
                # the council loader binds to this same app on import.
                # Commit before handing off. check_demo_data_loaded() above
                # ran queries, which opens a read transaction that SQLAlchemy
                # holds until something ends it -- keeping ACCESS SHARE locks
                # on projects and journal_entries. The loaders run in their
                # own app context (and therefore their own session) and
                # install audit triggers on a separate connection, where
                # DROP TRIGGER needs ACCESS EXCLUSIVE on those same tables.
                # Without this commit those two wait on each other forever,
                # with no error raised -- Postgres blocking is not a failure.
                db.session.commit()

                loader = importlib.import_module(module_name)
                if module_name == 'load_comprehensive_data':
                    loader.main(target_app=app)
                else:
                    loader.main()
                print(f"OK {label} demo data loaded.\n")
            except ImportError:
                print(f"! {module_name}.py not found. Skipping demo data.\n")
            except Exception as e:
                print(f"! Error loading demo data: {e}\n")
        else:
            print("OK Demo data already present -- leaving it alone.\n")
        
        print("=== Database Initialization Complete ===\n")
        print("You can now start the application:")
        print("  • Windows: start.bat")
        print("  • Linux/Mac: ./start.sh")
        print("\nDefault login credentials:")
        print("  Username: admin")
        print("  Password: admin123")

if __name__ == '__main__':
    init_database()

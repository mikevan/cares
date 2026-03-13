"""
CARES Production Migration Script
Safely adds missing columns/accounts and resets demo state on every startup.
Safe to run multiple times (idempotent structural changes).
Demo behavior: org settings preserved, admin user reset fresh every run.
"""

from app import app, db
from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project
from datetime import datetime
from sqlalchemy import inspect, text


# ==================== STRUCTURAL MIGRATIONS ====================

def add_organization_css_file():
    print("Step 0a: Checking organizations.css_file column...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('organizations')]
    if 'css_file' not in columns:
        db.session.execute(text('ALTER TABLE organizations ADD COLUMN css_file VARCHAR(100)'))
        db.session.commit()
        print("  + Added css_file column to organizations")
    else:
        print("✓ css_file column exists")


def add_dues_columns():
    print("\nStep 0b: Checking dues columns...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('organizations')]
    if 'dues_amount' not in columns:
        db.session.execute(text('ALTER TABLE organizations ADD COLUMN dues_amount NUMERIC(12,2)'))
        db.session.commit()
        print("  + Added dues_amount to organizations")
    else:
        print("✓ dues_amount column exists")
    # member_dues_payments table is created by db.create_all()
    tables = inspect(db.engine).get_table_names()
    if 'member_dues_payments' in tables:
        print("✓ member_dues_payments table exists")
    else:
        print("  ⚠ member_dues_payments table not found after create_all()")


# ==================== DEMO SYSTEM SETUP ====================

def ensure_default_organization():
    """Create default org if none exists. Preserves existing org settings."""
    from models import Organization
    print("\nStep 1: Checking organization...")
    if not Organization.query.first():
        org = Organization(
            name=app.config.get('DEFAULT_ORGANIZATION', 'CARES - Example Chapter'),
            org_type='Chapter',
            fiscal_year_start=1,
        )
        db.session.add(org)
        db.session.commit()
        print("  + Created default organization")
    else:
        print("✓ Organization exists (settings preserved)")


def reset_admin_user():
    """
    Reset admin user credentials on every startup.
    Updates in place to avoid FK violations from journal_entries.created_by.
    Demo system: testers cannot permanently change admin credentials.
    """
    from models import User, Organization
    print("\nStep 2: Resetting admin user...")

    org = Organization.query.first()
    if not org:
        raise RuntimeError("No organization found — cannot create admin user")

    admin = User.query.filter_by(username='admin').first()
    if admin:
        admin.email = 'admin@example.com'
        admin.role = 'Admin'
        admin.organization_id = org.id
        admin.set_password('admin123')
    else:
        admin = User(
            username='admin',
            email='admin@example.com',
            role='Admin',
            organization_id=org.id,
        )
        admin.set_password('admin123')
        db.session.add(admin)

    db.session.commit()
    print("✓ Admin user reset (admin / admin123)")

# ==================== CHART OF ACCOUNTS ====================

def add_missing_accounts():
    print("\nStep 3: Checking Chart of Accounts...")
    required_accounts = [
        ('1310', 'Short-term Investments',                  'Asset',    'Investments',          'Debit'),
        ('1410', 'Computer Equipment',                       'Asset',    'Fixed Assets',         'Debit'),
        ('1420', 'Furniture & Fixtures',                     'Asset',    'Fixed Assets',         'Debit'),
        ('1430', 'Vehicles',                                 'Asset',    'Fixed Assets',         'Debit'),
        ('1590', 'Accumulated Depreciation',                 'Asset',    'Contra-Asset',         'Credit'),
        ('2210', 'Accrued Salaries Payable',                 'Liability','Accrued Liabilities',  'Credit'),
        ('2310', 'Notes Payable - Long-term',                'Liability','Long-term Liabilities','Credit'),
        ('2320', 'Line of Credit',                           'Liability','Long-term Liabilities','Credit'),
        ('2410', 'Deferred Grant Revenue',                   'Liability','Deferred Revenue',     'Credit'),
        ('3210', 'Net Assets With Donor Restrictions - Purpose','Net Asset','Restricted',        'Credit'),
        ('4040', 'Government Grants',                        'Revenue',  'Grants',               'Credit'),
        ('4120', 'Program Service Fees',                     'Revenue',  'Program Revenue',      'Credit'),
        ('5030', 'Employee Benefits',                        'Expense',  'Personnel',            'Debit'),
        ('5720', 'Vehicle Expenses',                         'Expense',  'Program Services',     'Debit'),
        ('5910', 'Interest Expense',                         'Expense',  'Other Expenses',       'Debit'),
    ]
    added = 0
    for acc_data in required_accounts:
        if not ChartOfAccounts.query.filter_by(account_number=acc_data[0]).first():
            db.session.add(ChartOfAccounts(
                account_number=acc_data[0],
                account_name=acc_data[1],
                account_type=acc_data[2],
                account_subtype=acc_data[3],
                normal_balance=acc_data[4],
                active=True,
            ))
            added += 1
            print(f"  + Adding {acc_data[0]} - {acc_data[1]}")
    if added:
        db.session.commit()
        print(f"✓ Added {added} missing accounts")
    else:
        print("✓ All required accounts exist")


def fix_account_names():
    print("\nStep 4: Verifying account names...")
    fixes = [('5810', 'Depreciation')]
    fixed = 0
    for acc_number, correct_name in fixes:
        account = ChartOfAccounts.query.filter_by(account_number=acc_number).first()
        if account and account.account_name != correct_name:
            print(f"  ! Fixing {acc_number}: '{account.account_name}' -> '{correct_name}'")
            account.account_name = correct_name
            fixed += 1
    if fixed:
        db.session.commit()
        print(f"✓ Fixed {fixed} account names")
    else:
        print("✓ All account names correct")


def fix_depreciation_entries():
    print("\nStep 5: Checking depreciation entries...")
    acc_5810 = ChartOfAccounts.query.filter_by(account_number='5810').first()
    acc_1510 = ChartOfAccounts.query.filter_by(account_number='1510').first()
    acc_1590 = ChartOfAccounts.query.filter_by(account_number='1590').first()

    if not acc_5810 or not acc_1590:
        print("  ⚠ Required accounts missing — skipping depreciation check")
        return

    bad_entries = []
    if acc_1510:
        for entry in JournalEntry.query.filter(JournalEntry.description.ilike('%depreciation%')).all():
            lines = JournalEntryLine.query.filter_by(journal_entry_id=entry.id).all()
            if any(l.account_id == acc_5810.id for l in lines) and \
               any(l.account_id == acc_1510.id for l in lines):
                bad_entries.append(entry)

    if bad_entries:
        for entry in bad_entries:
            for line in JournalEntryLine.query.filter_by(journal_entry_id=entry.id).all():
                if line.account_id == acc_1510.id:
                    line.account_id = acc_1590.id
        db.session.commit()
        print(f"✓ Fixed {len(bad_entries)} depreciation entries")
    else:
        print("✓ No depreciation entries need fixing")


# ==================== INTEGRITY & SUMMARY ====================

def verify_database_integrity():
    print("\nStep 6: Verifying database integrity...")
    critical = ['1010', '1590', '3100', '4010', '5010', '5810']
    missing = [n for n in critical if not ChartOfAccounts.query.filter_by(account_number=n).first()]
    if missing:
        print(f"  ⚠ WARNING: Missing critical accounts: {', '.join(missing)}")
        return False
    print("✓ All critical accounts exist")
    print(f"✓ {JournalEntry.query.count()} journal entries in database")
    return True


def show_summary():
    print("\n" + "="*60)
    print("Database Summary:")
    print("="*60)
    print(f"Chart of Accounts: {ChartOfAccounts.query.filter_by(active=True).count()} active accounts")
    print(f"Transactions:      {JournalEntry.query.count()} journal entries, "
          f"{JournalEntryLine.query.count()} lines")
    print(f"Translation cache: table ready")
    print("="*60)


# ==================== MAIN ====================

def main():
    with app.app_context():
        print("\n" + "="*60)
        print("CARES Production Migration")
        print("Structural changes are idempotent.")
        print("Admin user is reset on every startup (demo system).")
        print("="*60 + "\n")

        try:
            # Create all tables including translation_cache (idempotent)
            db.create_all()
            print("✓ Database tables verified/created\n")

            # Structural column migrations
            add_organization_css_file()
            add_dues_columns()

            # Demo system setup
            ensure_default_organization()
            reset_admin_user()

            # Chart of accounts
            add_missing_accounts()
            fix_account_names()
            fix_depreciation_entries()

            # Verify and summarise
            verify_database_integrity()
            show_summary()

            print("\n✓ Migration complete — starting demo data load next")

        except Exception as e:
            print(f"\n❌ ERROR during migration: {e}")
            db.session.rollback()
            raise


if __name__ == '__main__':
    main()

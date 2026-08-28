"""
CARES Production Migration Script
Safely adds missing columns/accounts and resets demo state on every startup.
Safe to run multiple times (idempotent structural changes).
Demo behavior: org settings preserved, admin user reset fresh every run.
"""

from app import app, db
from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project, ProjectAssignment, Member, MembershipEvent
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


def add_project_previous_id_column():
    print("\nStep 0c: Checking projects.previous_project_id column...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('projects')]
    if 'previous_project_id' not in columns:
        db.session.execute(text('ALTER TABLE projects ADD COLUMN previous_project_id INTEGER REFERENCES projects(id)'))
        db.session.commit()
        print("  + Added previous_project_id column to projects")
    else:
        print("✓ previous_project_id column exists")


def add_must_change_password_column():
    print("\nStep 0e: Checking users.must_change_password column...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('users')]
    if 'must_change_password' not in columns:
        db.session.execute(text('ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.commit()
        print("  + Added must_change_password column to users")
    else:
        print("✓ must_change_password column exists")


def add_project_is_fundraiser_column():
    print("\nStep 0f: Checking projects.is_fundraiser column...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('projects')]
    if 'is_fundraiser' not in columns:
        db.session.execute(text('ALTER TABLE projects ADD COLUMN is_fundraiser BOOLEAN NOT NULL DEFAULT FALSE'))
        db.session.commit()
        print("  + Added is_fundraiser column to projects")
    else:
        print("✓ is_fundraiser column exists")


def add_kofc_council_identity_columns():
    print("\nStep 0g: Checking organizations.council_number/district_deputy_name columns...")
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('organizations')]
    if 'council_number' not in columns:
        db.session.execute(text('ALTER TABLE organizations ADD COLUMN council_number VARCHAR(20)'))
        db.session.commit()
        print("  + Added council_number column to organizations")
    else:
        print("✓ council_number column exists")
    if 'district_deputy_name' not in columns:
        db.session.execute(text('ALTER TABLE organizations ADD COLUMN district_deputy_name VARCHAR(200)'))
        db.session.commit()
        print("  + Added district_deputy_name column to organizations")
    else:
        print("✓ district_deputy_name column exists")


def create_membership_events_table():
    print("\nStep 0h: Checking membership_events table...")
    tables = inspect(db.engine).get_table_names()
    if 'membership_events' not in tables:
        db.session.execute(text("""
            CREATE TABLE membership_events (
                id SERIAL PRIMARY KEY,
                member_id INTEGER NOT NULL REFERENCES members(id),
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                event_type VARCHAR(50) NOT NULL,
                event_date DATE NOT NULL,
                notes TEXT,
                created_by INTEGER REFERENCES users(id),
                created_at TIMESTAMP
            )
        """))
        db.session.commit()
        print("  + Created membership_events table")
    else:
        print("✓ membership_events table exists")


def create_form_1295_submissions_table():
    print("\nStep 0i: Checking form_1295_submissions table...")
    tables = inspect(db.engine).get_table_names()
    if 'form_1295_submissions' not in tables:
        db.session.execute(text("""
            CREATE TABLE form_1295_submissions (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id),
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                misc_income_explanation TEXT,
                misc_liabilities_explanation TEXT,
                attested_by_user_id INTEGER REFERENCES users(id),
                attested_at TIMESTAMP,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                CONSTRAINT uq_form1295_org_period UNIQUE (organization_id, period_start, period_end)
            )
        """))
        db.session.commit()
        print("  + Created form_1295_submissions table")
    else:
        print("✓ form_1295_submissions table exists")


def backfill_membership_events():
    """
    One-time backfill: every existing member with no membership_events row
    at all gets a single 'Initiation' event dated at their join_date (or,
    if join_date is somehow blank, their created_at date -- see the
    reconciliation warning on the Form 1295 page for members this can't
    place precisely). Safe to run multiple times: only members with zero
    events are touched, so a real event recorded later never gets
    clobbered by a re-run of this migration.
    """
    print("\nStep 0j: Backfilling membership_events for existing members...")
    members_without_events = Member.query.filter(
        ~Member.id.in_(db.session.query(MembershipEvent.member_id).distinct())
    ).all()
    added = 0
    for member in members_without_events:
        event_date = member.join_date or (member.created_at.date() if member.created_at else datetime.utcnow().date())
        db.session.add(MembershipEvent(
            member_id=member.id,
            organization_id=member.organization_id,
            event_type='Initiation',
            event_date=event_date,
            notes='Backfilled by migration -- original join event predates membership event tracking.',
        ))
        added += 1
    if added:
        db.session.commit()
        print(f"  + Backfilled {added} Initiation event(s) for existing members")
    else:
        print("✓ No members missing a membership event")


def backfill_project_assignments():
    """
    One-time backfill: copy rows from the old project_leaders/project_members
    many-to-many tables into the new project_assignments history table, as
    still-open (end_date NULL) assignments. Safe to run multiple times --
    skips any pairing that already has an assignment row.

    The old project_leaders/project_members tables are intentionally left in
    place afterward (not dropped) so this backfill can be safely re-run and
    so no data is destroyed if something about the new model needs revisiting.
    """
    print("\nStep 0d: Backfilling project_assignments from legacy tables...")
    tables = inspect(db.engine).get_table_names()
    added = 0

    if 'project_leaders' in tables:
        rows = db.session.execute(text('SELECT project_id, member_id FROM project_leaders')).fetchall()
        for project_id, member_id in rows:
            exists = ProjectAssignment.query.filter_by(
                project_id=project_id, member_id=member_id, role='Leader'
            ).first()
            if not exists:
                project = Project.query.get(project_id)
                db.session.add(ProjectAssignment(
                    project_id=project_id,
                    member_id=member_id,
                    role='Leader',
                    start_date=(project.start_date if project and project.start_date else datetime.utcnow().date()),
                ))
                added += 1
    else:
        print("  (no legacy project_leaders table found -- nothing to backfill for leaders)")

    if 'project_members' in tables:
        rows = db.session.execute(text('SELECT project_id, member_id FROM project_members')).fetchall()
        for project_id, member_id in rows:
            exists = ProjectAssignment.query.filter_by(
                project_id=project_id, member_id=member_id, role='Volunteer'
            ).first()
            if not exists:
                project = Project.query.get(project_id)
                db.session.add(ProjectAssignment(
                    project_id=project_id,
                    member_id=member_id,
                    role='Volunteer',
                    start_date=(project.start_date if project and project.start_date else datetime.utcnow().date()),
                ))
                added += 1
    else:
        print("  (no legacy project_members table found -- nothing to backfill for volunteers)")

    if added:
        db.session.commit()
        print(f"  + Backfilled {added} project_assignments row(s) from legacy tables")
    else:
        print("✓ No legacy rows to backfill (already migrated, or none existed)")


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
        admin.must_change_password = True
    else:
        admin = User(
            username='admin',
            email='admin@example.com',
            role='Admin',
            organization_id=org.id,
            must_change_password=True,
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
        # Added for Knights of Columbus Form 1295 Schedule B/C support --
        # see default_chart_of_accounts.py for why each of these exists.
        ('1040', 'Financial Secretary Cash on Hand',        'Asset',    'Cash',                 'Debit'),
        ('1330', 'Money Market Account',                    'Asset',    'Investments',          'Debit'),
        ('1340', 'Certificates of Deposit',                 'Asset',    'Investments',          'Debit'),
        ('1350', 'Mutual Fund Investments',                 'Asset',    'Investments',          'Debit'),
        ('2130', 'Per Capita Payable - Supreme Council',    'Liability','Current Liabilities',  'Credit'),
        ('2140', 'Per Capita Payable - State Council',      'Liability','Current Liabilities',  'Credit'),
        ('5850', 'Per Capita - Supreme Council',            'Expense',  'Per Capita & Assessments','Debit'),
        ('5860', 'Per Capita - State Council',              'Expense',  'Per Capita & Assessments','Debit'),
        ('5870', 'Charitable Donations Given',              'Expense',  'Charitable Giving',    'Debit'),
        ('4115', 'Initiation Fees',                          'Revenue',  'Dues',                 'Credit'),
        ('4415', 'Interest Income - Checking Account',       'Revenue',  'Investment Income',    'Credit'),
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
            add_project_previous_id_column()
            backfill_project_assignments()
            add_must_change_password_column()
            add_project_is_fundraiser_column()
            add_kofc_council_identity_columns()
            create_membership_events_table()
            create_form_1295_submissions_table()

            # Demo system setup
            ensure_default_organization()
            reset_admin_user()

            # Chart of accounts
            add_missing_accounts()
            backfill_membership_events()
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

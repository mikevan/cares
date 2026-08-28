"""
Chapter initialization -- FIRST RUN ONLY
========================================

Stands up an empty, production-ready database for ONE real chapter or
council: schema, that chapter's organization record, its first
administrator, the standard chart of accounts, and the audit triggers.
Then it stops. No members, no projects, no transactions, no fiction.

This file deliberately shares NOTHING with the demo startup path. It does
not import init_db.py, load_comprehensive_data.py,
load_kofc_form1295_demo_data.py, or demo_guard.py, and it never will --
the guard in demo_guard.py exists because those paths CAN wipe data and
must be prevented from doing so; this path has no wipe in it to prevent.
The separation is structural rather than conditional, so there is no flag
anyone can set, and no environment variable anyone can forget, that turns
a chapter's initialization into a demo load.

What it DOES share, correctly: models.py, and the standard chart of
accounts in default_chart_of_accounts.py. Those are the product, not the
demo -- a council's books need the same account numbers the software
reports on.

RUN IT ONCE, when a chapter is onboarded:

    python init_chapter.py --council-name "Bishop Kelley Council" \\
                           --council-number 14203 \\
                           --admin-username jsmith \\
                           --admin-email jsmith@example.org

Subsequent deployments run migrate_production.py only (see
start_production.ps1 / start_production.sh), which applies schema changes
and touches no data.

THE ADMIN PASSWORD
------------------
Set INIT_ADMIN_PASSWORD in the environment, or let this generate one and
print it once. Either way the account is created with
must_change_password=True, so the real administrator sets their own
password at first login and the initial value stops being a credential.
There is no default password anywhere in this file -- 'admin123' lives in
the demo path, and this is not the demo path.

SAFETY
------
Refuses to run if an organization already exists, because "first run only"
is the whole contract. Re-running it against a live chapter would be a
second organization, a second admin, and a chart of accounts collision.
Use --force only to complete an initialization that failed partway.
"""
import argparse
import os
import secrets
import string
import sys

from app import app, db
from audit_schema import install_audit_triggers
from default_chart_of_accounts import DEFAULT_CHART_OF_ACCOUNTS
from models import ChartOfAccounts, Organization, User


def generate_password(length=20):
    """A password nobody has to remember -- it is replaced at first login."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def create_schema():
    print('\nStep 1: Creating database schema...')
    db.create_all()
    print('  Tables created (existing tables are left as they are).')


def create_organization(args):
    print('\nStep 2: Creating the chapter organization...')
    org = Organization(
        name=args.council_name,
        org_type='Chapter',
        council_number=args.council_number,
        district_deputy_name=args.district_deputy,
        ein=args.ein,
        city=args.city,
        state=args.state,
        email=args.email,
        fiscal_year_start=args.fiscal_year_start,
        dues_amount=args.dues_amount,
        # Drives BOTH the stylesheet (static/css/<css_file>) and, via
        # app.py::inject_branding, the header emblem (static/images/<code>.svg,
        # falling back to .png). Defaults to the Knights theme because that is
        # what this edition is for; pass --css-file to override.
        css_file=args.css_file,
    )
    db.session.add(org)
    db.session.commit()
    print(f'  {org.name}' + (f' (council #{org.council_number})' if org.council_number else ''))
    print(f'  Branding: {org.css_file} (header emblem: images/{org.css_file[:-4]}.svg|png)')
    if org.dues_amount is None:
        print('  NOTE: no --dues-amount given. Set the annual dues in Settings')
        print('        before using the Annual Dues Roster -- it refuses to post')
        print('        while the rate is unset.')
    return org


def create_admin(org, args):
    print('\nStep 3: Creating the first administrator...')
    password = os.environ.get('INIT_ADMIN_PASSWORD') or generate_password()
    from_env = bool(os.environ.get('INIT_ADMIN_PASSWORD'))

    admin = User(
        username=args.admin_username,
        email=args.admin_email,
        role='Admin',
        organization_id=org.id,
        active=True,
        must_change_password=True,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    print(f'  Username: {admin.username}')
    if from_env:
        print('  Password: (taken from INIT_ADMIN_PASSWORD)')
    else:
        print(f'  Password: {password}')
        print('  ^ Printed once and not stored anywhere else. Give it to the')
        print('    administrator over a channel you trust, then discard it.')
    print('  This account must change its password at first login.')
    return admin


def create_chart_of_accounts():
    print('\nStep 4: Creating the chart of accounts...')
    existing = {a.account_number for a in ChartOfAccounts.query.all()}
    added = 0
    for number, name, acct_type, subtype, normal_balance, active in DEFAULT_CHART_OF_ACCOUNTS:
        if number in existing:
            continue
        db.session.add(ChartOfAccounts(
            account_number=number, account_name=name, account_type=acct_type,
            account_subtype=subtype, normal_balance=normal_balance, active=active,
        ))
        added += 1
    db.session.commit()
    print(f'  {added} accounts created ({len(existing)} already present).')


def install_triggers():
    print('\nStep 5: Installing the audit trail...')
    with db.engine.begin() as connection:
        install_audit_triggers(connection)
    print('  Triggers installed on every audited table.')
    print('  Every change from here on is recorded and hash-chained.')


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog='init_chapter.py',
        description='Initialize a database for one real chapter. First run only.',
    )
    p.add_argument('--council-name', required=True,
                   help='The chapter or council name, as it should appear in the app.')
    p.add_argument('--council-number', default=None,
                   help='Knights of Columbus council number (printed on Form 1295).')
    p.add_argument('--district-deputy', default=None, dest='district_deputy',
                   help='District Deputy name (printed on Form 1295).')
    p.add_argument('--admin-username', required=True,
                   help='Username for the first administrator.')
    p.add_argument('--admin-email', required=True,
                   help='Email for the first administrator.')
    p.add_argument('--dues-amount', type=float, default=None,
                   help='Annual dues per member. Can also be set later in Settings.')
    p.add_argument('--css-file', default='kofc.css', dest='css_file',
                   help='Branding theme file in static/css/. Also selects the header '
                        'emblem in static/images/ (kofc.css -> kofc.svg|png). '
                        'Default kofc.css; use branding.css for an unbranded chapter.')
    p.add_argument('--ein', default=None, help='Employer Identification Number.')
    p.add_argument('--city', default=None)
    p.add_argument('--state', default=None)
    p.add_argument('--email', default=None, help='Chapter contact email.')
    p.add_argument('--fiscal-year-start', type=int, default=1, dest='fiscal_year_start',
                   help='Fiscal year start month, 1-12. Default 1 (January).')
    p.add_argument('--force', action='store_true',
                   help='Proceed even though an organization already exists. Only for '
                        'completing an initialization that failed partway.')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    with app.app_context():
        print('=' * 62)
        print('CHAPTER INITIALIZATION -- first run only')
        print('=' * 62)
        print('Creates an EMPTY set of books for one chapter. No demo data is')
        print('loaded, now or ever, by this script.')

        # create_all first, so the existence check below can actually query.
        create_schema()

        existing_org = Organization.query.first()
        if existing_org and not args.force:
            print('\nREFUSING TO RUN.')
            print(f"  This database already holds an organization: '{existing_org.name}'.")
            print('  init_chapter.py is a first-run script. Running it again would')
            print('  create a second organization and a second administrator beside')
            print('  the existing ones.')
            print('\n  To apply schema changes to an existing chapter, run:')
            print('      python migrate_production.py')
            print('  (or use start_production.ps1 / start_production.sh, which do')
            print('  that and nothing else).')
            print('\n  To complete an initialization that failed partway, re-run')
            print('  with --force.')
            return 1

        try:
            org = create_organization(args)
            create_admin(org, args)
            create_chart_of_accounts()
            install_triggers()
        except Exception as e:
            db.session.rollback()
            print(f'\nERROR during initialization: {e}')
            import traceback
            traceback.print_exc()
            return 1

        print('\n' + '=' * 62)
        print('CHAPTER INITIALIZED')
        print('=' * 62)
        print(f'  Organization:  {org.name}')
        print(f'  Members:       0')
        print(f'  Projects:      0')
        print(f'  Transactions:  0')
        print('\nThe books are empty and ready for the chapter to enter its own')
        print('opening balances. Start the application with:')
        print('    .\\start_production.ps1        (Windows)')
        print('    ./start_production.sh         (Linux / Render)')
        return 0


if __name__ == '__main__':
    sys.exit(main())

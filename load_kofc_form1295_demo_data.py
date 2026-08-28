"""
Knights of Columbus -- Six-Month Council Demo Data Loader
=========================================================

Seeds one Knights of Columbus council's books with SIX MONTHS of
realistic, council-scale activity -- roughly 90 posted journal entries
across January 1 - June 30, 2026 -- so that opening the app for a demo
shows something that reads like a real council's ledger, and so every
line of Form 1295's Schedule A, B, and C (see services/kofc_form_1295.py)
has a real, non-trivial, correctly computed number behind it.

WHY THIS WIPES FIRST
--------------------
An earlier version of this script COMPOSED with load_comprehensive_data.py's
demo data. That produced correct schedules on top of the wrong book: the
generic-nonprofit base data carries a $522K operating checking balance,
$60K government grants, and $38K gala ticket sales, which is a mid-size
501(c)(3), not a council. On Form 1295 that swamped the story -- named
fundraiser lines of $3,200 and $1,800 sitting under $91,100 of
"miscellaneous income."

So this loader now seeds the whole book itself, at council scale:
roughly $44K in total assets, $13K in the operating checking account,
$48 annual dues, per capita measured in hundreds. It clears transactional
data first (the same FK-safe table list load_comprehensive_data.py uses),
preserving organizations, the chart of accounts, the translation cache,
and the admin user.

load_comprehensive_data.py is left completely alone -- it is still the
generic CARES demo, and it is still what tests/conftest.py loads, so no
test in the suite is affected by anything in this file.

    !! This DELETES all members, projects, transactions, invoices,      !!
    !! donors, and vendors in the database it points at, and TRUNCATES  !!
    !! the audit log. It is a DEMO loader. Do not run it against a      !!
    !! council's real books.                                            !!

THE AUDIT TRAIL
---------------
The load attaches the audit triggers if they are missing (init_db.py
installs them, migrate_production.py does not, so a database brought up
through migrate_and_start.bat/.sh has none), then truncates audit_log,
then seeds -- so the Trustee Audit Report opens on this council's book
being created rather than on a wall of DELETEs from whatever was there
before. The rebuilt chain starts at genesis and verifies clean.

The rows carry the real wall-clock time of the load; they are NOT
backdated into the audit period. See reset_audit_log() for why not.

WHAT SIX MONTHS LOOKS LIKE HERE
-------------------------------
  Membership (Schedule A)
    - 34-member founding roster with join dates spread across 1998-2025.
    - Four additions during the period, one of EACH addition type.
    - Five deductions during the period, one of EACH deduction type.
    - Roll-forward: 34 + 4 - 5 = 33, and 33 members are actually Active,
      so the page reconciles.
    - A 2026 dues record for every one of the 38 members who was on the
      roll at any point; 33 paid, 5 unpaid -- and the ledger's dues
      revenue is exactly those 33 members x $48, so the roster page and
      the money agree.

  Cash transactions (Schedule B)
    - Dues posted ONE ENTRY PER MEMBER into a project named 'Dues',
      exactly as the application's own Annual Dues Roster does (see
      post_member_dues), each linked back to that member's dues record.
      21 members paid straight to checking; 12 paid cash to the Financial
      Secretary (1040) and were deposited later -- except one on June 26,
      deliberately still in hand, so closing "funds in possession" is a
      real $48 rather than zero.
    - Initiation fees (4115) for the four new members.
    - Three fundraisers, deliberately different sizes: Spring Raffle
      ($3,200 across four ticket-sale postings, with printing and prize
      costs), Pancake Breakfast ($1,800 across three seatings, with food
      costs), and Golf Outing ($600). Only the top two get named lines on
      the real form; the golf outing's $600 correctly falls through into
      miscellaneous income rather than vanishing.
    - Checking interest (4415) monthly AND savings/money-market interest
      (4410) -- proving the split holds: only the former reaches
      Schedule B.
    - Per capita to Supreme and State: assessed in January, paid in
      February. Assessed and paid inside the same period, so the expense
      and the cash agree.
    - Six charitable donations, monthly council operating costs (hall
      rent, utilities, insurance, postage, printing, bank fees, officer
      training, state convention travel), and transfers in BOTH
      directions between checking and savings.

  Accounts payable (six months, /ap)
    - Nine vendors, five of them flagged is_1099 -- individuals and
      unincorporated firms paid for services (bookkeeper, cleaner,
      grounds, organist, audio technician). The four corporations are
      flagged False, which is the distinction the 1099 report exists to
      make and the reason it is a vendor property rather than a guess.
    - Twenty invoices raised and settled across March-August, posted
      through services/ap_service.py -- the same path the Invoices screen
      uses -- so each carries its GL entry link, amount_paid, status, and
      an InvoicePayment row.
    - Five invoices deliberately left open, their due dates anchored to
      the day the demo is loaded so that every aging bucket (Current,
      1-30, 31-60, 61-90, 90+) has a real invoice in it on any run date.
      Hardcoded dates would collapse into a single 90+ column within
      months. See AP_OPEN_INVOICES.

  Financial position (Schedule C)
    - Opening balances at 12/31/2025 across checking, savings, money
      market, CDs and mutual funds. No fixed assets: this council rents
      its meeting space and has capitalized nothing.
    - $310 of accounts payable carried in from December, plus the vendor
      invoices still unpaid at June 30, so the miscellaneous-liabilities
      line is a real number with a real composition. The wizard note for
      it is generated from the ledger (see misc_liabilities_explanation)
      rather than hardcoded, because the open invoices move with the load
      date and an explanation that disagreed with the figure beside it
      would be worse than none.

  The Form1295Submission wizard
    - Both miscellaneous lines have saved explanations, so nothing on
      screen reads "Needs explanation". Nothing is attested, so the
      attest button is still there to click through. (To demonstrate the
      "Needs explanation" state instead, clear either explanation in the
      wizard.)

TWO REPORTING BUGS -- NOW FIXED IN THE CODE
-------------------------------------------
Both defects below were real and were found by reconciling this demo
data by hand. Both are now FIXED in services/kofc_form_1295.py, so the
schedules are correct for any council's books, not only for data shaped
to avoid them.

The conservative choices this loader makes -- no fixed assets, every
expense paid in the period it is incurred, no investment purchases
during the period -- are therefore no longer load-bearing. They are kept
because this dataset has been reconciled line by line in that shape and
it is what gets demonstrated. Restoring depreciation, an unpaid accrual,
or a mid-period CD purchase is now safe and the schedules still foot;
see the notes at each site.

  1. schedule_c() ADDS accumulated depreciation to total assets instead
     of subtracting it. It sweeps every active Asset-type account it does
     not name into "other assets", and account 1590's account_type is
     'Asset' (subtype Contra-Asset, normal balance Credit), so
     _balance_as_of() hands back a positive number. Total Assets and
     Total Net Assets come out overstated by twice the balance in 1590.
     This is the same defect already found and fixed once in
     services/reports.py::balance_sheet_detailed(); schedule_c() was
     written later and reintroduced it.

     FIXED: schedule_c() now negates any account whose subtype contains
     "contra" before adding it, the same convention
     services/reports.py::balance_sheet_detailed() already used.

  2. schedule_b()'s Treasurer disbursement lines are ACCRUAL, not cash.
     per_capita_supreme_council, per_capita_state_council,
     charitable_donations and general_council_expenses are all computed
     from expense-account DEBITS in the period. So:
       - an expense accrued but not paid before period end is reported as
         a disbursement though no cash moved (per capita payable, an
         unpaid utility bill);
       - a non-cash expense is reported as a disbursement (depreciation);
       - cash that leaves checking for something that is not an expense
         account appears in no line at all (buying a CD or mutual fund).
     Receipts minus disbursements then does not equal the change in the
     checking balance, which is the one thing a trustee can check by
     hand. The module docstring says these schedules are cash-basis; for
     these four lines they are not.

     FIXED: the disbursement lines are now derived from credits to 1010 --
     cash that actually left checking -- categorized by the other side of
     each entry, with a new "transfers to investments" line so cash spent
     on a CD or mutual fund has somewhere to land. The section now foots
     by construction. schedule_b() additionally returns total_receipts,
     total_disbursements, reconciles and unreconciled_difference, and both
     the page and the PDF print a prominent DOES NOT RECONCILE warning if
     opening + receipts - disbursements ever fails to equal the closing
     balance. A schedule that does not foot now says so on the document a
     trustee signs, instead of waiting to be found with a calculator.

The totals below are NOT hardcoded expectations -- this loader finishes
by computing schedule_a/b/c through the exact same code the page uses and
PRINTING those results, so what you see in the terminal is precisely what
/audit/form-1295 will show.

    python load_kofc_form1295_demo_data.py
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text

from app import app, db
from audit_schema import AUDITED_TABLES, install_audit_triggers
from demo_guard import demo_reset_allowed, demo_reset_refusal_message
from models import (
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    Organization, User, Member, Project, MembershipEvent, MemberDuesPayment,
    Vendor,
    MEMBERSHIP_EVENT_ADDITION_TYPES, MEMBERSHIP_EVENT_DEDUCTION_TYPES,
)
from services.ap_service import create_invoice, record_payment
from services.kofc_form_1295 import (
    get_audit_period, save_submission_explanations,
    schedule_a, schedule_b, schedule_c,
)

# Council annual dues. Deliberately a real council figure -- Supreme sets
# per capita, councils set their own dues, and $40-$60/year is typical.
ANNUAL_DUES = Decimal('48.00')
INITIATION_FEE = Decimal('30.00')

# ---------------------------------------------------------------------------
# BRANDING -- load-bearing, not decoration.
#
# The whole application's Knights of Columbus identity hangs off two columns
# on the organization row, and this loader is now the only thing that puts
# them there. Since the demo is rebuilt from an empty schema every run (see
# demo_kofc.ps1), nothing survives to be "preserved" -- migrate_production.py
# recreates a bare organization named after config's DEFAULT_ORGANIZATION with
# a NULL css_file, which renders as an unbranded generic chapter.
#
#   org.name      -> the header lockup text (templates/base.html: brand-name)
#   org.css_file  -> BOTH the stylesheet (static/css/kofc.css) AND, via
#                    app.py::inject_branding stripping the extension to make
#                    org_code, the header emblem at static/images/kofc.svg,
#                    which falls back through .png (the K of C emblem shipped
#                    in this repo).
#
# Change these and the product stops looking like it was built for the
# Knights. They are set unconditionally below for exactly that reason.
# ---------------------------------------------------------------------------
ORG_NAME = 'Regalia - A CARES edition for the Knights of Columbus'
ORG_CSS_FILE = 'kofc.css'
COUNCIL_NUMBER = '14203'
DISTRICT_DEPUTY = 'Robert T. Whalen'

# Per-member per capita rates used for the accrual/payment cycle below.
PER_CAPITA_SUPREME = Decimal('3.50')
PER_CAPITA_STATE = Decimal('5.00')

_acct_cache = {}


# ==================== LOW-LEVEL HELPERS ====================

def _load_accounts():
    _acct_cache.clear()
    for a in ChartOfAccounts.query.all():
        _acct_cache[a.account_number] = a


def acct(number):
    a = _acct_cache.get(number)
    if not a:
        raise ValueError(
            f"Account {number} not found in the chart of accounts. "
            f"Run init_db.py (or migrate_production.py on an existing "
            f"database) so the Form 1295 accounts exist before loading demo data."
        )
    return a


def je(project, entry_date, description, reference, lines, user_id):
    """Create one posted journal entry.

    lines = list of (account_number, debit, credit, memo). Written the
    same way as load_comprehensive_data.py's helper so the two loaders
    read alike; used directly (rather than post_simple_entry) because the
    opening-balance entry needs nine lines, not two.
    """
    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project.id,
        reference_number=reference,
        created_by=user_id,
        status='Posted',
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
        db.session.add(JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=acct(account_number).id,
            debit_amount=d,
            credit_amount=c,
            memo=memo,
        ))

    if abs(total_debits - total_credits) >= Decimal('0.01'):
        raise ValueError(
            f"Unbalanced entry '{reference}': debits={total_debits} credits={total_credits}"
        )
    return entry


# ==================== WIPE ====================

def clear_existing_data():
    """Wipe all transactional data for a clean council demo load.

    Preserves: organizations, chart_of_accounts, translation_cache, and
    the admin user. Same FK-safe ordering as
    load_comprehensive_data.py::clear_existing_data -- membership_events
    and form_1295_submissions must go before members/users or their
    foreign keys block those deletes.
    """
    print("  Clearing existing data for a fresh council demo load...")
    # FK-safe order: children before parents. invoice_payments and
    # receivable_payments must precede invoices/receivables, and
    # project_assignments must precede projects, or those deletes fail on
    # a foreign key. (The list this was copied from predates the AP demo
    # data and omitted them, which only stayed harmless while nothing
    # created an invoice_payments row.)
    tables = [
        'journal_entry_lines',
        'donations',
        'membership_events',
        'form_1295_submissions',
        'member_dues_payments',
        'invoice_payments',
        'receivable_payments',
        'invoices',
        'receivables',
        'journal_entries',
        'vendors',
        'donors',
        'members',
        'project_assignments',
        'projects',
    ]
    for table in tables:
        try:
            db.session.execute(text(f'DELETE FROM {table}'))
        except Exception as e:
            print(f"  ! Could not clear {table}: {e}")
            db.session.rollback()

    try:
        db.session.execute(text("DELETE FROM users WHERE username != 'admin'"))
    except Exception as e:
        print(f"  ! Could not clear non-admin users: {e}")
        db.session.rollback()

    db.session.commit()
    print("  Cleared (organizations, chart_of_accounts, translation_cache, admin preserved)")


# ==================== AUDIT TRAIL ====================

_LOCK_TIMEOUT = '10s'


def _tables_missing_triggers(connection):
    """Which audited tables do NOT currently have their audit trigger."""
    rows = connection.execute(text("""
        SELECT c.relname
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE NOT t.tgisinternal
          AND t.tgname = 'trg_audit_' || c.relname
    """)).fetchall()
    installed = {r[0] for r in rows}
    return [t for t in AUDITED_TABLES if t not in installed]


def ensure_audit_triggers():
    """Make sure every audited table has its trigger attached.

    init_db.py installs these, but migrate_production.py does not -- so a
    database brought up through migrate_and_start.bat/.sh has no audit
    trail at all, and the Trustee Audit Report would be empty no matter
    how much demo data got loaded.

    Checks before installing, rather than relying on
    install_audit_triggers() being idempotent. It IS idempotent, but it
    gets there by running DROP TRIGGER IF EXISTS on every audited table,
    and DROP TRIGGER takes an ACCESS EXCLUSIVE lock. Any other connection
    holding even a plain read lock on one of those tables -- a running
    app, a psql session, or a caller that queried and has not committed --
    blocks that DROP indefinitely. Postgres does not time out or raise;
    it simply waits, which reads as the loader hanging with no exception.
    So: when the triggers are already in place (the normal case), take no
    lock at all.

    When they genuinely are missing, lock_timeout turns a wait into an
    error with something useful to say instead of a silent hang.
    """
    # End our own session's transaction first. A read earlier in this
    # process holds locks too, and we would otherwise be waiting on
    # ourselves from a second connection.
    db.session.commit()

    try:
        with db.engine.begin() as connection:
            connection.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
            missing = _tables_missing_triggers(connection)
            if not missing:
                print(f"  Audit triggers already present on all "
                      f"{len(AUDITED_TABLES)} audited tables -- nothing to do.")
                return True
            print(f"  Installing audit triggers ({len(missing)} table(s) missing: "
                  f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''})")
            install_audit_triggers(connection)
        print("  Audit triggers installed.")
        return True
    except Exception as e:
        print(f"  ! Could not install audit triggers: {e}")
        if 'lock' in str(e).lower():
            print(f"    Timed out after {_LOCK_TIMEOUT} waiting for a table lock.")
            print("    Something else is holding a lock on an audited table --")
            print("    usually the app still running, or an open psql session.")
            print("    Stop the app and re-run. To see what is holding it:")
            print("      SELECT pid, state, left(query,60) FROM pg_stat_activity")
            print("       WHERE datname = current_database();")
        else:
            print("    The demo will still load, but /audit/log may be empty.")
        return False


def reset_audit_log():
    """Empty the tamper-evident audit log so the demo load rebuilds it
    from genesis.

    Ordering matters, and it is deliberate: this runs AFTER
    clear_existing_data() and BEFORE a single demo row is written. The
    resulting log therefore tells exactly one story -- this council's book
    being created -- instead of opening with a wall of DELETEs against
    whatever was in the database before.

    Truncating is safe for the chain rather than a break in it. Each row's
    prev_hash is the previous row's row_hash by id, and the trigger uses
    '<genesis>' in the payload when the table is empty, so the first row
    written after this has prev_hash IS NULL -- which is exactly what
    /audit/verify expects of a first row (it compares prev_hash against
    lag(row_hash), which is NULL at the top). The rebuilt chain verifies
    clean.

    What this does NOT do is backdate those rows into the audit period.
    Every row is stamped with the real wall-clock time of the load. Making
    them look like they were written across January-June would mean
    forging prev_hash and row_hash for the whole table -- the precise
    thing the chain exists to make detectable -- and /audit/verify would
    have to be lied to for the demo to hold up. The log honestly says this
    book was entered today; every change made in the app from here on
    carries its own true timestamp, which is what the report is for.

    Requires a role with TRUNCATE on audit_log. A deployment that has run
    grant_restricted_runtime_role() deliberately does not have it -- that
    is the whole point of that role -- so this reports and carries on
    rather than failing the load.
    """
    try:
        # TRUNCATE also takes ACCESS EXCLUSIVE. Same reasoning as
        # ensure_audit_triggers: fail with something to read rather than
        # block silently if another connection is holding audit_log.
        db.session.execute(text(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'"))
        db.session.execute(text('TRUNCATE audit_log RESTART IDENTITY'))
        db.session.commit()
        print("  Audit log truncated -- the load below rebuilds it from genesis.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"  ! Could not truncate audit_log: {e}")
        print("    Expected if this deployment has applied the restricted runtime")
        print("    role (INSERT/SELECT only). The demo still loads; the audit log")
        print("    will just also contain the history that was already there.")
        return False


def audit_log_row_count():
    try:
        return db.session.execute(text('SELECT count(*) FROM audit_log')).scalar()
    except Exception:
        return None


# ==================== ORG / ADMIN ====================

def get_org():
    org = Organization.query.first()
    if not org:
        print("ERROR: No organization found. Run init_db.py first.")
        return None
    changed = False

    # Branding first, and unconditionally. See the ORG_NAME/ORG_CSS_FILE
    # comment above: after a schema rebuild the organization row is a bare
    # generic chapter, so "only set it if it's missing" would leave the demo
    # unbranded -- which is what happened, and it made a product built
    # specifically for the Knights look like it had no Knights work in it.
    if org.name != ORG_NAME:
        print(f"  Branding: organization name -> '{ORG_NAME}'")
        org.name = ORG_NAME
        changed = True
    if org.css_file != ORG_CSS_FILE:
        print(f"  Branding: theme + header emblem -> {ORG_CSS_FILE} / images/kofc.*")
        org.css_file = ORG_CSS_FILE
        changed = True

    # Council identity -- printed on the Form 1295 PDF header/footer.
    if not org.council_number:
        org.council_number = COUNCIL_NUMBER
        changed = True
    if not org.district_deputy_name:
        org.district_deputy_name = DISTRICT_DEPUTY
        changed = True

    # dues_amount IS overwritten, unlike the identity fields above, and
    # deliberately so. It is not a preference -- it is the rate the app
    # itself uses: blueprints/member_routes.py reads org.dues_amount to
    # post the Annual Dues Roster, and refuses to run at all when it is
    # null or zero. Leaving a stale value (or none) behind would mean the
    # Settings page and the roster button disagreeing with the $1,584 of
    # dues this loader just posted to account 4110. The organization row
    # survives the wipe, but the book it describes does not, so the rate
    # has to come along with the new book.
    if org.dues_amount != ANNUAL_DUES:
        previous = org.dues_amount
        org.dues_amount = ANNUAL_DUES
        changed = True
        print(f"  Council dues rate set to ${ANNUAL_DUES} "
              f"(was {'unset' if previous is None else f'${previous}'}) "
              f"-- matches the dues posted to 4110 below.")

    if changed:
        db.session.commit()
    return org


def get_admin_user(org):
    admin = User.query.filter_by(organization_id=org.id, role='Admin').first()
    if admin:
        return admin
    admin = User(username='form1295_demo_admin', email='form1295-demo@example.com',
                 role='Admin', organization_id=org.id, active=True)
    admin.set_password('demo123')
    db.session.add(admin)
    db.session.commit()
    return admin


# ==================== MEMBERSHIP ====================

# 34 founding members -- on the roll before the audit period opens.
# (name, join_year)
FOUNDING_MEMBERS = [
    ('James Kowalski', 1998), ('Thomas Brennan', 1999), ('Patrick Sullivan', 2001),
    ("Michael O'Brien", 2002), ('Robert Callahan', 2003), ('William Fitzgerald', 2004),
    ('Joseph Donovan', 2005), ('Edward Murphy', 2006), ('Francis Gallagher', 2007),
    ('Daniel Hennessy', 2008), ('Charles Doyle', 2009), ('Anthony Riordan', 2010),
    ('Vincent Moretti', 2011), ('Stephen Walsh', 2012), ('Raymond Keane', 2012),
    ('Peter Lombardi', 2013), ('Lawrence Boyle', 2014), ('Gerald McCarthy', 2015),
    ('Dennis Flanagan', 2015), ('Albert Sanchez', 2016), ('Richard Nolan', 2017),
    ('Martin Delaney', 2017), ('Paul Mazurek', 2018), ('George Rafferty', 2019),
    ('Henry Castellano', 2019), ('Eugene Halloran', 2020), ('Leo Sokolowski', 2021),
    ('Andrew Tierney', 2021), ('Bernard Quigley', 2022), ('Alfred Dominguez', 2022),
    ('Clarence Byrne', 2023), ('Harold Prendergast', 2024), ('Victor Aguilar', 2024),
    ('Russell Kinsella', 2025),
]


def create_founding_roster(org, period_start):
    """The start-of-period roll: every member joined before the period
    opens, each with one Initiation event at their join date so the
    Schedule A roll-forward has a real source of truth to count from."""
    members = []
    for i, (name, join_year) in enumerate(FOUNDING_MEMBERS):
        # Spread join dates through each member's join year.
        join_date = date(join_year, (i % 12) + 1, (i % 27) + 1)
        surname = name.split()[-1].lower().replace("'", "")
        member = Member(
            name=name,
            email=f"{surname}@example.com",
            phone=f"555-0{200 + i}",
            address=f"{100 + (i * 7)} Fraternal Ave",
            city='Springfield', state='IL', zip_code='62701',
            join_date=join_date, active=True, organization_id=org.id,
        )
        db.session.add(member)
        db.session.flush()
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id,
            event_type='Initiation', event_date=join_date,
            notes='Council demo data -- founding roster.',
        ))
        members.append(member)
    db.session.commit()
    return members


def create_period_additions(org, period_start):
    """One brand-new member per addition type, each with exactly one
    addition event dated inside the period, so the roll-forward and the
    live Active count agree."""
    assert set(MEMBERSHIP_EVENT_ADDITION_TYPES) == {
        'Initiation', 'Transfer In (from another council)',
        'Re-entry', 'Transfer from Insurance to Associate',
    }, "MEMBERSHIP_EVENT_ADDITION_TYPES changed -- update this demo data to match."

    additions = [
        ('Initiation', 'Christopher Vance', period_start + timedelta(days=24)),
        ('Transfer In (from another council)', 'Nicholas Barlow', period_start + timedelta(days=52)),
        ('Re-entry', 'Gregory Castillo', period_start + timedelta(days=96)),
        ('Transfer from Insurance to Associate', 'Samuel Delgado', period_start + timedelta(days=137)),
    ]
    members = []
    for i, (event_type, name, event_date) in enumerate(additions):
        surname = name.split()[-1].lower()
        member = Member(
            name=name, email=f"{surname}@example.com",
            phone=f"555-03{i:02d}", address=f"{400 + (i * 9)} Fraternal Ave",
            city='Springfield', state='IL', zip_code='62701',
            join_date=event_date, active=True, organization_id=org.id,
        )
        db.session.add(member)
        db.session.flush()
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type=event_type,
            event_date=event_date, notes='Council demo data -- addition during audit period.',
        ))
        members.append(member)
    db.session.commit()
    return members


def create_period_deductions(org, period_start, exclude_ids):
    """Five members from the founding roster (never one of the four just
    added), one deduction type each, deactivated with an event dated
    inside the period."""
    assert set(MEMBERSHIP_EVENT_DEDUCTION_TYPES) == {
        'Suspension', 'Death', 'Withdrawal',
        'Transfer Out (to another council)', 'Transfer from Associate to Insurance',
    }, "MEMBERSHIP_EVENT_DEDUCTION_TYPES changed -- update this demo data to match."

    candidates = Member.query.filter(
        Member.organization_id == org.id,
        Member.active == True,  # noqa: E712
        ~Member.id.in_(exclude_ids),
    ).order_by(Member.id.desc()).limit(5).all()
    if len(candidates) < 5:
        raise RuntimeError(
            f"Need at least 5 existing active members for deductions, found {len(candidates)}."
        )

    deductions = [
        ('Suspension', period_start + timedelta(days=38),
         'Dues unpaid after two notices -- suspended under Section 130.'),
        ('Death', period_start + timedelta(days=63),
         'Requiescat in pace. Council Mass offered.'),
        ('Withdrawal', period_start + timedelta(days=88),
         'Withdrew by written request.'),
        ('Transfer Out (to another council)', period_start + timedelta(days=119),
         'Relocated; transferred to a council in his new parish.'),
        ('Transfer from Associate to Insurance', period_start + timedelta(days=151),
         'Reclassified to insurance membership.'),
    ]
    for (event_type, event_date, note), member in zip(deductions, candidates):
        member.active = False
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type=event_type,
            event_date=event_date, notes=note,
        ))
    db.session.commit()
    return candidates


# Five members carried on the roll who never paid 2026 dues. Indices into
# the full member list (founding roster + period additions), chosen so
# the unpaid members are scattered rather than clustered at one end.
UNPAID_DUES_INDICES = {3, 11, 19, 27, 35}


# When each paid member's dues came in, and by what route.
#   'checking' -- handed to the Treasurer, straight into 1010.
#   'fs'       -- collected as cash at a meeting by the Financial
#                 Secretary into 1040, deposited later (see DUES_DEPOSITS).
# 21 checking + 12 FS = 33 paying members.
DUES_COLLECTION_SCHEDULE = [
    ((1, 8),  'checking', 7),
    ((1, 22), 'fs',       5),
    ((2, 5),  'checking', 6),
    ((2, 19), 'fs',       4),
    ((3, 12), 'checking', 4),
    ((4, 9),  'checking', 3),
    ((4, 16), 'fs',       2),
    ((5, 14), 'checking', 1),
    ((6, 26), 'fs',       1),   # deliberately never deposited -- see below
]

# The Financial Secretary turning collected cash over to the Treasurer.
# The June 26 collection is deliberately absent: that $48 is still in his
# possession at period end, which is what makes Schedule B's closing
# "funds in possession" a real number instead of zero.
DUES_DEPOSITS = [
    ((1, 24), 5),
    ((2, 21), 4),
    ((4, 18), 2),
]


def post_member_dues(org, projects, admin_id, dues_year):
    """Post dues exactly the way the application itself posts them.

    blueprints/member_routes.py's Annual Dues Roster creates ONE journal
    entry per paid member in a project named 'Dues', described
    '<name> <year> Dues Payment', referenced
    'DUES-<year>-<member_id>-<MMDD>', debiting 1010 and crediting 4110 at
    org.dues_amount -- then writes that entry's id back onto the member's
    MemberDuesPayment row so the same dues can never be posted twice.

    This mirrors that, rather than posting batch totals against a generic
    project. The demo's dues therefore look like dues the council actually
    entered through the app: every paid member on the roster page links to
    his own transaction, and the Dues project's ledger IS the list of who
    paid. It also removes a shortcut in the earlier version of this
    loader, where the dues records and the dues revenue were two parallel
    facts that agreed only because I made the arithmetic match.

    The one thing the roster button cannot express is cash. It always
    debits checking, but a Financial Secretary really does collect some
    dues in cash at a meeting and turn them over days later -- which is
    the only reason Schedule B has a "funds in possession" line at all. So
    a subset of these entries debit 1040 instead, with separate deposit
    entries moving that cash to 1010 afterwards.
    """
    dues_project = projects['Dues']
    members = Member.query.filter_by(organization_id=org.id).order_by(Member.id).all()

    paid_members = [m for i, m in enumerate(members) if i not in UNPAID_DUES_INDICES]
    unpaid_members = [m for i, m in enumerate(members) if i in UNPAID_DUES_INDICES]

    # Expand the schedule into one (date, route) slot per paying member.
    slots = []
    for (month, day), route, count in DUES_COLLECTION_SCHEDULE:
        slots.extend([(date(dues_year, month, day), route)] * count)
    if len(slots) != len(paid_members):
        raise RuntimeError(
            f"DUES_COLLECTION_SCHEDULE covers {len(slots)} members but "
            f"{len(paid_members)} are marked paid. Update one to match the other."
        )

    fs_collected = Decimal('0')
    for member, (paid_on, route) in zip(paid_members, slots):
        description = f'{member.name} {dues_year} Dues Payment'
        debit_account = '1040' if route == 'fs' else '1010'
        entry = je(
            dues_project, paid_on, description,
            f'DUES-{dues_year}-{member.id}-{paid_on:%m%d}',
            [(debit_account, ANNUAL_DUES, 0, description),
             ('4110', 0, ANNUAL_DUES, description)],
            admin_id,
        )
        db.session.flush()
        if route == 'fs':
            fs_collected += ANNUAL_DUES
        db.session.add(MemberDuesPayment(
            member_id=member.id, organization_id=org.id, year=dues_year,
            paid_date=paid_on,
            # True, matching what the roster button sets. Paired with
            # journal_entry_id below, this is what marks the record as
            # already posted, so clicking the button will not double-post.
            include_in_transaction=True,
            journal_entry_id=entry.id,
        ))

    # Members carried on the roll who never paid. The record exists (so
    # they show on the roster as outstanding) with no payment behind it.
    for member in unpaid_members:
        db.session.add(MemberDuesPayment(
            member_id=member.id, organization_id=org.id, year=dues_year,
            paid_date=None, include_in_transaction=True, journal_entry_id=None,
        ))

    # Financial Secretary turning collected cash over to the Treasurer.
    deposited = Decimal('0')
    for (month, day), count in DUES_DEPOSITS:
        amount = ANNUAL_DUES * count
        deposited += amount
        when = date(dues_year, month, day)
        je(dues_project, when,
           f'Financial Secretary deposits collected dues ({count} members)',
           f'DUES-DEP-{dues_year}-{when:%m%d}',
           [('1010', amount, 0, 'Deposited to operating checking'),
            ('1040', 0, amount, 'Turned over to Treasurer')],
           admin_id)

    db.session.commit()
    return {
        'records': len(members),
        'paid': len(paid_members),
        'entries': len(paid_members) + len(DUES_DEPOSITS),
        'revenue': ANNUAL_DUES * len(paid_members),
        'in_hand': fs_collected - deposited,
    }


# ==================== PROJECTS ====================

def create_projects(org, period_start):
    """Six projects at council scale -- three ordinary council activities
    and three fundraisers of deliberately different sizes."""
    defs = [
        # Name and description match blueprints/member_routes.py exactly --
        # the Annual Dues Roster looks this project up by the literal name
        # 'Dues' and creates it with this description if it is missing. If
        # the demo used any other name, the app would silently create a
        # SECOND dues project the first time someone used that button.
        ('Dues',
         'Member dues and subscription payments',
         1824, 'Active', False),
        ('Council Operations',
         'Hall rent, utilities, insurance, supplies, and general council administration.',
         12000, 'Active', False),
        ('Charitable Giving',
         'Donations to the parish, seminarian support, Special Olympics, and local charities.',
         4000, 'Active', False),
        ('Youth & Family Programs',
         'Free Throw Championship, family picnic, and youth activities.',
         2500, 'Active', False),
        ('Spring Raffle 2026',
         'Council-wide ticket raffle -- the largest fundraiser this period.',
         3000, 'Completed', True),
        ('Pancake Breakfast 2026',
         'Three parish-hall breakfast seatings -- second-largest fundraiser this period.',
         2000, 'Completed', True),
        ('Golf Outing 2026',
         'Deliberately the THIRD, smallest fundraiser: proves proceeds beyond the top '
         'two correctly fall into miscellaneous income rather than vanishing.',
         1500, 'Completed', True),
    ]
    projects = {}
    for name, desc, budget, status, is_fundraiser in defs:
        p = Project(
            name=name, description=desc, start_date=period_start,
            status=status, budget=Decimal(str(budget)),
            is_fundraiser=is_fundraiser, organization_id=org.id,
        )
        db.session.add(p)
        db.session.flush()
        projects[name] = p
    db.session.commit()
    return projects


# ==================== SIX MONTHS OF TRANSACTIONS ====================

def load_opening_balances(projects, user_id):
    """Council-scale opening position at 12/31/2025.

    Debits  38,350.00 = 14,250 checking + 8,400 savings + 6,200 money
                        market + 6,000 CDs + 3,500 mutual funds
    Credits 38,350.00 = 310 accounts payable + 38,040 net assets

    NO FIXED ASSETS, DELIBERATELY. This council rents its meeting space
    and has capitalized nothing, which is true of a great many councils --
    and it keeps account 1590 (Accumulated Depreciation) at zero.

    That last part is not cosmetic. schedule_c() sweeps every active
    Asset-type account it does not name individually into "other assets",
    and 1590's account_type IS 'Asset' (subtype Contra-Asset, normal
    balance Credit). _balance_as_of() returns a balance signed by the
    account's own normal balance, so a non-zero 1590 comes back POSITIVE
    and gets ADDED to total assets instead of subtracted -- overstating
    Total Assets and Total Net Assets by twice its balance. Holding 1590
    at zero means that code path cannot produce a wrong number here.

    The bug is still in schedule_c() and still needs fixing for any real
    council that owns anything. See the note in the module docstring.
    """
    ops = projects['Council Operations']
    je(ops, date(2025, 12, 31),
       'Opening balances - carried forward from prior fraternal year',
       'OB-KC-2026',
       [('1010', 14250, 0, 'Operating checking account'),
        ('1020', 8400, 0, 'Savings account'),
        ('1330', 6200, 0, 'Money market account'),
        ('1340', 6000, 0, 'Certificates of deposit'),
        ('1350', 3500, 0, 'Mutual fund investments'),
        ('2110', 0, 310, 'December invoices unpaid at year end'),
        ('3100', 0, 38040, 'Net assets without donor restrictions')],
       user_id)


def load_period_transactions(projects, user_id):
    """Six months of council activity, January 1 - June 30, 2026.

    Written as flat tables of (date, description, lines) rather than
    generated in a loop, so that every figure on Form 1295 can be traced
    back to a specific, readable posting.
    """
    dues = projects['Dues']
    ops = projects['Council Operations']
    charity = projects['Charitable Giving']
    youth = projects['Youth & Family Programs']
    raffle = projects['Spring Raffle 2026']
    pancake = projects['Pancake Breakfast 2026']
    golf = projects['Golf Outing 2026']

    n = [0]  # entry counter, for reference numbers

    def post(project, entry_date, description, lines, prefix='JE'):
        n[0] += 1
        return je(project, entry_date, description,
                  f'{prefix}-2026-{n[0]:04d}', lines, user_id)

    # ---- Dues -----------------------------------------------------------
    # Not here. Dues are posted one entry per member into the 'Dues'
    # project by post_member_dues(), which runs before this function --
    # see that docstring for why the demo mirrors the application's own
    # Annual Dues Roster instead of writing batch totals.

    # ---- Initiation fees for the four members added this period -------
    # Also the Dues project: these are Financial Secretary membership
    # receipts, and Form 1295 reports them on the same combined
    # "dues and initiations" line as dues themselves.
    for day, name in ((25, 'Christopher Vance'), (53, 'Nicholas Barlow'),
                      (97, 'Gregory Castillo'), (138, 'Samuel Delgado')):
        post(dues, date(2026, 1, 1) + timedelta(days=day), f'Initiation fee - {name}',
             [('1010', INITIATION_FEE, 0, 'Initiation fee received'),
              ('4115', 0, INITIATION_FEE, f'Initiation fee - {name}')])

    # ---- Spring Raffle 2026: $3,200 revenue, $585 costs ----------------
    post(raffle, date(2026, 2, 2), 'Raffle ticket printing',
         [('5530', 185, 0, 'Ticket books and posters'),
          ('1010', 0, 185, 'Paid by council check')])
    post(raffle, date(2026, 2, 14), 'Raffle ticket sales - first turn-in',
         [('1010', 850, 0, 'Ticket sales deposited'),
          ('4210', 0, 850, 'Spring Raffle ticket sales')])
    post(raffle, date(2026, 3, 14), 'Raffle ticket sales - after Sunday Masses',
         [('1010', 1120, 0, 'Ticket sales deposited'),
          ('4210', 0, 1120, 'Spring Raffle ticket sales')])
    post(raffle, date(2026, 4, 11), 'Raffle ticket sales - final push',
         [('1010', 890, 0, 'Ticket sales deposited'),
          ('4210', 0, 890, 'Spring Raffle ticket sales')])
    post(raffle, date(2026, 4, 18), 'Raffle ticket sales - drawing night',
         [('1010', 340, 0, 'Ticket sales deposited'),
          ('4210', 0, 340, 'Spring Raffle ticket sales')])
    post(raffle, date(2026, 4, 20), 'Raffle prize payout',
         [('5520', 400, 0, 'First, second, and third prizes'),
          ('1010', 0, 400, 'Paid by council check')])

    # ---- Pancake Breakfast 2026: $1,800 revenue, $590 costs ------------
    post(pancake, date(2026, 3, 6), 'Pancake breakfast food supplies - March seating',
         [('5320', 210, 0, 'Batter, sausage, eggs, coffee'),
          ('1010', 0, 210, 'Paid by council check')])
    post(pancake, date(2026, 3, 8), 'Pancake breakfast proceeds - March seating',
         [('1010', 640, 0, 'Door receipts deposited'),
          ('4210', 0, 640, 'Pancake Breakfast proceeds')])
    post(pancake, date(2026, 5, 8), 'Pancake breakfast food supplies - May seating',
         [('5320', 230, 0, 'Batter, sausage, eggs, coffee'),
          ('1010', 0, 230, 'Paid by council check')])
    post(pancake, date(2026, 5, 10), 'Pancake breakfast proceeds - May seating',
         [('1010', 720, 0, 'Door receipts deposited'),
          ('4210', 0, 720, 'Pancake Breakfast proceeds')])
    post(pancake, date(2026, 6, 12), 'Pancake breakfast food supplies - June seating',
         [('5320', 150, 0, 'Batter, sausage, eggs, coffee'),
          ('1010', 0, 150, 'Paid by council check')])
    post(pancake, date(2026, 6, 14), 'Pancake breakfast proceeds - June seating',
         [('1010', 440, 0, 'Door receipts deposited'),
          ('4210', 0, 440, 'Pancake Breakfast proceeds')])

    # ---- Golf Outing 2026: the third, smallest fundraiser --------------
    # $600 -- correctly lands in miscellaneous income, not a named line.
    post(golf, date(2026, 6, 20), 'Golf outing net proceeds',
         [('1010', 600, 0, 'Net proceeds deposited'),
          ('4220', 0, 600, 'Golf Outing net proceeds')])

    # ---- Other council revenue (also miscellaneous income) ------------
    post(youth, date(2026, 2, 7), 'Free Throw Championship entry fees',
         [('1010', 120, 0, 'Entry fees collected'),
          ('4120', 0, 120, 'Youth program fees')])
    post(youth, date(2026, 5, 30), 'Family picnic ticket sales',
         [('1010', 260, 0, 'Ticket sales deposited'),
          ('4210', 0, 260, 'Family picnic tickets')])
    post(charity, date(2026, 3, 15), 'Member contributions to council charity fund',
         [('1010', 150, 0, 'Contributions received'),
          ('4010', 0, 150, 'Individual contributions')])
    post(charity, date(2026, 6, 5), 'Member contributions to council charity fund',
         [('1010', 200, 0, 'Contributions received'),
          ('4010', 0, 200, 'Individual contributions')])

    # ---- Interest: checking (Schedule B) vs. everything else -----------
    checking_interest = [
        (date(2026, 1, 31), '2.10'), (date(2026, 2, 28), '1.95'),
        (date(2026, 3, 31), '2.30'), (date(2026, 4, 30), '2.15'),
        (date(2026, 5, 31), '2.40'), (date(2026, 6, 30), '2.60'),
    ]
    for when, amount in checking_interest:
        post(ops, when, 'Checking account interest',
             [('1010', amount, 0, 'Interest credited'),
              ('4415', 0, amount, 'Interest income - checking account')])
    post(ops, date(2026, 3, 31), 'Savings account interest',
         [('1020', '10.50', 0, 'Interest credited'),
          ('4410', 0, '10.50', 'Investment income - interest')])
    post(ops, date(2026, 6, 30), 'Savings account interest',
         [('1020', '11.20', 0, 'Interest credited'),
          ('4410', 0, '11.20', 'Investment income - interest')])
    post(ops, date(2026, 6, 30), 'Money market interest',
         [('1330', '18.75', 0, 'Interest credited'),
          ('4410', 0, '18.75', 'Investment income - interest')])

    # ---- Per capita: accrued in January, paid in February, accrued
    #      again unpaid at June 30 --------------------------------------
    jan_supreme = PER_CAPITA_SUPREME * 34
    jan_state = PER_CAPITA_STATE * 34
    post(ops, date(2026, 1, 15), 'Per capita assessment received from Supreme Council',
         [('5850', jan_supreme, 0, '34 members x $3.50 semi-annual per capita'),
          ('2130', 0, jan_supreme, 'Per capita payable - Supreme Council')])
    post(ops, date(2026, 1, 15), 'Per capita assessment received from State Council',
         [('5860', jan_state, 0, '34 members x $5.00 semi-annual per capita'),
          ('2140', 0, jan_state, 'Per capita payable - State Council')])
    post(ops, date(2026, 2, 10), 'Per capita paid to Supreme Council',
         [('2130', jan_supreme, 0, 'Payable cleared'),
          ('1010', 0, jan_supreme, 'Council check to Supreme Council')])
    post(ops, date(2026, 2, 10), 'Per capita paid to State Council',
         [('2140', jan_state, 0, 'Payable cleared'),
          ('1010', 0, jan_state, 'Council check to State Council')])

    # No second accrual at June 30, deliberately. An expense accrued
    # inside the period but NOT paid inside the period is exactly what
    # breaks Schedule B's Treasurer section: its per-capita and general
    # expense lines are computed from expense-account DEBITS, so an
    # unpaid accrual is reported as a disbursement while no cash actually
    # left checking -- and receipts minus disbursements then no longer
    # equals the closing balance. Every expense in this period is paid in
    # this period, so the Treasurer section foots exactly.

    # ---- Charitable donations given -----------------------------------
    donations = [
        (date(2026, 1, 25), 'St. Vincent de Paul food pantry', 250),
        (date(2026, 2, 22), 'Seminarian support (RSVP program)', 400),
        (date(2026, 3, 20), 'Special Olympics Illinois', 300),
        (date(2026, 4, 24), 'Global Wheelchair Mission', 250),
        (date(2026, 5, 22), 'Parish high school scholarship fund', 500),
        (date(2026, 6, 18), 'Local pregnancy resource center', 250),
    ]
    for when, recipient, amount in donations:
        post(charity, when, f'Charitable donation - {recipient}',
             [('5870', amount, 0, f'Donation to {recipient}'),
              ('1010', 0, amount, 'Paid by council check')])

    # ---- Monthly council operating costs ------------------------------
    for month in range(1, 7):
        post(ops, date(2026, month, 5), 'Parish hall rent - monthly',
             [('5210', 175, 0, 'Meeting room and hall use'),
              ('1010', 0, 175, 'Paid by council check')])

    # Every month's bill is paid in the month it arrives. No June accrual
    # left outstanding -- see the per-capita note above for why an unpaid
    # accrual inside the period breaks the Treasurer section's footing.
    utilities = [(1, 145), (2, 158), (3, 132), (4, 118), (5, 126), (6, 149)]
    for month, amount in utilities:
        post(ops, date(2026, month, 18), 'Utilities - electric, gas, water',
             [('5220', amount, 0, 'Council home utilities'),
              ('1010', 0, amount, 'Paid by council check')])

    for month in range(1, 7):
        post(ops, date(2026, month, 28), 'Bank service charge',
         [('5820', 6, 0, 'Monthly account fee'),
          ('1010', 0, 6, 'Debited from operating checking')])

    # No depreciation entries: this council has no capitalized fixed
    # assets (see load_opening_balances). Depreciation is also the other
    # non-cash expense that would put the Treasurer section out by the
    # amount expensed.

    other_costs = [
        (date(2026, 1, 20), 'General liability insurance - semi-annual premium', '5610', 420),
        (date(2026, 1, 30), 'Postage - dues notices and Columbia mailing', '5330', 58),
        (date(2026, 2, 12), 'Office supplies', '5310', 68),
        (date(2026, 2, 28), 'State council assessment and subscriptions', '5830', 95),
        (date(2026, 3, 7), 'Officer formation and training session', '5840', 180),
        (date(2026, 3, 26), 'Council newsletter printing', '5530', 145),
        (date(2026, 4, 8), 'Council home repairs - kitchen plumbing', '5240', 215),
        (date(2026, 4, 20), 'General liability insurance - semi-annual premium', '5610', 420),
        (date(2026, 4, 30), 'Postage - spring mailing', '5330', 62),
        (date(2026, 5, 14), 'Office supplies', '5310', 92),
        (date(2026, 5, 16), 'State convention - delegate travel and lodging', '5840', 650),
        (date(2026, 6, 26), 'Council newsletter printing', '5530', 138),
    ]
    for when, description, account, amount in other_costs:
        post(ops, when, description,
             [(account, amount, 0, description),
              ('1010', 0, amount, 'Paid by council check')])

    # ---- Transfers between checking and savings, both directions ------
    post(ops, date(2026, 2, 26), 'Transfer to savings - raffle proceeds set aside',
         [('1020', 500, 0, 'Deposited to savings'),
          ('1010', 0, 500, 'Transferred from operating checking')])
    post(ops, date(2026, 5, 20), 'Transfer from savings - convention and insurance costs',
         [('1010', 300, 0, 'Deposited to operating checking'),
          ('1020', 0, 300, 'Transferred from savings')])

    # ---- No investment purchases this period, deliberately ------------
    # Cash moving from checking into a CD or mutual fund is a real
    # disbursement, but 1340/1350 are ASSET accounts, so Schedule B's
    # Treasurer section -- which builds its disbursement lines from
    # EXPENSE-account debits -- has no line that can hold it. The cash
    # leaves the checking balance while appearing nowhere in the activity
    # above it. The council's CDs are carried in the opening balance
    # instead, so Schedule C still shows real long-term assets.

    db.session.commit()
    return n[0]


# ==================== WIZARD STATE ====================

# ==================== ACCOUNTS PAYABLE ====================

# (key, name, contact, is_1099, terms, city, state)
#
# is_1099 marks a payee the council would issue a Form 1099-NEC to --
# individuals, sole proprietors and partnerships paid for services.
# Incorporated vendors are generally exempt, which is why the corporations
# below are flagged False. That split is the whole point of the 1099
# report: it has to be a property of the vendor, not a guess from the name.
AP_VENDORS = [
    ('cpa',      'Sullivan & Reeve, Bookkeeping',   'Eileen Reeve',      True,  'Net30', 'Springfield', 'IL'),
    ('cleaning', 'Ortega Cleaning Services',        'Marisol Ortega',    True,  'Net15', 'Springfield', 'IL'),
    ('grounds',  'Greenfield Grounds Care',         'Daniel Greenfield', True,  'Net30', 'Chatham',     'IL'),
    ('organist', 'Thomas Beckett, Organist',        'Thomas Beckett',    True,  'Net15', 'Springfield', 'IL'),
    ('audio',    'Halloran Audio & Sound',          'Kevin Halloran',    True,  'Net30', 'Springfield', 'IL'),
    ('plumbing', 'Midland Plumbing & HVAC, Inc.',   'Service Desk',      False, 'Net30', 'Springfield', 'IL'),
    ('print',    'Basilica Print Shop, LLC',        'Anne Mulcahy',      False, 'Net30', 'Springfield', 'IL'),
    ('food',     'Riverside Food Supply Co.',       'Orders Department', False, 'Net30', 'Riverton',    'IL'),
    ('office',   'Statewide Office Products, Inc.', 'Customer Service',  False, 'Net30', 'Springfield', 'IL'),
]

# Invoices with fixed dates, all settled. (vendor, invoice_date, GL account,
# amount, days_to_payment, project, description)
AP_PAID_INVOICES = [
    ('cleaning', date(2026, 3, 2),  '5420', '185.00', 12, 'ops',   'Hall cleaning - March'),
    ('organist', date(2026, 3, 3),  '5420', '150.00', 10, 'ops',   'Organist stipend - March'),
    ('cpa',      date(2026, 3, 20), '5130', '450.00', 24, 'ops',   'Quarterly bookkeeping review'),
    ('cleaning', date(2026, 4, 1),  '5420', '185.00', 13, 'ops',   'Hall cleaning - April'),
    ('organist', date(2026, 4, 2),  '5420', '150.00', 11, 'ops',   'Organist stipend - April'),
    ('grounds',  date(2026, 4, 14), '5420', '180.00', 21, 'ops',   'Spring grounds cleanup'),
    ('plumbing', date(2026, 4, 22), '5240', '395.00', 26, 'ops',   'Kitchen water heater service'),
    ('cleaning', date(2026, 5, 1),  '5420', '185.00', 12, 'ops',   'Hall cleaning - May'),
    ('organist', date(2026, 5, 4),  '5420', '150.00', 10, 'ops',   'Organist stipend - May'),
    ('grounds',  date(2026, 5, 12), '5420', '180.00', 19, 'ops',   'Grounds maintenance - May'),
    ('food',     date(2026, 5, 20), '5320', '210.00', 22, 'youth', 'Free Throw Championship refreshments'),
    ('cleaning', date(2026, 6, 1),  '5420', '185.00', 14, 'ops',   'Hall cleaning - June'),
    ('organist', date(2026, 6, 2),  '5420', '150.00', 12, 'ops',   'Organist stipend - June'),
    ('grounds',  date(2026, 6, 9),  '5420', '180.00', 20, 'ops',   'Grounds maintenance - June'),
    ('print',    date(2026, 6, 22), '5530', '215.00', 25, 'ops',   'Council directory reprint'),
    ('cleaning', date(2026, 7, 1),  '5420', '185.00', 13, 'ops',   'Hall cleaning - July'),
    ('organist', date(2026, 7, 6),  '5420', '150.00', 11, 'ops',   'Organist stipend - July'),
    ('cpa',      date(2026, 7, 15), '5130', '450.00', 23, 'ops',   'Quarterly bookkeeping review'),
    ('grounds',  date(2026, 7, 20), '5420', '180.00', 18, 'ops',   'Grounds maintenance - July'),
    ('cleaning', date(2026, 8, 3),  '5420', '185.00', 12, 'ops',   'Hall cleaning - August'),
]

# Invoices left OPEN, positioned by how many days past due they should be
# TODAY. Anchored to date.today() rather than to fixed dates on purpose:
# Invoice.days_outstanding is (date.today() - due_date).days, so hardcoded
# dates would slide into the 90+ bucket a few months from now and the aging
# report would degenerate into a single column. Anchoring means all five
# buckets populate whenever the demo is rebuilt.
#
# (vendor, GL account, amount, days_past_due, terms_days, project, description)
# A negative days_past_due is an invoice not yet due -- the "Current" bucket.
AP_OPEN_INVOICES = [
    ('office',   '5310', '128.50', -12, 30, 'ops',   'Office supplies - quarterly restock'),
    ('print',    '5530', '342.75',   9, 30, 'ops',   'Summer newsletter print run'),
    ('food',     '5320', '286.40',  41, 30, 'ops',   'Council picnic supplies'),
    ('audio',    '5710', '475.00',  74, 30, 'ops',   'Hall sound system repair'),
    ('grounds',  '5420', '180.00', 118, 30, 'ops',   'Grounds maintenance - disputed invoice'),
]


def create_vendors(org):
    vendors = {}
    for key, name, contact, is_1099, terms, city, state in AP_VENDORS:
        v = Vendor(
            organization_id=org.id, name=name, contact_name=contact,
            email=f"ap@{key}.example.com", phone=f"555-04{len(vendors):02d}",
            address=f"{100 + len(vendors) * 13} Commerce St",
            city=city, state=state, zip_code='62701',
            payment_terms=terms, is_1099=is_1099, active=True,
            notes=('Issues a Form 1099-NEC at year end.' if is_1099
                   else 'Incorporated -- no Form 1099 required.'),
        )
        db.session.add(v)
        db.session.flush()
        vendors[key] = v
    db.session.commit()
    return vendors


def create_ap_activity(org, vendors, projects, admin_id):
    """Six months of accounts payable, posted through the application's own
    AP service rather than as hand-written journal entries.

    services/ap_service.py is what the Invoices screen calls, so going
    through it means the demo's invoices carry everything the app would
    have set: the GL entry link, amount_paid, the Open/Partial/Paid status,
    and an InvoicePayment row per payment. An invoice fabricated directly
    in the ORM would look right on the list page and be wrong everywhere
    the app derives something from it.

    The GL effect is the ordinary accrual pair, and it is worth being
    explicit about how it reaches Form 1295 now that Schedule B's
    disbursement lines are cash-based:

        raising an invoice   DR expense / CR 2110   -- no cash, so it does
                             NOT appear as a Treasurer disbursement
        paying an invoice    DR 2110    / CR 1010   -- cash, so it DOES

    An invoice still open at period end therefore sits in Schedule C's
    miscellaneous liabilities and nowhere on Schedule B, which is correct
    and is what keeps the Treasurer section footing to the closing balance.
    """
    proj = {'ops': projects['Council Operations'],
            'youth': projects['Youth & Family Programs']}
    counter = {}

    def invoice_number(key, when):
        counter[key] = counter.get(key, 0) + 1
        return f"{key.upper()[:4]}-{when:%Y%m}-{counter[key]:02d}"

    created = paid = 0
    for vkey, inv_date, gl, amount, pay_after, pkey, desc in AP_PAID_INVOICES:
        vendor = vendors[vkey]
        terms_days = 15 if vendor.payment_terms == 'Net15' else 30
        inv = create_invoice(
            organization_id=org.id, vendor_id=vendor.id, project_id=proj[pkey].id,
            gl_account_number=gl, gl_account_id=acct(gl).id,
            invoice_number=invoice_number(vkey, inv_date),
            invoice_date=inv_date, due_date=inv_date + timedelta(days=terms_days),
            amount=Decimal(amount), notes=desc, created_by=admin_id,
        )
        created += 1
        record_payment(
            invoice=inv, payment_amount=Decimal(amount),
            payment_date=inv_date + timedelta(days=pay_after),
            reference_number=f"CHK-{inv_date:%Y%m}-{counter[vkey]:02d}",
            created_by=admin_id,
        )
        paid += 1

    today = date.today()
    open_total = Decimal('0')
    for vkey, gl, amount, days_past_due, terms_days, pkey, desc in AP_OPEN_INVOICES:
        vendor = vendors[vkey]
        due = today - timedelta(days=days_past_due)
        inv_date = due - timedelta(days=terms_days)
        create_invoice(
            organization_id=org.id, vendor_id=vendor.id, project_id=proj[pkey].id,
            gl_account_number=gl, gl_account_id=acct(gl).id,
            invoice_number=invoice_number(vkey, inv_date),
            invoice_date=inv_date, due_date=due,
            amount=Decimal(amount), notes=desc, created_by=admin_id,
        )
        created += 1
        open_total += Decimal(amount)

    return {'vendors': len(vendors),
            'vendors_1099': sum(1 for v in vendors.values() if v.is_1099),
            'invoices': created, 'paid': paid,
            'open': len(AP_OPEN_INVOICES), 'open_total': open_total}


def save_wizard_demo_state(org, period_start, period_end):
    """One miscellaneous line explained, one deliberately left blank, so
    the submission wizard shows both states on one page. Nothing is
    attested, so the attest button is still there to click through."""
    save_submission_explanations(
        org.id, period_start, period_end,
        misc_income_explanation=(
            "Golf Outing 2026 net proceeds ($600 -- our third fundraiser this "
            "period, beyond the two named above), Free Throw Championship entry "
            "fees ($120), family picnic ticket sales ($260), and member "
            "contributions to the council charity fund ($350)."
        ),
        misc_liabilities_explanation=misc_liabilities_explanation(org, period_end),
    )


def misc_liabilities_explanation(org, period_end):
    """Build the Schedule C miscellaneous-liabilities note from the ledger
    itself, listing the invoices that make it up.

    Written rather than hardcoded because the open AP invoices are dated
    relative to the day the demo is loaded (see AP_OPEN_INVOICES), so a
    fixed sentence would drift out of agreement with the figure beside it.
    An explanation on a compliance document that does not match the number
    it explains is worse than no explanation.
    """
    from models import Invoice
    open_invoices = Invoice.query.filter(
        Invoice.organization_id == org.id,
        Invoice.status.in_(['Open', 'Partial']),
        Invoice.invoice_date <= period_end,
    ).order_by(Invoice.invoice_date).all()

    # Day built from .day rather than %-d: that strftime flag is glibc-only
    # and raises ValueError on Windows, which is what this app runs on.
    parts = [f"{i.vendor.name} invoice {i.invoice_number} dated "
             f"{i.invoice_date:%B} {i.invoice_date.day} (${i.amount_due:,.2f})"
             for i in open_invoices]
    total = sum((i.amount_due for i in open_invoices), Decimal('0'))

    text_ = ("Accounts payable at June 30. $310.00 of invoices was carried "
             "forward unpaid from December 2025.")
    if parts:
        text_ += (f" A further ${total:,.2f} was outstanding to vendors at "
                  f"period end: " + "; ".join(parts) + ".")
    text_ += (" Per capita to Supreme and State was assessed in January and "
              "paid in February, so no council charges remain payable.")
    return text_


# ==================== REPORT BACK ====================

def print_expected_results(org, period_start, period_end):
    """Compute the schedules through the exact same code the page uses and
    print them -- what appears below is precisely what /audit/form-1295
    will show for the default period."""
    a = schedule_a(org.id, period_start, period_end)
    b = schedule_b(org.id, period_start, period_end)
    c = schedule_c(org.id, period_end)

    print("\n" + "=" * 62)
    print("WHAT /audit/form-1295 WILL SHOW (computed via the same code)")
    print("=" * 62)
    print("\nSchedule A -- Membership roll-forward")
    print(f"  Start of period:        {a['members_start_of_period']}")
    for event_type, count in a['additions'].items():
        print(f"    + {event_type}: {count}")
    print(f"  Total for period:       {a['total_for_period']}")
    for event_type, count in a['deductions'].items():
        print(f"    - {event_type}: {count}")
    print(f"  End of period:          {a['members_end_of_period']}")
    print(f"  Live active members:    {a['active_members_actual']}")
    print(f"  Reconciled:             {a['reconciled']}")
    print(f"  Dues records/paid ({a['dues_year']}): {a['dues_records_for_year']} / {a['dues_paid_for_year']}")
    print(f"  Dues collected:         ${a['dues_collected_in_period']:,.2f}")

    fs, tr = b['financial_secretary'], b['treasurer']
    print("\nSchedule B -- Cash Transactions")
    print(f"  Dues & initiations:     ${fs['dues_and_initiations_received']:,.2f}")
    for f in fs['top_fundraisers']:
        print(f"  Fundraiser {f['name']}: ${f['amount']:,.2f}")
    print(f"  Miscellaneous income:   ${fs['misc_income']:,.2f}")
    print(f"  FS closing in-hand:     ${fs['closing_funds_in_possession']:,.2f}")
    print(f"  Checking interest:      ${tr['checking_account_interest']:,.2f}")
    print(f"  Per capita Supreme/State: ${tr['per_capita_supreme_council']:,.2f} / ${tr['per_capita_state_council']:,.2f}")
    print(f"  Charitable donations:   ${tr['charitable_donations']:,.2f}")
    print(f"  Transfers to savings:   ${tr['transfers_to_savings']:,.2f}")
    print(f"  Checking closing:       ${tr['closing_balance']:,.2f}")

    print("\nSchedule C -- Financial Position")
    print(f"  Total current assets:   ${c['assets']['current']['total_current_assets']:,.2f}")
    print(f"  Total liabilities:      ${c['liabilities']['total_liabilities']:,.2f}")
    print(f"    (misc liabilities:    ${c['liabilities']['misc_liabilities']:,.2f} -- left unexplained on purpose)")
    print(f"  Net current assets:     ${c['net_current_assets']:,.2f}")
    print(f"  Total long-term assets: ${c['assets']['long_term']['total_long_term_assets']:,.2f}")
    print(f"  Total assets:           ${c['assets']['total_assets']:,.2f}")
    print(f"  Total net assets:       ${c['total_net_assets']:,.2f}")

    if not a['reconciled']:
        print("\n  NOTE: reconciled=False means a member's status was changed")
        print("  without a logged event (outside this loader). The page will")
        print("  show a reconciliation warning -- that is the feature working,")
        print("  not the demo failing.")


# ==================== MAIN ====================

def main():
    with app.app_context():
        org = get_org()
        if not org:
            return

        period_start, period_end, period_label = get_audit_period()
        print("=" * 62)
        print("KNIGHTS OF COLUMBUS -- SIX-MONTH COUNCIL DEMO DATA")
        print("=" * 62)
        print(f"Organization:  {org.name} (council #{org.council_number})")
        print(f"Audit period:  {period_label}")
        print("\nThis DELETES existing members, projects, transactions,")
        print("invoices, donors, and vendors and replaces them with a")
        print("council-scale demo book. Demo loader -- never run against")
        print("a council's real books.\n")

        # Everything below is destructive. On a live deployment the rows
        # this would delete are a council's real books, so the guard
        # decides rather than the choice of script -- see demo_guard.py.
        if not demo_reset_allowed():
            print(demo_reset_refusal_message('wipe and reload demo data'))
            return

        try:
            clear_existing_data()

            # Audit trail: attach the triggers (so the load below is
            # captured), then reset the log (so it opens on this council's
            # book rather than on the wipe above). Order matters.
            print("Preparing the audit trail...")
            ensure_audit_triggers()
            reset_audit_log()

            _load_accounts()
            admin = get_admin_user(org)

            print("Creating the founding roster...")
            founding = create_founding_roster(org, period_start)
            print(f"  {len(founding)} members on the roll at {period_start}.")

            print("Logging one addition of each type...")
            new_members = create_period_additions(org, period_start)
            print(f"  {', '.join(m.name for m in new_members)}")

            print("Logging one deduction of each type...")
            deducted = create_period_deductions(org, period_start, [m.id for m in new_members])
            print(f"  {', '.join(m.name for m in deducted)}")

            print("Creating projects...")
            projects = create_projects(org, period_start)
            print(f"  {', '.join(projects)}")

            print("Posting opening balances at 12/31/2025...")
            load_opening_balances(projects, admin.id)

            print("Posting dues, one entry per member, into the 'Dues' project...")
            d = post_member_dues(org, projects, admin.id, dues_year=period_end.year)
            print(f"  {d['records']} dues records ({d['paid']} paid, "
                  f"{d['records'] - d['paid']} unpaid).")
            print(f"  {d['entries']} entries posted, ${d['revenue']:,.2f} to account 4110, "
                  f"${d['in_hand']:,.2f} still in the Financial Secretary's hands.")

            print("Posting six months of council transactions...")
            count = load_period_transactions(projects, admin.id)

            print("Creating vendors...")
            vendors = create_vendors(org)
            print(f"  {len(vendors)} vendors "
                  f"({sum(1 for v in vendors.values() if v.is_1099)} receive a Form 1099).")

            print("Posting six months of accounts payable through the AP service...")
            ap = create_ap_activity(org, vendors, projects, admin.id)
            print(f"  {ap['invoices']} invoices: {ap['paid']} paid, {ap['open']} still open "
                  f"(${ap['open_total']:,.2f} outstanding today).")
            print("  Open invoice due dates are anchored to today, so every aging")
            print("  bucket -- Current through 90+ -- has something in it.")

            print("Saving one wizard explanation, leaving one deliberately blank...")
            save_wizard_demo_state(org, period_start, period_end)
            print("  Schedule C's miscellaneous-liabilities line is left unexplained on purpose.")

            print_expected_results(org, period_start, period_end)

            from models import Invoice
            buckets = {}
            for inv in Invoice.query.filter(
                Invoice.organization_id == org.id,
                Invoice.status.in_(['Open', 'Partial']),
            ).all():
                buckets[inv.aging_bucket] = buckets.get(inv.aging_bucket, Decimal('0')) + inv.amount_due
            print("\nAP aging as of today (/ap/aging):")
            for b in ('Current', '1-30', '31-60', '61-90', '90+'):
                print(f"  {b:>8}: ${buckets.get(b, Decimal('0')):>9,.2f}")

            rows = audit_log_row_count()
            if rows:
                print(f"\nAudit trail: {rows:,} rows written by the load, chained from")
                print("genesis. /audit/log will show them; 'Verify Chain Integrity'")
                print("on that page should report the chain intact.")

            print("\nCouncil demo data loaded successfully.")
            print("Visit /audit/form-1295 as an Admin -- the default period "
                  f"({period_label}) matches what was just seeded.")
            print("Visit /audit/log for the Trustee Audit Report.")
        except Exception as e:
            db.session.rollback()
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()

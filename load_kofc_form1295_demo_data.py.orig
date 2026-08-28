"""
Knights of Columbus Form 1295 -- Demo Data Loader
====================================================

Seeds one Council's data so that every line of Form 1295's Schedule A, B,
and C (see services/kofc_form_1295.py) has a real, non-trivial, correctly
computed number behind it for the current default audit period -- the
same period /audit/form-1295 shows when opened with no date range picked
(see get_audit_period()).

COMPOSES with whatever is already in the database rather than assuming a
clean slate: members that already exist (e.g. the 20 created by
load_comprehensive_data.py) become the start-of-period roster -- they are
backfilled with an Initiation event at their join_date if they have no
membership event yet (same semantics as migrate_production.py's
backfill), NOT duplicated with a second parallel roster. Extra "founding"
members are created only if the database holds fewer than 15. Dues
records are created for EVERY member missing one for the period's dues
year, so the member count and the dues-record count tell one coherent
story on the Schedule A page.

Because the ledger may already contain other posted activity in the
period (load_comprehensive_data.py posts dues, donations, and expenses in
2026), the totals on screen are NOT hardcoded expectations -- this loader
finishes by computing schedule_a/b/c through the exact same code the page
uses and PRINTING those results, so what you see in the terminal is
precisely what /audit/form-1295 will show.

To reset and reload from scratch:
    python load_comprehensive_data.py   (wipes + reloads the base demo data)
    python load_kofc_form1295_demo_data.py

What this seeds, and why:

  Schedule A (Membership roll-forward)
    - Existing members become the start-of-period roster (backfilled
      Initiation events where missing).
    - One addition of EACH of the four addition types (Initiation,
      Transfer In, Re-entry, Transfer from Insurance to Associate) --
      four new members, each with exactly one addition event, so the
      roll-forward and the live Active count agree (reconciled = True).
    - One deduction of EACH of the five deduction types (Suspension,
      Death, Withdrawal, Transfer Out, Transfer from Associate to
      Insurance), applied to five existing active members.
    - A MemberDuesPayment row for every member for the dues year
      (~80% paid), so member count and dues-record count line up.

  Schedule B (Cash Transactions)
    - Dues AND initiation fees (accounts 4110 / 4115) -- the combined
      Financial Secretary line.
    - Three fundraiser-flagged projects with different revenue totals.
      Only the top two get their own named line on the real form; the
      third (smallest) fundraiser's proceeds correctly fall through into
      "miscellaneous income" instead of vanishing. (Revenue from
      pre-existing projects not flagged as fundraisers -- donations,
      program fees, event revenue -- also correctly lands in misc
      income; that is the real form's behavior, not a bug.)
    - Checking-account interest (4415) AND non-checking investment
      interest (4410) -- proving the split holds: only the former shows
      up on Schedule B.
    - A Financial Secretary cash-on-hand cycle (account 1040): one dues
      collection held in cash then deposited, and one collected at
      period end and deliberately NOT yet deposited, so closing "funds
      in possession" is genuinely non-zero.
    - Per capita to Supreme and State, charitable donations, general
      council expenses, and a net transfer to savings.

  Schedule C (Financial Position)
    - A certificate of deposit and mutual fund purchase (long-term
      assets) plus money market interest, so the two-tier
      current/long-term split has real numbers on both sides.
    - Accrued (unpaid) per capita liabilities to Supreme and State.
    - One unpaid utility bill so "miscellaneous liabilities" is non-zero
      -- deliberately left WITHOUT a wizard explanation so the "Needs
      explanation" state is visible next to the explained misc-income
      line.

  The Form1295Submission wizard
    - Miscellaneous income gets a saved explanation; miscellaneous
      liabilities is deliberately left unexplained; nothing is attested.

Safe to run multiple times: skips everything if it detects this data was
already loaded (looks for the "Spring Raffle 2026" project).
"""
from datetime import date, timedelta
from decimal import Decimal

from app import app, db
from models import (
    Organization, User, Member, Project, MembershipEvent, MemberDuesPayment,
    MEMBERSHIP_EVENT_ADDITION_TYPES, MEMBERSHIP_EVENT_DEDUCTION_TYPES,
)
from services.journal_service import post_simple_entry
from services.kofc_form_1295 import (
    get_audit_period, save_submission_explanations,
    schedule_a, schedule_b, schedule_c,
)

MARKER_PROJECT_NAME = 'Spring Raffle 2026'
MIN_FOUNDING_ROSTER = 15


def already_loaded(org_id):
    return Project.query.filter_by(organization_id=org_id, name=MARKER_PROJECT_NAME).first() is not None


def get_org():
    org = Organization.query.first()
    if not org:
        print("ERROR: No organization found. Run init_db.py first.")
        return None
    # Fill in Knights of Columbus council identity if it isn't set yet --
    # printed on the Form 1295 PDFs' header/footer. Never overwrites a
    # value the user already entered in Settings.
    changed = False
    if not org.council_number:
        org.council_number = '14203'
        changed = True
    if not org.district_deputy_name:
        org.district_deputy_name = 'Robert T. Whalen'
        changed = True
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


def backfill_missing_events(org, period_start):
    """Any existing member with zero membership events gets one Initiation
    event at their join_date -- identical semantics to
    migrate_production.py's backfill, so this loader works the same
    whether or not that migration already ran."""
    members_without_events = Member.query.filter(
        Member.organization_id == org.id,
        ~Member.id.in_(db.session.query(MembershipEvent.member_id).distinct()),
    ).all()
    for member in members_without_events:
        event_date = member.join_date or (period_start - timedelta(days=700))
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type='Initiation',
            event_date=event_date,
            notes='Backfilled by Form 1295 demo loader -- join predates event tracking.',
        ))
    db.session.commit()
    return len(members_without_events)


def top_up_founding_members(org, period_start):
    """Create extra pre-period members ONLY if the database holds fewer
    than MIN_FOUNDING_ROSTER -- never duplicates an existing roster."""
    existing_count = Member.query.filter_by(organization_id=org.id).count()
    to_create = max(0, MIN_FOUNDING_ROSTER - existing_count)
    for i in range(to_create):
        join_date = period_start - timedelta(days=700 - (i * 20))
        member = Member(
            name=f"Founding Member {i + 1}",
            email=f"founding.member{i + 1}@example.com",
            phone=f"555-01{i:02d}",
            address=f"{100 + i} Fraternal Ave",
            city="Springfield", state="IL", zip_code="62701",
            join_date=join_date, active=True, organization_id=org.id,
        )
        db.session.add(member)
        db.session.flush()
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type='Initiation',
            event_date=join_date, notes='Form 1295 demo data -- founding roster top-up.',
        ))
    db.session.commit()
    return to_create


def create_period_additions(org, period_start):
    """One brand-new member per addition type, each logged with exactly
    one addition event dated inside the period -- keeps the roll-forward
    and the live Active count in agreement."""
    assert set(MEMBERSHIP_EVENT_ADDITION_TYPES) == {
        'Initiation', 'Transfer In (from another council)',
        'Re-entry', 'Transfer from Insurance to Associate',
    }, "MEMBERSHIP_EVENT_ADDITION_TYPES changed -- update this demo data to match."

    additions = [
        ('Initiation', 'New Knight Anderson', period_start + timedelta(days=10)),
        ('Transfer In (from another council)', 'Transferred Knight Barlow', period_start + timedelta(days=40)),
        ('Re-entry', 'Returning Knight Castillo', period_start + timedelta(days=70)),
        ('Transfer from Insurance to Associate', 'Reclassified Knight Delgado', period_start + timedelta(days=100)),
    ]
    members = []
    for event_type, name, event_date in additions:
        member = Member(
            name=name, email=f"{name.split()[-1].lower()}@example.com",
            phone="555-0200", address="200 Fraternal Ave", city="Springfield",
            state="IL", zip_code="62701", join_date=event_date,
            active=True, organization_id=org.id,
        )
        db.session.add(member)
        db.session.flush()
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type=event_type,
            event_date=event_date, notes='Form 1295 demo data -- period addition.',
        ))
        members.append(member)
    db.session.commit()
    return members


def create_period_deductions(org, period_start, new_member_ids):
    """Five existing active members (never the four just added), one
    deduction type each, deactivated with an event dated inside the
    period."""
    assert set(MEMBERSHIP_EVENT_DEDUCTION_TYPES) == {
        'Suspension', 'Death', 'Withdrawal',
        'Transfer Out (to another council)', 'Transfer from Associate to Insurance',
    }, "MEMBERSHIP_EVENT_DEDUCTION_TYPES changed -- update this demo data to match."

    candidates = Member.query.filter(
        Member.organization_id == org.id,
        Member.active == True,
        ~Member.id.in_(new_member_ids),
    ).order_by(Member.id).limit(5).all()
    if len(candidates) < 5:
        raise RuntimeError(
            f"Need at least 5 existing active members for deductions, found {len(candidates)}."
        )

    deductions = [
        ('Suspension', period_start + timedelta(days=15)),
        ('Death', period_start + timedelta(days=45)),
        ('Withdrawal', period_start + timedelta(days=75)),
        ('Transfer Out (to another council)', period_start + timedelta(days=105)),
        ('Transfer from Associate to Insurance', period_start + timedelta(days=135)),
    ]
    for (event_type, event_date), member in zip(deductions, candidates):
        member.active = False
        db.session.add(MembershipEvent(
            member_id=member.id, organization_id=org.id, event_type=event_type,
            event_date=event_date, notes='Form 1295 demo data -- period deduction.',
        ))
    db.session.commit()
    return candidates


def create_dues_payments(org, dues_year):
    """A dues record for EVERY member of the org missing one for the
    year (~80% paid) -- so the member count and dues-record count on the
    Schedule A page tell one coherent story."""
    members_with_record = {
        row[0] for row in db.session.query(MemberDuesPayment.member_id).filter(
            MemberDuesPayment.organization_id == org.id,
            MemberDuesPayment.year == dues_year,
        ).all()
    }
    members = Member.query.filter_by(organization_id=org.id).order_by(Member.id).all()
    created = paid_count = 0
    for i, member in enumerate(members):
        if member.id in members_with_record:
            continue
        paid = i % 5 != 0  # 4 out of every 5 paid, 1 unpaid
        db.session.add(MemberDuesPayment(
            member_id=member.id, organization_id=org.id, year=dues_year,
            paid_date=(date(dues_year, 2, 1) if paid else None),
            include_in_transaction=False,  # the ledger total below is posted separately
        ))
        created += 1
        paid_count += 1 if paid else 0
    db.session.commit()
    return created, paid_count


def create_projects(org):
    regular = Project(
        name='Council Operations - Form 1295 Demo', organization_id=org.id,
        status='Active', is_fundraiser=False,
        description='Form 1295 demo data -- ordinary council operations.',
    )
    raffle = Project(
        name='Spring Raffle 2026', organization_id=org.id,
        status='Completed', is_fundraiser=True,
        description='Form 1295 demo data -- largest fundraiser this period.',
    )
    pancake = Project(
        name='Pancake Breakfast 2026', organization_id=org.id,
        status='Completed', is_fundraiser=True,
        description='Form 1295 demo data -- second-largest fundraiser this period.',
    )
    golf = Project(
        name='Golf Outing 2026', organization_id=org.id,
        status='Completed', is_fundraiser=True,
        description=('Form 1295 demo data -- deliberately the THIRD, smallest '
                      'fundraiser: proves proceeds beyond the top two correctly '
                      'fall into miscellaneous income rather than vanishing.'),
    )
    db.session.add_all([regular, raffle, pancake, golf])
    db.session.commit()
    return regular, raffle, pancake, golf


def create_financial_transactions(org, projects, admin_id, period_start, period_end):
    regular, raffle, pancake, golf = projects
    d = lambda offset: period_start + timedelta(days=offset)  # noqa: E731

    def post(entry_date, description, project, debit, credit, amount, memo=''):
        return post_simple_entry(
            entry_date=entry_date, description=description, project_id=project.id,
            created_by=admin_id, debit_account=debit, credit_account=credit,
            amount=Decimal(str(amount)), memo=memo or description,
        )

    # ---- Dues collected straight to checking ----
    post(d(5), 'Dues collected', regular, '1010', '4110', '1800.00')
    post(d(60), 'Dues collected', regular, '1010', '4110', '900.00')

    # ---- Financial Secretary cash-on-hand cycle (account 1040) ----
    # Collected in cash, then deposited -- exercises "transferred to Treasurer".
    post(d(12), 'Dues collected in cash by FS', regular, '1040', '4110', '300.00')
    post(d(14), 'FS deposits collected dues', regular, '1010', '1040', '300.00')
    # Collected right at period end, deliberately not yet deposited --
    # closing "funds in possession" is genuinely non-zero.
    last_day_offset = (period_end - period_start).days - 2
    post(d(last_day_offset), 'Dues collected in cash by FS (not yet deposited)',
         regular, '1040', '4110', '100.00')

    # ---- Initiation fees for the four new members this period ----
    for offset in (11, 41, 71, 101):
        post(d(offset), 'Initiation fee', regular, '1010', '4115', '30.00')

    # ---- Fundraiser revenue: three projects, three different totals ----
    post(d(20), 'Raffle ticket sales', raffle, '1010', '4210', '2200.00')
    post(d(25), 'Raffle ticket sales - late entries', raffle, '1010', '4210', '1000.00')
    post(d(50), 'Pancake breakfast proceeds', pancake, '1010', '4210', '1200.00')
    post(d(52), 'Pancake breakfast proceeds - second seating', pancake, '1010', '4210', '600.00')
    # Deliberately the smallest -- see module docstring for why this
    # matters: it should land in misc income, not disappear.
    post(d(90), 'Golf outing net proceeds', golf, '1010', '4220', '600.00')

    # ---- Interest: checking (Schedule B) vs. everything else (Schedule C only) ----
    for offset in (30, 60, 90, 120, 150, 175):
        post(d(offset), 'Checking account interest', regular, '1010', '4415', '2.50')
    post(d(60), 'Savings account interest', regular, '1020', '4410', '8.00')
    post(d(150), 'Money market interest', regular, '1330', '4410', '12.00')

    # ---- Per capita: some paid in cash, some accrued (unpaid) at period end ----
    post(d(95), 'Per capita paid to Supreme Council', regular, '5850', '1010', '600.00')
    post(d(last_day_offset), 'Per capita accrued to Supreme Council (unpaid)',
         regular, '5850', '2130', '50.00')
    post(d(95), 'Per capita paid to State Council', regular, '5860', '1010', '240.00')
    post(d(last_day_offset), 'Per capita accrued to State Council (unpaid)',
         regular, '5860', '2140', '30.00')

    # ---- Charitable donations given ----
    post(d(110), 'Charitable donation - local food bank', regular, '5870', '1010', '500.00')
    post(d(130), 'Charitable donation - scholarship fund', regular, '5870', '1010', '300.00')

    # ---- Ordinary general council expenses ----
    post(d(35), 'Hall rent', regular, '5210', '1010', '200.00')
    post(d(65), 'Utilities', regular, '5220', '1010', '150.00')
    post(d(85), 'Office supplies', regular, '5310', '1010', '75.00')

    # ---- One unpaid utility bill -- a genuine "miscellaneous liability" ----
    post(d(last_day_offset), 'Utility bill received, not yet paid',
         regular, '5220', '2110', '85.00')

    # ---- Net transfer of cash to savings ----
    post(d(45), 'Transfer to savings', regular, '1020', '1010', '600.00')

    # ---- Long-term assets: CD and mutual fund purchases ----
    post(d(55), 'Purchase certificate of deposit', regular, '1340', '1010', '2000.00')
    post(d(75), 'Purchase mutual fund shares', regular, '1350', '1010', '1500.00')


def save_wizard_demo_state(org, period_start, period_end):
    """One misc line explained, one deliberately left blank -- so the
    submission wizard shows both states on one page. Nothing is attested,
    so the attest button is still there to click through."""
    save_submission_explanations(
        org.id, period_start, period_end,
        misc_income_explanation=(
            "Golf Outing 2026 net proceeds ($600 -- our third fundraiser this "
            "period, beyond the two named above), plus revenue from council "
            "activities not tied to a flagged fundraiser (donations, program "
            "fees, and event proceeds recorded on their own projects)."
        ),
        misc_liabilities_explanation=None,  # deliberately left for the demo
    )


def print_expected_results(org, period_start, period_end):
    """Compute the schedules through the exact same code the page uses
    and print them -- what appears below is precisely what
    /audit/form-1295 will show for the default period."""
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


def main():
    with app.app_context():
        org = get_org()
        if not org:
            return
        if already_loaded(org.id):
            print(f"Form 1295 demo data already loaded for '{org.name}' -- skipping.")
            print("To reset: python load_comprehensive_data.py, then re-run this loader.")
            return

        period_start, period_end, period_label = get_audit_period()
        print(f"Organization: {org.name} (council #{org.council_number})")
        print(f"Target audit period: {period_label}\n")

        try:
            admin = get_admin_user(org)

            print("Backfilling membership events for existing members...")
            backfilled = backfill_missing_events(org, period_start)
            print(f"  {backfilled} member(s) backfilled with an Initiation event.")

            created = top_up_founding_members(org, period_start)
            if created:
                print(f"  Roster below {MIN_FOUNDING_ROSTER} -- created {created} founding member(s).")
            else:
                print("  Existing roster is large enough -- no founding members created.")

            print("Logging one addition of each type...")
            new_members = create_period_additions(org, period_start)
            print(f"  {len(new_members)} new members added, one per addition type.")

            print("Logging one deduction of each type...")
            deducted = create_period_deductions(org, period_start, [m.id for m in new_members])
            print(f"  Deactivated: {', '.join(m.name for m in deducted)}")

            print("Creating dues records for every member missing one...")
            dues_created, dues_paid = create_dues_payments(org, dues_year=period_end.year)
            print(f"  {dues_created} dues records created ({dues_paid} marked paid).")

            print("Creating projects (one regular, three fundraisers)...")
            projects = create_projects(org)
            print(f"  {[p.name for p in projects]}")

            print("Posting financial transactions for the period...")
            create_financial_transactions(org, projects, admin.id, period_start, period_end)
            print("  Done.")

            print("Saving one wizard explanation, leaving one deliberately blank...")
            save_wizard_demo_state(org, period_start, period_end)
            print("  Done -- Schedule C's misc. liabilities line is left unexplained on purpose.")

            print_expected_results(org, period_start, period_end)

            print("\nForm 1295 demo data loaded successfully.")
            print("Visit /audit/form-1295 as an Admin -- the default period "
                  f"({period_label}) matches what was just seeded.")
        except Exception as e:
            db.session.rollback()
            print(f"\nERROR: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()

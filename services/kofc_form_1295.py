"""
Knights of Columbus Form 1295 -- Schedule A/B/C Calculation
=============================================================

Section 145 of the Laws of the Order requires councils to audit their
books twice a year and report the result on Form 1295 (see AUDIT_TRAIL.md
for the full compliance background, and blueprints/audit_routes.py for
the tamper-evident change-log this report complements). This module
computes the three schedules Form 1295 actually asks for directly from
the ledger, so a council using CARES doesn't have to reconstruct them by
hand from paper receipts:

  Schedule A -- Membership (a real roll-forward, not a snapshot)
  Schedule B -- Cash Transactions (Financial Secretary side / Treasurer side)
  Schedule C -- Financial Position (Assets / Liabilities, current + long-term)

Every number here is a real, recorded transaction total -- nothing is
estimated or inferred from account names or guesswork. Where this
system's data model can't yet distinguish something Form 1295 asks for
(see the module-level constants and comments below), the corresponding
line is reported as its own explicit, documented $0 or omission rather
than a plausible-looking guess. This matters because a trustee signs and
files this document -- see the Knights' own audit instructions: "Only
enter true and accurate numbers, no matter what they say."

Real Form 1295 structure verified against multiple independent Knights of
Columbus primary sources: a council's own audit report template, KofC
Audit Instructions (Council 8079), and state-council financial-officer
training materials (Utah, Michigan). See kofc-v2-backlog.md for the
source list.

Recording convention this module assumes
-------------------------------------------
Dues, fundraiser, and other income can be recorded either straight to the
Treasurer's bank account (account 1010) or, for councils that model the
Financial Secretary physically holding cash/checks before handing them to
the Treasurer for deposit, to account 1040 (Financial Secretary Cash on
Hand) with a separate transfer entry into 1010 once deposited. Schedule
B's "total cash received" (Financial Secretary side) sums actual revenue
recognized either way, so it's correct under both practices; only the
"funds in the Financial Secretary's possession" opening/closing lines
depend on whether 1040 is actually used -- if a council never uses it,
those lines are correctly $0 throughout, since no cash is genuinely
sitting outside the bank.

Checks are recorded as disbursed the moment they're written (a normal
double-entry debit to an expense/liability account, credit to checking),
not when they clear the bank. That means the checking account's book
balance already excludes outstanding/uncleared checks by construction --
satisfying Form 1295's "opening bank balance minus uncleared checks"
requirement without any special-case bank-reconciliation logic.
"""
from datetime import date, timedelta, datetime
from decimal import Decimal

from sqlalchemy import func

from models import (
    db, ChartOfAccounts, JournalEntry, JournalEntryLine, Project,
    Member, MemberDuesPayment, MembershipEvent, Form1295Submission,
    MEMBERSHIP_EVENT_ADDITION_TYPES, MEMBERSHIP_EVENT_DEDUCTION_TYPES,
)

# Cash-type accounts (see default_chart_of_accounts.py). A journal entry
# whose lines touch only these accounts is a transfer between cash
# accounts -- not income or an expense -- and is reported on Schedule B
# as a transfer, not folded into receipts/disbursements totals.
_CASH_ACCOUNT_NUMBERS = {'1010', '1020', '1030', '1040'}

_FS_CASH_ACCOUNT = '1040'
_CHECKING_ACCOUNT = '1010'
_SAVINGS_ACCOUNT = '1020'
_MONEY_MARKET_ACCOUNT = '1330'
_CDS_ACCOUNT = '1340'
_MUTUAL_FUNDS_ACCOUNT = '1350'
_DUES_ACCOUNT = '4110'
_INITIATION_FEES_ACCOUNT = '4115'
# Non-checking investment interest (savings/CDs/money market/mutual
# funds) -- never appears on Schedule B; it only ever shows up through
# the balance change on Schedule C, since it's never cash the Financial
# Secretary or Treasurer actually received and handled.
_INVESTMENT_INTEREST_ACCOUNT = '4410'
# Checking-account interest specifically -- this is what Schedule B's
# Treasurer side actually asks for.
_CHECKING_INTEREST_ACCOUNT = '4415'
_PER_CAPITA_SUPREME_EXPENSE = '5850'
_PER_CAPITA_STATE_EXPENSE = '5860'
_CHARITABLE_GIVING_EXPENSE = '5870'
_PER_CAPITA_SUPREME_LIABILITY = '2130'
_PER_CAPITA_STATE_LIABILITY = '2140'

# Schedule C asset/liability lines that are always $0 in this system today
# because nothing in the data model tracks them -- called out explicitly
# in the report rather than silently omitted, matching Form 1295's own
# layout (both lines are also "always zero" on the paper form for most
# councils, per the Knights' own audit instructions).
ALWAYS_ZERO_NOTE = "Not tracked by this system -- always $0 on Form 1295 for most councils."


def get_audit_period(as_of=None):
    """
    Return (period_start, period_end, label) for the most recently
    COMPLETED Knights of Columbus semi-annual audit period as of `as_of`
    (defaults to today) -- Jan 1-Jun 30 (filed by Aug 15) or Jul 1-Dec 31
    (filed by Feb 15), per Section 145 and Form 1295's own filing
    deadlines. On any date in Jan-Jun, the most recently completed period
    is the prior Jul-Dec; on any date in Jul-Dec, it's the same year's
    Jan-Jun.
    """
    if as_of is None:
        as_of = date.today()
    if as_of.month <= 6:
        start, end = date(as_of.year - 1, 7, 1), date(as_of.year - 1, 12, 31)
    else:
        start, end = date(as_of.year, 1, 1), date(as_of.year, 6, 30)
    # %-d (non-padded day) is a Linux/glibc-only strftime flag -- it
    # raises ValueError on Windows' strftime, which is what this app
    # actually runs under. Built manually instead so it works on both.
    label = f"{start:%B} {start.day}, {start:%Y} - {end:%B} {end.day}, {end:%Y}"
    return start, end, label


def _account(number):
    return ChartOfAccounts.query.filter_by(account_number=number).first()


def _balance_as_of(org_id, account_number, as_of_date):
    """Cumulative balance of `account_number` as of `as_of_date`, signed
    per the account's own normal balance -- i.e. what's actually in it,
    not which side moved."""
    account = _account(account_number)
    if not account:
        return Decimal('0')
    debits = db.session.query(func.sum(JournalEntryLine.debit_amount)).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id == account.id,
        JournalEntry.entry_date <= as_of_date,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).scalar() or Decimal('0')
    credits = db.session.query(func.sum(JournalEntryLine.credit_amount)).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id == account.id,
        JournalEntry.entry_date <= as_of_date,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).scalar() or Decimal('0')
    return (debits - credits) if account.normal_balance == 'Debit' else (credits - debits)


def _period_side_total(org_id, account_number, start, end, side):
    """Total of just the debit (or credit) side posted to `account_number`
    within [start, end] -- which side moved, not the net balance change.
    Used for Schedule B's received/disbursed totals, where what matters
    is which side of the account was hit, independent of its normal
    balance."""
    account = _account(account_number)
    if not account:
        return Decimal('0')
    column = JournalEntryLine.debit_amount if side == 'debit' else JournalEntryLine.credit_amount
    total = db.session.query(func.sum(column)).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id == account.id,
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date <= end,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).scalar() or Decimal('0')
    return total


def _revenue_received_excluding(org_id, start, end, exclude_account_numbers):
    """Total credits posted to Revenue-type accounts within the period,
    excluding the given account numbers (used to isolate the truly
    "miscellaneous" income Schedule B needs, after dues, initiations, and
    interest -- all reported on their own lines -- are pulled out)."""
    excluded_ids = [a.id for a in ChartOfAccounts.query.filter(
        ChartOfAccounts.account_number.in_(exclude_account_numbers)
    ).all()]
    revenue_account_ids = [a.id for a in ChartOfAccounts.query.filter_by(account_type='Revenue').all()
                            if a.id not in excluded_ids]
    if not revenue_account_ids:
        return Decimal('0')
    total = db.session.query(func.sum(JournalEntryLine.credit_amount)).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id.in_(revenue_account_ids),
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date <= end,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).scalar() or Decimal('0')
    return total


def _cash_transfers_net(org_id, start, end, into_account_number, from_cash_account_numbers):
    """Net amount moved INTO `into_account_number` from any of
    `from_cash_account_numbers` via pure cash-to-cash transfer entries
    (every line on the entry touches only cash-type accounts -- see
    _CASH_ACCOUNT_NUMBERS) within [start, end]. Positive means net money
    moved in; negative means net money moved out. This is how Schedule
    B's "transfers from/to savings" and "amounts transferred to
    Treasurer" are computed -- from the entries actually posted, not
    inferred from account names."""
    into_account = _account(into_account_number)
    from_accounts = ChartOfAccounts.query.filter(
        ChartOfAccounts.account_number.in_(from_cash_account_numbers)
    ).all()
    if not into_account or not from_accounts:
        return Decimal('0')
    from_ids = {a.id for a in from_accounts}
    cash_account_ids = {a.id for a in ChartOfAccounts.query.filter(
        ChartOfAccounts.account_number.in_(_CASH_ACCOUNT_NUMBERS)
    ).all()}

    entries = JournalEntry.query.join(Project).filter(
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date <= end,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).all()

    net = Decimal('0')
    for entry in entries:
        lines = entry.lines.all() if hasattr(entry.lines, 'all') else list(entry.lines)
        touched_ids = {line.account_id for line in lines}
        if not touched_ids or not touched_ids.issubset(cash_account_ids):
            continue  # not a pure cash-to-cash transfer entry
        if into_account.id not in touched_ids or not (touched_ids & from_ids):
            continue  # doesn't touch both sides of this specific transfer
        for line in lines:
            if line.account_id == into_account.id:
                net += line.debit_amount - line.credit_amount
    return net


def _membership_count_as_of(org_id, as_of_date):
    """Net membership count from replaying every logged event up to and
    including `as_of_date` -- additions minus deductions. This is the
    real source of truth for Schedule A's roll-forward; Member.active is
    a denormalized convenience flag kept in sync with events (see
    blueprints/member_routes.py), not the record itself."""
    additions = db.session.query(func.count(MembershipEvent.id)).filter(
        MembershipEvent.organization_id == org_id,
        MembershipEvent.event_type.in_(MEMBERSHIP_EVENT_ADDITION_TYPES),
        MembershipEvent.event_date <= as_of_date,
    ).scalar() or 0
    deductions = db.session.query(func.count(MembershipEvent.id)).filter(
        MembershipEvent.organization_id == org_id,
        MembershipEvent.event_type.in_(MEMBERSHIP_EVENT_DEDUCTION_TYPES),
        MembershipEvent.event_date <= as_of_date,
    ).scalar() or 0
    return additions - deductions


def schedule_a(org_id, period_start, period_end):
    """Membership roll-forward for the audit period, exactly as Form
    1295's real Schedule A asks for it: start-of-period count, plus
    categorized additions, minus categorized deductions, equals
    end-of-period count. See models.py::MembershipEvent for why this
    needs its own event log rather than a plain active/inactive flag, and
    for why the paper form's symmetric "assoc./insurance transfer"
    categories are modeled here as two unambiguous, directional types.
    """
    members_start_of_period = _membership_count_as_of(org_id, period_start - timedelta(days=1))

    def _count_in_period(event_type):
        return MembershipEvent.query.filter(
            MembershipEvent.organization_id == org_id,
            MembershipEvent.event_type == event_type,
            MembershipEvent.event_date >= period_start,
            MembershipEvent.event_date <= period_end,
        ).count()

    additions = {event_type: _count_in_period(event_type) for event_type in MEMBERSHIP_EVENT_ADDITION_TYPES}
    deductions = {event_type: _count_in_period(event_type) for event_type in MEMBERSHIP_EVENT_DEDUCTION_TYPES}
    total_additions = sum(additions.values())
    total_deductions = sum(deductions.values())
    total_for_period = members_start_of_period + total_additions
    members_end_of_period = total_for_period - total_deductions

    # Reconciliation: the roll-forward should agree with the live
    # active-member count. A mismatch means some status change happened
    # without a logged event (e.g. someone toggled the Active checkbox
    # directly instead of recording why) -- surfaced as a warning on the
    # report rather than silently trusting either number.
    active_members_actual = Member.query.filter_by(organization_id=org_id, active=True).count()

    dues_year = period_end.year
    dues_records = MemberDuesPayment.query.join(Member).filter(
        Member.organization_id == org_id,
        MemberDuesPayment.year == dues_year,
    ).all()
    dues_paid_count = sum(1 for r in dues_records if r.is_paid)
    # The real ledger total for dues actually posted in this period --
    # not derived from MemberDuesPayment rows, since a payment can be
    # marked paid without yet being posted to the GL (include_in_transaction).
    dues_total_collected = _period_side_total(org_id, _DUES_ACCOUNT, period_start, period_end, 'credit')

    return {
        'period_start': period_start,
        'period_end': period_end,
        'members_start_of_period': members_start_of_period,
        'additions': additions,
        'total_additions': total_additions,
        'total_for_period': total_for_period,
        'deductions': deductions,
        'total_deductions': total_deductions,
        'members_end_of_period': members_end_of_period,
        'active_members_actual': active_members_actual,
        'reconciled': members_end_of_period == active_members_actual,
        'dues_year': dues_year,
        'dues_records_for_year': len(dues_records),
        'dues_paid_for_year': dues_paid_count,
        'dues_collected_in_period': dues_total_collected,
    }


# Cash-disbursement categorisation for Schedule B's Treasurer section.
# Paying down a per-capita PAYABLE is per capita paid in cash just as much
# as expensing it directly, so both the expense and the liability account
# map to the same line.
_SAVINGS_TRANSFER_ACCOUNTS = {_SAVINGS_ACCOUNT}
_INVESTMENT_ACCOUNTS = {_MONEY_MARKET_ACCOUNT, _CDS_ACCOUNT, _MUTUAL_FUNDS_ACCOUNT}
_PER_CAPITA_SUPREME_CASH_ACCOUNTS = {_PER_CAPITA_SUPREME_EXPENSE, _PER_CAPITA_SUPREME_LIABILITY}
_PER_CAPITA_STATE_CASH_ACCOUNTS = {_PER_CAPITA_STATE_EXPENSE, _PER_CAPITA_STATE_LIABILITY}


def _checking_disbursements_by_category(org_id, start, end):
    """Every dollar that actually LEFT checking in the period, split into
    the Treasurer's disbursement lines.

    Form 1295's Treasurer section is a CASH statement. A trustee verifies
    it by confirming that opening balance plus receipts minus
    disbursements equals the closing balance. That only holds if the
    disbursement lines are cash.

    These lines used to be computed from expense-account DEBITS, which is
    accrual, and broke the footing three different ways -- silently, since
    nothing checked:

      - an expense accrued but not paid before period end (per capita
        payable, an unpaid utility bill) was reported as disbursed
        although no cash moved;
      - a non-cash expense (depreciation) was reported as disbursed;
      - cash spent on something that is not an expense account (buying a
        CD or a mutual fund) appeared on no line at all.

    So categories come from the other side of each entry that credits
    checking, with the cash split across that entry's debit lines in
    proportion to their amounts -- exact for an ordinary two-line entry,
    and correct in general for a compound one.

    Transfers to savings are deliberately NOT bucketed here: they keep
    their existing net-of-both-directions treatment on the schedule, and
    the same netting is applied to the receipts side, so the two remain
    consistent with each other.
    """
    buckets = {
        'per_capita_supreme_council': Decimal('0'),
        'per_capita_state_council': Decimal('0'),
        'charitable_donations': Decimal('0'),
        'transfers_to_investments': Decimal('0'),
        'general_council_expenses': Decimal('0'),
    }
    checking = _account(_CHECKING_ACCOUNT)
    if not checking:
        return buckets

    credited = db.session.query(
        JournalEntryLine.journal_entry_id,
        func.sum(JournalEntryLine.credit_amount),
    ).join(JournalEntry, JournalEntry.id == JournalEntryLine.journal_entry_id).join(
        Project, Project.id == JournalEntry.project_id
    ).filter(
        JournalEntryLine.account_id == checking.id,
        JournalEntry.entry_date >= start,
        JournalEntry.entry_date <= end,
        JournalEntry.status == 'Posted',
        Project.organization_id == org_id,
    ).group_by(JournalEntryLine.journal_entry_id).all()

    entry_cash_out = {eid: amount for eid, amount in credited if amount}
    if not entry_cash_out:
        return buckets

    debit_rows = db.session.query(
        JournalEntryLine.journal_entry_id,
        ChartOfAccounts.account_number,
        JournalEntryLine.debit_amount,
    ).join(ChartOfAccounts, ChartOfAccounts.id == JournalEntryLine.account_id).filter(
        JournalEntryLine.journal_entry_id.in_(list(entry_cash_out)),
        JournalEntryLine.debit_amount > 0,
    ).all()

    legs_by_entry = {}
    for entry_id, account_number, amount in debit_rows:
        legs_by_entry.setdefault(entry_id, []).append((account_number, amount or Decimal('0')))

    for entry_id, cash_out in entry_cash_out.items():
        legs = legs_by_entry.get(entry_id, [])
        total_debits = sum((amount for _, amount in legs), Decimal('0'))
        if total_debits <= 0:
            # Cash left with nothing on the other side to classify it by.
            # Report it rather than drop it -- dropping it would break the
            # footing, which is the failure this function exists to end.
            buckets['general_council_expenses'] += cash_out
            continue
        for account_number, amount in legs:
            share = cash_out * (amount / total_debits)
            if account_number in _SAVINGS_TRANSFER_ACCOUNTS:
                continue  # its own line, netted -- see schedule_b
            if account_number in _PER_CAPITA_SUPREME_CASH_ACCOUNTS:
                buckets['per_capita_supreme_council'] += share
            elif account_number in _PER_CAPITA_STATE_CASH_ACCOUNTS:
                buckets['per_capita_state_council'] += share
            elif account_number == _CHARITABLE_GIVING_EXPENSE:
                buckets['charitable_donations'] += share
            elif account_number in _INVESTMENT_ACCOUNTS:
                buckets['transfers_to_investments'] += share
            else:
                buckets['general_council_expenses'] += share

    return {k: v.quantize(Decimal('0.01')) for k, v in buckets.items()}

def schedule_b(org_id, period_start, period_end):
    """Cash Transactions -- Financial Secretary side and Treasurer side,
    per Form 1295's Schedule B. See the module docstring for the
    recording convention this depends on."""
    fs_opening = _balance_as_of(org_id, _FS_CASH_ACCOUNT, period_start)
    fs_closing = _balance_as_of(org_id, _FS_CASH_ACCOUNT, period_end)

    # Fundraisers: the two projects flagged is_fundraiser with the most
    # revenue recognized in this period, by name and amount -- not a
    # guess from the project name, a real per-project revenue total.
    fundraiser_projects = Project.query.filter_by(organization_id=org_id, is_fundraiser=True).all()
    fundraiser_totals = []
    for project in fundraiser_projects:
        total = db.session.query(func.sum(JournalEntryLine.credit_amount)).join(JournalEntry).join(
            ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
        ).filter(
            JournalEntry.project_id == project.id,
            JournalEntry.entry_date >= period_start,
            JournalEntry.entry_date <= period_end,
            JournalEntry.status == 'Posted',
            ChartOfAccounts.account_type == 'Revenue',
        ).scalar() or Decimal('0')
        if total > 0:
            fundraiser_totals.append({'name': project.name, 'amount': total})
    fundraiser_totals.sort(key=lambda f: f['amount'], reverse=True)
    top_fundraisers = fundraiser_totals[:2]
    fundraiser_revenue_total = sum((f['amount'] for f in top_fundraisers), Decimal('0'))

    # Form 1295's Financial Secretary side reports "dues, initiations" as
    # one combined line.
    dues_received = (
        _period_side_total(org_id, _DUES_ACCOUNT, period_start, period_end, 'credit')
        + _period_side_total(org_id, _INITIATION_FEES_ACCOUNT, period_start, period_end, 'credit')
    )
    # Checking-account interest is a Treasurer-side line, not FS cash
    # received; non-checking investment interest never passes through
    # anyone's hands as cash at all (it shows up only via the Schedule C
    # balance). Both are excluded from the "miscellaneous income" pool
    # below, same as dues/initiations and the named fundraisers.
    checking_interest_received = _period_side_total(org_id, _CHECKING_INTEREST_ACCOUNT, period_start, period_end, 'credit')

    excluded_from_misc = {_DUES_ACCOUNT, _INITIATION_FEES_ACCOUNT, _CHECKING_INTEREST_ACCOUNT, _INVESTMENT_INTEREST_ACCOUNT}
    other_revenue_total = _revenue_received_excluding(org_id, period_start, period_end, excluded_from_misc)
    misc_income = other_revenue_total - fundraiser_revenue_total
    if misc_income < 0:
        misc_income = Decimal('0')  # fundraiser accounting can overlap with other lines; never show a negative "misc"

    total_cash_received_fs = dues_received + fundraiser_revenue_total + misc_income

    # Amount handed off to the Treasurer this period, derived from the FS
    # cash account's own activity rather than assumed equal to receipts --
    # this stays correct whether or not a council actually uses account
    # 1040 to model cash-in-hand (see module docstring).
    transferred_to_treasurer = fs_opening + total_cash_received_fs - fs_closing

    checking_opening = _balance_as_of(org_id, _CHECKING_ACCOUNT, period_start)
    checking_closing = _balance_as_of(org_id, _CHECKING_ACCOUNT, period_end)
    transfers_from_savings = max(
        _cash_transfers_net(org_id, period_start, period_end, _CHECKING_ACCOUNT, {_SAVINGS_ACCOUNT}),
        Decimal('0'),
    )
    transfers_to_savings = max(
        -_cash_transfers_net(org_id, period_start, period_end, _CHECKING_ACCOUNT, {_SAVINGS_ACCOUNT}),
        Decimal('0'),
    )

    # Cash that actually left checking, categorised by what it bought --
    # not expense-account debits. See _checking_disbursements_by_category
    # for the three ways the old accrual-based version failed to foot.
    disbursed = _checking_disbursements_by_category(org_id, period_start, period_end)
    per_capita_supreme = disbursed['per_capita_supreme_council']
    per_capita_state = disbursed['per_capita_state_council']
    charitable_giving = disbursed['charitable_donations']
    general_council_expenses = disbursed['general_council_expenses']
    transfers_to_investments = disbursed['transfers_to_investments']

    total_receipts = transferred_to_treasurer + transfers_from_savings + checking_interest_received
    total_disbursements = (
        per_capita_supreme + per_capita_state + charitable_giving
        + general_council_expenses + transfers_to_investments + transfers_to_savings
    )
    # A trustee checks this section by confirming opening + receipts -
    # disbursements = closing. Do the same check here and report the
    # result, so any discrepancy is stated on the document instead of
    # waiting to be found with a calculator -- or not found.
    expected_closing = checking_opening + total_receipts - total_disbursements
    unreconciled_difference = checking_closing - expected_closing



    return {
        'period_start': period_start,
        'period_end': period_end,
        'financial_secretary': {
            'opening_funds_in_possession': fs_opening,
            'dues_and_initiations_received': dues_received,
            'top_fundraisers': top_fundraisers,
            'misc_income': misc_income,
            'total_cash_received': total_cash_received_fs,
            'transferred_to_treasurer': transferred_to_treasurer,
            'closing_funds_in_possession': fs_closing,
        },
        'treasurer': {
            'opening_balance': checking_opening,
            'received_from_financial_secretary': transferred_to_treasurer,
            'transfers_from_savings': transfers_from_savings,
            'checking_account_interest': checking_interest_received,
            'per_capita_supreme_council': per_capita_supreme,
            'per_capita_state_council': per_capita_state,
            'general_council_expenses': general_council_expenses,
            'transfers_to_savings': transfers_to_savings,
            'transfers_to_investments': transfers_to_investments,
            'charitable_donations': charitable_giving,
            'total_receipts': total_receipts,
            'total_disbursements': total_disbursements,
            'closing_balance': checking_closing,
            'reconciles': abs(unreconciled_difference) < Decimal('0.01'),
            'unreconciled_difference': unreconciled_difference,
        },
        'note': (
            "Checking balances above are this system's book balance as of each "
            "date. Checks are recorded as disbursed when written, not when they "
            "clear, so this already reflects outstanding checks as spent -- "
            "satisfying Form 1295's 'minus uncleared checks' requirement by "
            "construction rather than needing a separate reconciliation step."
        ),
    }


def schedule_c(org_id, as_of_date):
    """Financial Position (Assets / Liabilities) as of the end of the
    audit period, per Form 1295's Schedule C -- reported in the same
    two-tier shape as the real form: current assets are totaled and
    netted against total liabilities first ("Net Current Assets"), then
    long-term/other assets are added on top to reach "Total Assets" and
    a final "Total Net Assets"."""
    checking = _balance_as_of(org_id, _CHECKING_ACCOUNT, as_of_date)
    fs_cash = _balance_as_of(org_id, _FS_CASH_ACCOUNT, as_of_date)
    savings = _balance_as_of(org_id, _SAVINGS_ACCOUNT, as_of_date)
    money_market = _balance_as_of(org_id, _MONEY_MARKET_ACCOUNT, as_of_date)
    cds = _balance_as_of(org_id, _CDS_ACCOUNT, as_of_date)
    mutual_funds = _balance_as_of(org_id, _MUTUAL_FUNDS_ACCOUNT, as_of_date)

    total_current_assets = checking + fs_cash + savings + money_market  # due_from_members is always $0

    # Everything else -- fixed assets, receivables, and any other asset
    # account -- has no line of its own on Form 1295 and falls into the
    # same "Other Assets/Miscellaneous" catch-all the real form itself
    # uses, alongside CDs and mutual funds, as a long-term/other bucket.
    named_asset_numbers = {_CHECKING_ACCOUNT, _FS_CASH_ACCOUNT, _SAVINGS_ACCOUNT,
                            _MONEY_MARKET_ACCOUNT, _CDS_ACCOUNT, _MUTUAL_FUNDS_ACCOUNT}
    named_asset_ids = [a.id for a in ChartOfAccounts.query.filter(
        ChartOfAccounts.account_number.in_(named_asset_numbers)
    ).all()]
    other_asset_accounts = ChartOfAccounts.query.filter(
        ChartOfAccounts.account_type == 'Asset',
        ChartOfAccounts.active == True,
        ChartOfAccounts.id.notin_(named_asset_ids),
    ).all()
    # _balance_as_of signs by each account's OWN normal balance, so a
    # contra-asset -- 1590 Accumulated Depreciation, whose account_type is
    # 'Asset' with a Credit normal balance -- comes back POSITIVE, meaning
    # "this much depreciation has accumulated". Adding that to assets
    # overstates Total Assets and Total Net Assets by twice its balance.
    # Negate it so it reduces assets, which is what a contra account does.
    # Same convention as services/reports.py::balance_sheet_detailed(),
    # where this exact defect was found and fixed once already.
    other_assets = Decimal('0')
    for a in other_asset_accounts:
        balance = _balance_as_of(org_id, a.account_number, as_of_date)
        other_assets += -balance if 'contra' in (a.account_subtype or '').lower() else balance

    total_long_term_assets = cds + mutual_funds + other_assets
    total_assets = total_current_assets + total_long_term_assets

    per_capita_supreme_payable = _balance_as_of(org_id, _PER_CAPITA_SUPREME_LIABILITY, as_of_date)
    per_capita_state_payable = _balance_as_of(org_id, _PER_CAPITA_STATE_LIABILITY, as_of_date)

    named_liability_numbers = {_PER_CAPITA_SUPREME_LIABILITY, _PER_CAPITA_STATE_LIABILITY}
    named_liability_ids = [a.id for a in ChartOfAccounts.query.filter(
        ChartOfAccounts.account_number.in_(named_liability_numbers)
    ).all()]
    other_liability_accounts = ChartOfAccounts.query.filter(
        ChartOfAccounts.account_type == 'Liability',
        ChartOfAccounts.active == True,
        ChartOfAccounts.id.notin_(named_liability_ids),
    ).all()
    # Same contra handling, in case a contra-liability is ever added.
    other_liabilities = Decimal('0')
    for a in other_liability_accounts:
        balance = _balance_as_of(org_id, a.account_number, as_of_date)
        other_liabilities += -balance if 'contra' in (a.account_subtype or '').lower() else balance

    total_liabilities = per_capita_supreme_payable + per_capita_state_payable + other_liabilities

    net_current_assets = total_current_assets - total_liabilities
    total_net_assets = total_assets - total_liabilities

    return {
        'as_of_date': as_of_date,
        'assets': {
            'current': {
                'financial_secretary_cash_on_hand': fs_cash,
                'checking_account': checking,
                'savings_account': savings,
                'money_market_account': money_market,
                'due_from_members': Decimal('0'),
                'due_from_members_note': ALWAYS_ZERO_NOTE,
                'total_current_assets': total_current_assets,
            },
            'long_term': {
                'certificates_of_deposit': cds,
                'mutual_fund_investments': mutual_funds,
                'other_assets': other_assets,
                'total_long_term_assets': total_long_term_assets,
            },
            'total_assets': total_assets,
        },
        'liabilities': {
            'supreme_council_charges': per_capita_supreme_payable,
            'state_council_charges': per_capita_state_payable,
            'advance_payments': Decimal('0'),
            'advance_payments_note': ALWAYS_ZERO_NOTE,
            'misc_liabilities': other_liabilities,
            'total_liabilities': total_liabilities,
        },
        'net_current_assets': net_current_assets,
        'total_net_assets': total_net_assets,
    }


# ==================== Form1295Submission (narrative / attestation) ====================
#
# The pieces of Form 1295 that are inherently NOT computable from the
# ledger: an explanation for a non-zero "miscellaneous" line, and an
# in-app record of who reviewed and finalized a period's schedules.
# Deliberately never stores a calculated figure -- see
# models.py::Form1295Submission.

def get_submission(org_id, period_start, period_end):
    return Form1295Submission.query.filter_by(
        organization_id=org_id, period_start=period_start, period_end=period_end,
    ).first()


def save_submission_explanations(org_id, period_start, period_end, misc_income_explanation, misc_liabilities_explanation):
    submission = get_submission(org_id, period_start, period_end)
    if not submission:
        submission = Form1295Submission(organization_id=org_id, period_start=period_start, period_end=period_end)
        db.session.add(submission)
    submission.misc_income_explanation = (misc_income_explanation or '').strip() or None
    submission.misc_liabilities_explanation = (misc_liabilities_explanation or '').strip() or None
    db.session.commit()
    return submission


def attest_submission(org_id, period_start, period_end, user_id):
    submission = get_submission(org_id, period_start, period_end)
    if not submission:
        submission = Form1295Submission(organization_id=org_id, period_start=period_start, period_end=period_end)
        db.session.add(submission)
    submission.attested_by_user_id = user_id
    submission.attested_at = datetime.utcnow()
    db.session.commit()
    return submission

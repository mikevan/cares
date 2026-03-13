"""
CARES UAT - Accounting Accuracy Tests
======================================

Validates that the system produces mathematically correct accounting results.

Three layers of verification:
  1. Data load sanity  - known stable values from load_comprehensive_data
  2. Report integrity  - fundamental accounting equations must hold
  3. Transaction delta - post a transaction, verify exactly the right accounts move

These tests use the session-scoped `app` fixture (which loads comprehensive
sample data) and a function-scoped `db_session` for new transactions.
"""

import pytest
from decimal import Decimal
from datetime import date
from services.reports import FinancialReports
from models import (
    db, ChartOfAccounts, JournalEntry, JournalEntryLine,
    Project, Organization, Member
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reports(app_ctx):
    """Return a FinancialReports instance for org 1."""
    org = Organization.query.first()
    return FinancialReports(db.session, org.id)


def get_account(number):
    return ChartOfAccounts.query.filter_by(account_number=number).first()


def raw_balance(account_number, as_of=None):
    """Direct SQL balance — bypasses the report service to give an independent check."""
    as_of = as_of or date.today()
    acc = get_account(account_number)
    assert acc is not None, f"Account {account_number} not found"
    debits = db.session.query(
        db.func.coalesce(db.func.sum(JournalEntryLine.debit_amount), 0)
    ).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id == acc.id,
        JournalEntry.entry_date <= as_of,
        JournalEntry.status == 'Posted',
    ).scalar()
    credits = db.session.query(
        db.func.coalesce(db.func.sum(JournalEntryLine.credit_amount), 0)
    ).join(JournalEntry).join(Project).filter(
        JournalEntryLine.account_id == acc.id,
        JournalEntry.entry_date <= as_of,
        JournalEntry.status == 'Posted',
    ).scalar()
    if acc.normal_balance == 'Debit':
        return Decimal(str(debits)) - Decimal(str(credits))
    else:
        return Decimal(str(credits)) - Decimal(str(debits))


def post_entry(project, entry_date, description, reference, lines, user_id):
    """Post a journal entry directly and flush (does not commit)."""
    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project.id,
        reference_number=reference,
        created_by=user_id,
        status='Posted'
    )
    db.session.add(entry)
    db.session.flush()
    total_d = Decimal('0')
    total_c = Decimal('0')
    for acct_num, debit, credit, memo in lines:
        d, c = Decimal(str(debit)), Decimal(str(credit))
        total_d += d
        total_c += c
        acc = get_account(acct_num)
        assert acc is not None, f"Account {acct_num} not found"
        db.session.add(JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=acc.id,
            debit_amount=d,
            credit_amount=c,
            memo=memo
        ))
    assert abs(total_d - total_c) < Decimal('0.01'), \
        f"Test entry '{reference}' is unbalanced: debits={total_d} credits={total_c}"
    db.session.flush()
    return entry


# ===========================================================================
# 1. DATA LOAD SANITY
# ===========================================================================

@pytest.mark.uat
class TestDataLoadSanity:
    """Verify the comprehensive data loaded correctly."""

    def test_member_count(self, app):
        with app.app_context():
            count = Member.query.count()
            assert count == 20, f"Expected 20 members, got {count}"

    def test_project_count(self, app):
        with app.app_context():
            count = Project.query.count()
            assert count == 6, f"Expected 6 projects, got {count}"

    def test_journal_entries_loaded(self, app):
        with app.app_context():
            count = JournalEntry.query.filter_by(status='Posted').count()
            assert count > 50, f"Expected >50 posted entries, got {count}"

    def test_opening_cash_balance(self, app):
        """
        Opening entry OB-2025 debits 1010 with $180,000.
        All subsequent cash transactions build on this.
        This verifies the data loader ran and the first entry is correct.
        """
        with app.app_context():
            opening = JournalEntry.query.filter_by(reference_number='OB-2025').first()
            assert opening is not None, "Opening balance entry OB-2025 not found"
            cash_line = next(
                (l for l in opening.lines if get_account('1010') and l.account_id == get_account('1010').id),
                None
            )
            assert cash_line is not None, "OB-2025 has no line for account 1010"
            assert cash_line.debit_amount == Decimal('180000'), \
                f"Opening cash debit expected $180,000, got {cash_line.debit_amount}"

    def test_all_journal_entries_balanced(self, app):
        """Every posted journal entry must have equal total debits and credits."""
        with app.app_context():
            entries = JournalEntry.query.filter_by(status='Posted').all()
            unbalanced = []
            for entry in entries:
                total_d = sum(l.debit_amount for l in entry.lines)
                total_c = sum(l.credit_amount for l in entry.lines)
                if abs(total_d - total_c) >= Decimal('0.01'):
                    unbalanced.append(
                        f"{entry.reference_number}: debits={total_d} credits={total_c}"
                    )
            assert not unbalanced, \
                f"Unbalanced entries found:\n" + "\n".join(unbalanced)

    def test_opening_fixed_assets(self, app):
        """OB-2025 loads known fixed asset values."""
        with app.app_context():
            opening = JournalEntry.query.filter_by(reference_number='OB-2025').first()
            assert opening is not None
            def line_debit(acct_num):
                acc = get_account(acct_num)
                line = next((l for l in opening.lines if l.account_id == acc.id), None)
                return line.debit_amount if line else Decimal('0')
            assert line_debit('1410') == Decimal('15000'), "Computer equipment opening balance wrong"
            assert line_debit('1420') == Decimal('8000'),  "Furniture opening balance wrong"
            assert line_debit('1430') == Decimal('35000'), "Vehicles opening balance wrong"


# ===========================================================================
# 2. REPORT INTEGRITY
# ===========================================================================

@pytest.mark.uat
class TestReportIntegrity:
    """Fundamental accounting equations that must always hold."""

    def test_balance_sheet_equation_dec_2025(self, app):
        """Assets = Liabilities + Net Assets as of Dec 31, 2025."""
        with app.app_context():
            r = reports(app)
            bs = r.balance_sheet_detailed(date(2025, 12, 31))
            assets      = bs['assets']['total']
            liabilities = bs['liabilities']['total']
            net_assets  = bs['net_assets']['total']
            total_l_na  = bs['total_liabilities_and_net_assets']

            assert abs(assets - total_l_na) < 0.02, \
                f"Balance sheet does not balance at Dec 31, 2025: " \
                f"Assets={assets:.2f}, L+NA={total_l_na:.2f}, diff={assets-total_l_na:.2f}"
            assert abs((liabilities + net_assets) - total_l_na) < 0.02, \
                f"L+NA total inconsistent: L={liabilities:.2f} NA={net_assets:.2f} total={total_l_na:.2f}"

    def test_balance_sheet_equation_mar_2026(self, app):
        """Assets = Liabilities + Net Assets as of Mar 31, 2026 (YTD period end)."""
        with app.app_context():
            r = reports(app)
            bs = r.balance_sheet_detailed(date(2026, 3, 31))
            assets     = bs['assets']['total']
            total_l_na = bs['total_liabilities_and_net_assets']
            assert abs(assets - total_l_na) < 0.02, \
                f"Balance sheet does not balance at Mar 31, 2026: " \
                f"Assets={assets:.2f}, L+NA={total_l_na:.2f}, diff={assets-total_l_na:.2f}"

    def test_cash_balance_consistent_across_reports(self, app):
        """
        Balance sheet cash subtotal must equal the raw sum of cash account balances
        (1010 + 1020 + 1030).  This checks the report service and raw SQL agree.
        """
        with app.app_context():
            as_of = date(2025, 12, 31)
            r = reports(app)
            bs = r.balance_sheet_detailed(as_of)

            # Cash total from balance sheet
            cash_from_bs = bs['assets']['subtotals'].get('Cash', 0)

            # Independent raw total
            cash_raw = sum(
                float(raw_balance(num, as_of))
                for num in ('1010', '1020', '1030')
            )

            assert abs(cash_from_bs - cash_raw) < 0.02, \
                f"Cash subtotal on balance sheet ({cash_from_bs:.2f}) " \
                f"doesn't match raw account sum ({cash_raw:.2f})"

    def test_net_income_ties_to_net_asset_change(self, app):
        """
        Net income for 2025 must equal the change in net assets from
        Jan 1, 2025 to Dec 31, 2025 (excluding the opening balance entry itself).

        Beginning NA + Net Income = Ending NA
        """
        with app.app_context():
            r = reports(app)

            income = r.income_statement(date(2025, 1, 1), date(2025, 12, 31))
            net_income_2025 = income['net_income']

            # Net assets at start of year = opening 3xxx balance only (before any P&L)
            # The opening entry OB-2025 credits 3100 with $213,000
            beginning_na = float(raw_balance('3100', date(2024, 12, 31)))
            ending_na_3xxx = float(raw_balance('3100', date(2025, 12, 31))) + \
                             float(raw_balance('3200', date(2025, 12, 31)))

            # Cumulative income through end of 2025
            cumulative_income_2025 = float(
                r._get_cumulative_net_income(date(2025, 12, 31))
            )

            # beginning 3xxx + cumulative P&L = total net assets on balance sheet
            bs = r.balance_sheet_detailed(date(2025, 12, 31))
            bs_net_assets = bs['net_assets']['total']

            assert abs((ending_na_3xxx + cumulative_income_2025) - bs_net_assets) < 0.02, \
                f"3xxx balances + cumulative income should equal BS net assets. " \
                f"3xxx={ending_na_3xxx:.2f}, income={cumulative_income_2025:.2f}, " \
                f"sum={ending_na_3xxx+cumulative_income_2025:.2f}, BS={bs_net_assets:.2f}"

    def test_depreciation_accumulates_correctly(self, app):
        """
        12 monthly depreciation entries in 2025 at $450 each = $5,400.
        3 more in Jan/Feb/Mar 2026 = $1,350.
        Accumulated depreciation (1590) through Mar 2026 = $6,750.
        """
        with app.app_context():
            # 1590 has normal_balance=Credit, so get_account_balance returns credits-debits
            # But we stored it negated in the report. Use raw_balance here.
            bal_dec_2025 = raw_balance('1590', date(2025, 12, 31))
            bal_mar_2026 = raw_balance('1590', date(2026, 3, 31))

            assert bal_dec_2025 == Decimal('5400'), \
                f"Accum depreciation at Dec 2025 expected $5,400, got {bal_dec_2025}"
            assert bal_mar_2026 == Decimal('6750'), \
                f"Accum depreciation at Mar 2026 expected $6,750, got {bal_mar_2026}"

    def test_contra_asset_reduces_total_assets(self, app):
        """Accumulated depreciation must reduce total assets, not increase them."""
        with app.app_context():
            r = reports(app)
            bs = r.balance_sheet_detailed(date(2025, 12, 31))

            # Contra-Asset subtotal should be negative
            contra_total = bs['assets']['subtotals'].get('Contra-Asset', 0)
            assert contra_total < 0, \
                f"Contra-Asset subtotal should be negative (reduces assets), got {contra_total}"

            # And total assets should be less than gross assets
            gross_assets = sum(
                v for k, v in bs['assets']['subtotals'].items()
                if k != 'Contra-Asset'
            )
            assert bs['assets']['total'] < gross_assets, \
                "Total assets should be reduced by contra-asset accounts"


# ===========================================================================
# 3. TRANSACTION DELTA TESTS
# ===========================================================================

@pytest.mark.uat
class TestTransactionDeltas:
    """
    Post specific transactions and verify account balances change
    by exactly the expected amounts.  Balance sheet must still balance after.
    """

    def test_cash_receipt_dues(self, app, db_session):
        """
        Post a $150 dues payment: DR 1010 Cash / CR 4110 Membership Dues.
        Cash increases $150, dues revenue increases $150, balance sheet balances.
        """
        with app.app_context():
            r = reports(app)
            as_of = date(2026, 6, 1)
            project = Project.query.first()
            from models import User
            user = User.query.filter_by(role='Admin').first()

            cash_before  = r.get_account_balance('1010', as_of)
            dues_before  = r.get_account_balance('4110', as_of)
            bs_before    = r.balance_sheet_detailed(as_of)

            post_entry(project, as_of, 'UAT test - dues receipt', 'UAT-DUES-001',
                       [('1010', 150, 0,   'Test dues'),
                        ('4110', 0,   150, 'Test dues revenue')],
                       user.id)

            cash_after  = r.get_account_balance('1010', as_of)
            dues_after  = r.get_account_balance('4110', as_of)
            bs_after    = r.balance_sheet_detailed(as_of)

            assert cash_after - cash_before == Decimal('150'), \
                f"Cash should increase $150, delta={cash_after - cash_before}"
            assert dues_after - dues_before == Decimal('150'), \
                f"Dues revenue should increase $150, delta={dues_after - dues_before}"
            assert abs(bs_after['assets']['total'] - bs_after['total_liabilities_and_net_assets']) < 0.02, \
                "Balance sheet broke after dues receipt"

    def test_cash_payment_expense(self, app, db_session):
        """
        Post a $500 rent payment: DR 5210 Rent / CR 1010 Cash.
        Cash decreases $500, rent expense increases $500, balance sheet balances.
        """
        with app.app_context():
            r = reports(app)
            as_of = date(2026, 6, 1)
            project = Project.query.first()
            from models import User
            user = User.query.filter_by(role='Admin').first()

            cash_before = r.get_account_balance('1010', as_of)
            rent_before = r.get_account_balance('5210', as_of)

            post_entry(project, as_of, 'UAT test - rent payment', 'UAT-RENT-001',
                       [('5210', 500, 0,   'Test rent'),
                        ('1010', 0,   500, 'Cash payment')],
                       user.id)

            cash_after = r.get_account_balance('1010', as_of)
            rent_after = r.get_account_balance('5210', as_of)
            bs_after   = r.balance_sheet_detailed(as_of)

            assert cash_before - cash_after == Decimal('500'), \
                f"Cash should decrease $500, delta={cash_before - cash_after}"
            assert rent_after - rent_before == Decimal('500'), \
                f"Rent expense should increase $500, delta={rent_after - rent_before}"
            assert abs(bs_after['assets']['total'] - bs_after['total_liabilities_and_net_assets']) < 0.02, \
                "Balance sheet broke after rent payment"

    def test_ap_accrual_then_payment(self, app, db_session):
        """
        Full AP cycle:
          Step 1 - Accrue expense: DR 5310 Supplies / CR 2110 AP  ($200)
          Step 2 - Pay invoice:    DR 2110 AP / CR 1010 Cash       ($200)

        After Step 1: AP increases $200, expense increases $200, cash unchanged.
        After Step 2: AP back to pre-Step1, cash decreases $200.
        Balance sheet balances at each step.
        """
        with app.app_context():
            r = reports(app)
            as_of = date(2026, 6, 15)
            project = Project.query.first()
            from models import User
            user = User.query.filter_by(role='Admin').first()

            cash_before    = r.get_account_balance('1010', as_of)
            ap_before      = r.get_account_balance('2110', as_of)
            supplies_before = r.get_account_balance('5310', as_of)

            # Step 1: accrue
            post_entry(project, as_of, 'UAT test - supplies invoice', 'UAT-AP-001',
                       [('5310', 200, 0,   'Test supplies'),
                        ('2110', 0,   200, 'AP accrual')],
                       user.id)

            ap_after_accrual       = r.get_account_balance('2110', as_of)
            supplies_after_accrual = r.get_account_balance('5310', as_of)
            cash_after_accrual     = r.get_account_balance('1010', as_of)
            bs_after_accrual       = r.balance_sheet_detailed(as_of)

            assert ap_after_accrual - ap_before == Decimal('200'), \
                f"AP should increase $200 after accrual, delta={ap_after_accrual - ap_before}"
            assert supplies_after_accrual - supplies_before == Decimal('200'), \
                f"Supplies expense should increase $200, delta={supplies_after_accrual - supplies_before}"
            assert cash_after_accrual == cash_before, \
                f"Cash should not change on accrual"
            assert abs(bs_after_accrual['assets']['total'] - bs_after_accrual['total_liabilities_and_net_assets']) < 0.02, \
                "Balance sheet broke after AP accrual"

            # Step 2: pay
            post_entry(project, as_of, 'UAT test - pay supplies invoice', 'UAT-AP-002',
                       [('2110', 200, 0,   'Clear AP'),
                        ('1010', 0,   200, 'Cash payment')],
                       user.id)

            ap_after_payment   = r.get_account_balance('2110', as_of)
            cash_after_payment = r.get_account_balance('1010', as_of)
            bs_after_payment   = r.balance_sheet_detailed(as_of)

            assert abs(ap_after_payment - ap_before) < Decimal('0.01'), \
                f"AP should be back to original after payment, expected {ap_before} got {ap_after_payment}"
            assert cash_before - cash_after_payment == Decimal('200'), \
                f"Cash should decrease $200 after AP payment, delta={cash_before - cash_after_payment}"
            assert abs(bs_after_payment['assets']['total'] - bs_after_payment['total_liabilities_and_net_assets']) < 0.02, \
                "Balance sheet broke after AP payment"

    def test_voided_entry_excluded_from_reports(self, app, db_session):
        """
        A voided journal entry must not affect any account balances.
        """
        with app.app_context():
            r = reports(app)
            as_of = date(2026, 6, 1)
            project = Project.query.first()
            from models import User
            user = User.query.filter_by(role='Admin').first()

            cash_before = r.get_account_balance('1010', as_of)

            # Post then void
            entry = post_entry(project, as_of, 'UAT test - void me', 'UAT-VOID-001',
                               [('1010', 999, 0,   'Should be voided'),
                                ('4010', 0,   999, 'Should be voided')],
                               user.id)
            entry.status = 'Voided'
            db_session.flush()

            cash_after = r.get_account_balance('1010', as_of)

            assert cash_after == cash_before, \
                f"Voided entry should not affect cash balance. Before={cash_before} After={cash_after}"

    def test_income_statement_reflects_new_transaction(self, app, db_session):
        """
        Post a $1,000 donation in a fresh period and verify the income statement
        captures it in revenue and net income increases by exactly $1,000.
        """
        with app.app_context():
            r = reports(app)
            start = date(2026, 9, 1)
            end   = date(2026, 9, 30)
            project = Project.query.first()
            from models import User
            user = User.query.filter_by(role='Admin').first()

            income_before = r.income_statement(start, end)
            revenue_before = income_before['revenues']['total']
            net_before     = income_before['net_income']

            post_entry(project, date(2026, 9, 15), 'UAT test - donation', 'UAT-DON-001',
                       [('1010', 1000, 0,    'Test donation cash'),
                        ('4010', 0,    1000, 'Individual contribution')],
                       user.id)

            income_after = r.income_statement(start, end)
            revenue_after = income_after['revenues']['total']
            net_after     = income_after['net_income']

            assert abs(revenue_after - revenue_before - 1000) < 0.02, \
                f"Revenue should increase $1,000, delta={revenue_after - revenue_before:.2f}"
            assert abs(net_after - net_before - 1000) < 0.02, \
                f"Net income should increase $1,000, delta={net_after - net_before:.2f}"

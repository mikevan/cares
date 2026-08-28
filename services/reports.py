"""
Financial Reports Generator
Generates FASB ASC 958 compliant financial statements
"""
from models import JournalEntry, JournalEntryLine, ChartOfAccounts, Organization, Project
from flask import current_app
from sqlalchemy import func, and_
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict


class FinancialReports:
    """Generate financial reports for nonprofits"""
    
    def __init__(self, db_session, organization_id=1):
        self.session = db_session
        self.org_id = organization_id
    
    def get_account_balance(self, account_number, as_of_date=None):
        """Get balance for a specific account"""
        if as_of_date is None:
            as_of_date = date.today()
        
        account = ChartOfAccounts.query.filter_by(account_number=account_number).first()
        if not account:
            return Decimal('0')
        
        # Sum debits and credits - filter by organization through Project
        debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
            .join(JournalEntry)\
            .join(Project)\
            .filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        
        credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
            .join(JournalEntry)\
            .join(Project)\
            .filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        
        # Calculate balance based on normal balance
        if account.normal_balance == 'Debit':
            return debits - credits
        else:
            return credits - debits
    
    def get_accounts_by_type(self, account_type, as_of_date=None):
        """Get all accounts of a specific type with balances"""
        accounts = ChartOfAccounts.query.filter_by(
            account_type=account_type,
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        result = []
        for account in accounts:
            balance = self.get_account_balance(account.account_number, as_of_date)
            if balance != 0:
                result.append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(balance)
                })
        return result
    
    def balance_sheet(self, as_of_date=None):
        """Generate Statement of Financial Position (Balance Sheet) - Simple version for backward compatibility"""
        if as_of_date is None:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        org = Organization.query.get(self.org_id)
        
        # Assets
        assets = self.get_accounts_by_type('Asset', as_of_date)
        total_assets = sum(a['balance'] for a in assets)
        
        # Liabilities
        liabilities = self.get_accounts_by_type('Liability', as_of_date)
        total_liabilities = sum(l['balance'] for l in liabilities)
        
        # Net Assets
        net_assets = self.get_accounts_by_type('Net Asset', as_of_date)
        total_net_assets = sum(n['balance'] for n in net_assets)
        
        # If no net assets recorded, calculate as difference
        if total_net_assets == 0:
            total_net_assets = total_assets - total_liabilities
        
        return {
            'organization': org.name if org else current_app.config.get('DEFAULT_ORGANIZATION', current_app.config.get('APP_NAME', 'CARES - Community Accounting & Resource Engagement System')),
            'as_of_date': as_of_date.strftime('%B %d, %Y'),
            'assets': {
                'accounts': assets,
                'total': total_assets
            },
            'liabilities': {
                'accounts': liabilities,
                'total': total_liabilities
            },
            'net_assets': {
                'accounts': net_assets,
                'total': total_net_assets
            },
            'total_liabilities_and_net_assets': total_liabilities + total_net_assets
        }
    
    def _get_cumulative_net_income(self, as_of_date):
        """
        Net income (revenue minus expenses) for ALL posted activity from
        inception through as_of_date -- not just a single fiscal period.

        This system never closes Revenue/Expense accounts into Net Assets at
        year end, so their balances keep accumulating across fiscal years.
        balance_sheet_detailed() uses this to add that running, unclosed P&L
        into its Net Assets total, which is what keeps Assets = Liabilities
        + Net Assets true at any as_of_date, not just on the very first day
        of the books.
        """
        if isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()

        revenue_credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
            .join(JournalEntry).join(Project).join(
                ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
            ).filter(
                ChartOfAccounts.account_type == 'Revenue',
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        revenue_debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
            .join(JournalEntry).join(Project).join(
                ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
            ).filter(
                ChartOfAccounts.account_type == 'Revenue',
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        total_revenue = revenue_credits - revenue_debits

        expense_debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
            .join(JournalEntry).join(Project).join(
                ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
            ).filter(
                ChartOfAccounts.account_type == 'Expense',
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        expense_credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
            .join(JournalEntry).join(Project).join(
                ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id
            ).filter(
                ChartOfAccounts.account_type == 'Expense',
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted',
                Project.organization_id == self.org_id
            ).scalar() or Decimal('0')
        total_expenses = expense_debits - expense_credits

        return total_revenue - total_expenses

    def balance_sheet_detailed(self, as_of_date=None):
        """Generate detailed Statement of Financial Position (Balance Sheet) for IRS compliance"""
        if as_of_date is None:
            as_of_date = date.today()
        elif isinstance(as_of_date, str):
            as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
        
        org = Organization.query.get(self.org_id)
        
        # Get all accounts by type
        asset_accounts = ChartOfAccounts.query.filter_by(
            account_type='Asset',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        liability_accounts = ChartOfAccounts.query.filter_by(
            account_type='Liability',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        net_asset_accounts = ChartOfAccounts.query.filter_by(
            account_type='Net Asset',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        # Group assets by subtype
        assets_grouped = defaultdict(list)
        for account in asset_accounts:
            balance = self.get_account_balance(account.account_number, as_of_date)
            if balance != 0:
                subtype = account.account_subtype or 'Other Assets'
                # get_account_balance() returns the balance in the account's
                # own normal-balance direction, so a contra-asset (e.g. 1590
                # Accumulated Depreciation, normal_balance=Credit) comes back
                # as a positive credit balance. Left as-is, it would be added
                # to total assets instead of reducing them. Negate it here so
                # it subtracts, matching how a contra account actually works.
                signed_balance = -balance if 'contra' in subtype.lower() else balance
                assets_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(signed_balance)
                })
        
        # Calculate asset subtotals
        asset_subtotals = {subtype: sum(acc['balance'] for acc in accts) 
                          for subtype, accts in assets_grouped.items()}
        total_assets = sum(asset_subtotals.values())
        
        # Group liabilities by subtype
        liabilities_grouped = defaultdict(list)
        for account in liability_accounts:
            balance = self.get_account_balance(account.account_number, as_of_date)
            if balance != 0:
                subtype = account.account_subtype or 'Other Liabilities'
                # Same contra-account handling as assets above, in case a
                # contra-liability account is ever added to the chart.
                signed_balance = -balance if 'contra' in subtype.lower() else balance
                liabilities_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(signed_balance)
                })
        
        # Calculate liability subtotals
        liability_subtotals = {subtype: sum(acc['balance'] for acc in accts) 
                              for subtype, accts in liabilities_grouped.items()}
        total_liabilities = sum(liability_subtotals.values())
        
        # Group net assets by subtype
        net_assets_grouped = defaultdict(list)
        for account in net_asset_accounts:
            balance = self.get_account_balance(account.account_number, as_of_date)
            if balance != 0:
                subtype = account.account_subtype or 'Unrestricted Net Assets'
                # Same contra-account handling as assets above.
                signed_balance = -balance if 'contra' in subtype.lower() else balance
                net_assets_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(signed_balance)
                })
        
        # Calculate net asset subtotals
        net_asset_subtotals = {subtype: sum(acc['balance'] for acc in accts) 
                              for subtype, accts in net_assets_grouped.items()}

        # This system has no periodic closing-entry step -- Revenue and
        # Expense accounts accumulate indefinitely instead of being closed
        # into a 3xxx Net Asset account at year end. For Assets = Liabilities
        # + Net Assets to hold at any point in time, the balance sheet has to
        # fold in net income earned (or lost) from inception through
        # as_of_date that hasn't been closed into a recorded 3xxx balance yet.
        cumulative_net_income = self._get_cumulative_net_income(as_of_date)
        if cumulative_net_income != 0:
            net_assets_grouped['Current Year Activity'].append({
                'number': 'YTD',
                'name': 'Net Income (Unclosed, Inception-to-Date)',
                'balance': float(cumulative_net_income)
            })
            net_asset_subtotals['Current Year Activity'] = \
                net_asset_subtotals.get('Current Year Activity', 0) + float(cumulative_net_income)

        total_net_assets = sum(net_asset_subtotals.values())
        
        # If no net assets recorded at all (a brand new org with no opening
        # balance entry), fall back to the accounting identity directly.
        if total_net_assets == 0:
            total_net_assets = total_assets - total_liabilities
        
        return {
            'organization': org.name if org else current_app.config.get('DEFAULT_ORGANIZATION', 
                                                                       current_app.config.get('APP_NAME', 'CARES')),
            'as_of_date': as_of_date.strftime('%B %d, %Y'),
            'assets': {
                'groups': dict(assets_grouped),
                'subtotals': asset_subtotals,
                'total': total_assets
            },
            'liabilities': {
                'groups': dict(liabilities_grouped),
                'subtotals': liability_subtotals,
                'total': total_liabilities
            },
            'net_assets': {
                'groups': dict(net_assets_grouped),
                'subtotals': net_asset_subtotals,
                'total': total_net_assets
            },
            'total_liabilities_and_net_assets': total_liabilities + total_net_assets
        }
    
    def income_statement(self, start_date, end_date):
        """Generate Statement of Activities (Income Statement)"""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        org = Organization.query.get(self.org_id)
        
        # Revenue
        revenue_accounts = ChartOfAccounts.query.filter_by(
            account_type='Revenue',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        revenues = []
        for account in revenue_accounts:
            amount = self.session.query(func.sum(JournalEntryLine.credit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            # Subtract debits (returns/adjustments)
            debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            net_amount = amount - debits
            if net_amount != 0:
                revenues.append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'amount': float(net_amount)
                })
        
        total_revenue = sum(r['amount'] for r in revenues)
        
        # Expenses
        expense_accounts = ChartOfAccounts.query.filter_by(
            account_type='Expense',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        expenses = []
        for account in expense_accounts:
            amount = self.session.query(func.sum(JournalEntryLine.debit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            # Subtract credits (reversals)
            credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            net_amount = amount - credits
            if net_amount != 0:
                expenses.append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'amount': float(net_amount)
                })
        
        total_expenses = sum(e['amount'] for e in expenses)
        
        # Net Income
        net_income = total_revenue - total_expenses
        
        return {
            'organization': org.name if org else current_app.config.get('DEFAULT_ORGANIZATION', current_app.config.get('APP_NAME', 'CARES - Community Accounting & Resource Engagement System')),
            'period': f'{start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}',
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'revenues': {
                'accounts': revenues,
                'total': total_revenue
            },
            'expenses': {
                'accounts': expenses,
                'total': total_expenses
            },
            'net_income': net_income
        }
    
    def cash_flow_statement(self, start_date, end_date):
        """Generate Statement of Cash Flows showing actual cash transactions (direct method)"""
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        org = Organization.query.get(self.org_id)

        # Get cash accounts (typically 1010-1030)
        cash_accounts = ChartOfAccounts.query.filter(
            ChartOfAccounts.account_number.between('1010', '1030'),
            ChartOfAccounts.active == True
        ).all()

        cash_account_ids = [acc.id for acc in cash_accounts]

        # Beginning and ending cash balances — used only for the reconciliation rows
        beginning_cash = sum(
            self.get_account_balance(acc.account_number, start_date - timedelta(days=1))
            for acc in cash_accounts
        )
        ending_cash = sum(
            self.get_account_balance(acc.account_number, end_date)
            for acc in cash_accounts
        )

        # Get all posted journal entries for the period
        entries = (
            JournalEntry.query
            .join(Project)
            .filter(
                Project.organization_id == self.org_id,
                JournalEntry.status == 'Posted',
                JournalEntry.entry_date.between(start_date, end_date)
            ).all()
        )

        # Buckets: {project_name: {account_label: Decimal}}
        cash_receipts     = {}  # Operating: revenue credited (cash in)
        cash_payments     = {}  # Operating: expense debited (cash out)
        investing_receipts = {} # Investing: non-cash asset credited (cash in)
        investing_payments = {} # Investing: non-cash asset debited (cash out)
        financing_inflows  = {} # Financing: liability/net-asset credited (cash in)
        financing_outflows = {} # Financing: liability/net-asset debited (cash out)

        def _add(bucket, project_name, account_label, amount):
            bucket.setdefault(project_name, {}).setdefault(account_label, Decimal('0'))
            bucket[project_name][account_label] += amount

        for entry in entries:
            project_name = entry.project.name

            # Only process entries that touch a cash account
            if not any(line.account_id in cash_account_ids for line in entry.lines):
                continue

            for line in entry.lines:
                if line.account_id in cash_account_ids:
                    continue  # skip the cash side itself

                account = line.account
                label   = f"{account.account_number} - {account.account_name}"
                num     = account.account_number

                if num.startswith('4'):
                    # Revenue account
                    if line.credit_amount > 0:
                        _add(cash_receipts, project_name, label, line.credit_amount)
                    if line.debit_amount > 0:  # refund/reversal
                        _add(cash_payments, project_name, label, line.debit_amount)

                elif num.startswith('5'):
                    # Expense account
                    if line.debit_amount > 0:
                        _add(cash_payments, project_name, label, line.debit_amount)
                    if line.credit_amount > 0:  # reversal
                        _add(cash_receipts, project_name, label, line.credit_amount)

                elif num > '1030':
                    # Non-cash asset account (1031 and above)
                    if line.credit_amount > 0:  # asset reduced/sold → cash in
                        _add(investing_receipts, project_name, label, line.credit_amount)
                    if line.debit_amount > 0:   # asset purchased → cash out
                        _add(investing_payments, project_name, label, line.debit_amount)

                elif num.startswith('2') or num.startswith('3'):
                    # Liability or Net Asset
                    if line.credit_amount > 0:  # liability/net-asset increased → cash in
                        _add(financing_inflows, project_name, label, line.credit_amount)
                    if line.debit_amount > 0:   # liability/net-asset decreased → cash out
                        _add(financing_outflows, project_name, label, line.debit_amount)

        def _total(bucket):
            return sum(sum(accts.values()) for accts in bucket.values())

        def _floatify(bucket):
            return {
                proj: {acct: float(amt) for acct, amt in accts.items()}
                for proj, accts in bucket.items()
            }

        total_receipts          = _total(cash_receipts)
        total_payments          = _total(cash_payments)
        total_inv_receipts      = _total(investing_receipts)
        total_inv_payments      = _total(investing_payments)
        total_fin_inflows       = _total(financing_inflows)
        total_fin_outflows      = _total(financing_outflows)

        operating_activities    = float(total_receipts - total_payments)
        investing_activities    = float(total_inv_receipts - total_inv_payments)
        financing_activities    = float(total_fin_inflows - total_fin_outflows)

        # Net change is the sum of all three sections — must reconcile to ending - beginning
        net_change_in_cash      = operating_activities + investing_activities + financing_activities

        return {
            'organization': org.name if org else current_app.config.get(
                'DEFAULT_ORGANIZATION',
                current_app.config.get('APP_NAME', 'CARES - Community Accounting & Resource Engagement System')
            ),
            'period': f'{start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}',

            # Operating
            'cash_receipts':            _floatify(cash_receipts),
            'cash_payments':            _floatify(cash_payments),
            'total_receipts':           float(total_receipts),
            'total_payments':           float(total_payments),
            'operating_activities':     operating_activities,

            # Investing
            'investing_receipts':       _floatify(investing_receipts),
            'investing_payments':       _floatify(investing_payments),
            'total_investing_receipts': float(total_inv_receipts),
            'total_investing_payments': float(total_inv_payments),
            'investing_activities':     investing_activities,

            # Financing
            'financing_inflows':        _floatify(financing_inflows),
            'financing_outflows':       _floatify(financing_outflows),
            'total_financing_inflows':  float(total_fin_inflows),
            'total_financing_outflows': float(total_fin_outflows),
            'financing_activities':     financing_activities,

            # Summary / reconciliation
            'net_change_in_cash':       net_change_in_cash,
            'beginning_cash':           float(beginning_cash),
            'ending_cash':              float(ending_cash),
        }

    def functional_expenses(self, start_date, end_date):
        """Generate Statement of Functional Expenses (FASB ASC 958)
        
        Matrix showing expenses by nature (rows) and function (columns)
        Functions: Program Services, Management & General, Fundraising
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        org = Organization.query.get(self.org_id)
        
        # Get all expense accounts
        expense_accounts = ChartOfAccounts.query.filter_by(
            account_type='Expense',
            active=True
        ).order_by(ChartOfAccounts.account_number).all()
        
        # Initialize expense matrix
        expenses_by_nature = {}
        
        for account in expense_accounts:
            # Calculate total expense for this account
            amount = self.session.query(func.sum(JournalEntryLine.debit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            # Subtract credits (reversals)
            credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
                .join(JournalEntry)\
                .join(Project)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted',
                    Project.organization_id == self.org_id
                ).scalar() or Decimal('0')
            
            net_amount = amount - credits
            
            if net_amount == 0:
                continue
            
            # Determine functional allocation based on account_subtype
            # This is simplified for MVP - ideally would track function per transaction
            program = Decimal('0')
            management = Decimal('0')
            fundraising = Decimal('0')
            
            subtype = account.account_subtype.lower() if account.account_subtype else ''
            
            if 'program' in subtype:
                # Program Services expenses
                program = net_amount
            elif 'fundraising' in subtype:
                # Fundraising expenses
                fundraising = net_amount
            elif 'personnel' in subtype or account.account_number.startswith('50'):
                # Personnel costs - allocate across functions (simplified: 70% program, 20% admin, 10% fundraising)
                program = net_amount * Decimal('0.70')
                management = net_amount * Decimal('0.20')
                fundraising = net_amount * Decimal('0.10')
            else:
                # Default to Management & General (Administrative)
                management = net_amount
            
            expenses_by_nature[account.account_name] = {
                'number': account.account_number,
                'program': float(program),
                'management': float(management),
                'fundraising': float(fundraising),
                'total': float(net_amount)
            }
        
        # Calculate totals by function
        total_program = sum(exp['program'] for exp in expenses_by_nature.values())
        total_management = sum(exp['management'] for exp in expenses_by_nature.values())
        total_fundraising = sum(exp['fundraising'] for exp in expenses_by_nature.values())
        total_expenses = sum(exp['total'] for exp in expenses_by_nature.values())
        
        return {
            'organization': org.name if org else current_app.config.get('DEFAULT_ORGANIZATION', current_app.config.get('APP_NAME', 'CARES - Community Accounting & Resource Engagement System')),
            'period': f'{start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}',
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'expenses': expenses_by_nature,
            'totals': {
                'program': total_program,
                'management': total_management,
                'fundraising': total_fundraising,
                'total': total_expenses
            }
        }

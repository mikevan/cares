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
                assets_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(balance)
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
                liabilities_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(balance)
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
                net_assets_grouped[subtype].append({
                    'number': account.account_number,
                    'name': account.account_name,
                    'balance': float(balance)
                })
        
        # Calculate net asset subtotals
        net_asset_subtotals = {subtype: sum(acc['balance'] for acc in accts) 
                              for subtype, accts in net_assets_grouped.items()}
        total_net_assets = sum(net_asset_subtotals.values())
        
        # If no net assets recorded, calculate as difference
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
        
        # Beginning cash balance
        beginning_cash = sum(
            self.get_account_balance(acc.account_number, start_date - timedelta(days=1))
            for acc in cash_accounts
        )
        
        # Ending cash balance
        ending_cash = sum(
            self.get_account_balance(acc.account_number, end_date)
            for acc in cash_accounts
        )
        
        # Net change in cash
        net_change = ending_cash - beginning_cash
        
        # Get all journal entries for the period
        entries = JournalEntry.query            .join(Project)            .filter(
                Project.organization_id == self.org_id,
                JournalEntry.status == 'Posted',
                JournalEntry.entry_date.between(start_date, end_date)
            ).all()
        
        # Group cash receipts and payments by project and account
        # Look for transactions that affect cash accounts
        cash_receipts = {}  # {project_name: {account_name: amount}}
        cash_payments = {}  # {project_name: {account_name: amount}}
        
        for entry in entries:
            project_name = entry.project.name
            
            # Check if this entry affects a cash account
            has_cash = any(line.account_id in cash_account_ids for line in entry.lines)
            
            if not has_cash:
                continue  # Skip entries that don't affect cash
            
            # Process each line in the entry
            for line in entry.lines:
                # Skip the cash account itself - we want to see what the other side is
                if line.account_id in cash_account_ids:
                    continue
                
                account = line.account
                account_name = f"{account.account_number} - {account.account_name}"
                
                # Cash receipts: revenue accounts (4xxx) that are credited when cash is debited
                if line.credit_amount > 0 and account.account_number.startswith('4'):
                    if project_name not in cash_receipts:
                        cash_receipts[project_name] = {}
                    if account_name not in cash_receipts[project_name]:
                        cash_receipts[project_name][account_name] = Decimal('0')
                    cash_receipts[project_name][account_name] += line.credit_amount
                
                # Cash payments: expense accounts (5xxx) that are debited when cash is credited
                elif line.debit_amount > 0 and account.account_number.startswith('5'):
                    if project_name not in cash_payments:
                        cash_payments[project_name] = {}
                    if account_name not in cash_payments[project_name]:
                        cash_payments[project_name][account_name] = Decimal('0')
                    cash_payments[project_name][account_name] += line.debit_amount
        
        # Calculate totals
        total_receipts = sum(
            sum(accounts.values()) for accounts in cash_receipts.values()
        )
        
        total_payments = sum(
            sum(accounts.values()) for accounts in cash_payments.values()
        )
        
        operating_activities = float(total_receipts - total_payments)
        
        return {
            'organization': org.name if org else current_app.config.get('DEFAULT_ORGANIZATION', current_app.config.get('APP_NAME', 'CARES - Community Accounting & Resource Engagement System')),
            'period': f'{start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}',
            'cash_receipts': {proj: {acct: float(amt) for acct, amt in accounts.items()} for proj, accounts in cash_receipts.items()},
            'cash_payments': {proj: {acct: float(amt) for acct, amt in accounts.items()} for proj, accounts in cash_payments.items()},
            'total_receipts': float(total_receipts),
            'total_payments': float(total_payments),
            'operating_activities': operating_activities,
            'investing_activities': 0.0,
            'financing_activities': 0.0,
            'net_change_in_cash': float(net_change),
            'beginning_cash': float(beginning_cash),
            'ending_cash': float(ending_cash)
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

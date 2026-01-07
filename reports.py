"""
Financial Reports Generator
Generates FASB ASC 958 compliant financial statements
"""
from models import JournalEntry, JournalEntryLine, ChartOfAccounts, Organization
from sqlalchemy import func, and_
from datetime import datetime, date
from decimal import Decimal


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
        
        # Sum debits and credits
        debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
            .join(JournalEntry)\
            .filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted'
            ).scalar() or Decimal('0')
        
        credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
            .join(JournalEntry)\
            .filter(
                JournalEntryLine.account_id == account.id,
                JournalEntry.entry_date <= as_of_date,
                JournalEntry.status == 'Posted'
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
        """Generate Statement of Financial Position (Balance Sheet)"""
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
            'organization': org.name if org else "Knights of Columbus Chapter",
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
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted'
                ).scalar() or Decimal('0')
            
            # Subtract debits (returns/adjustments)
            debits = self.session.query(func.sum(JournalEntryLine.debit_amount))\
                .join(JournalEntry)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted'
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
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted'
                ).scalar() or Decimal('0')
            
            # Subtract credits (reversals)
            credits = self.session.query(func.sum(JournalEntryLine.credit_amount))\
                .join(JournalEntry)\
                .filter(
                    JournalEntryLine.account_id == account.id,
                    JournalEntry.entry_date >= start_date,
                    JournalEntry.entry_date <= end_date,
                    JournalEntry.status == 'Posted'
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
            'organization': org.name if org else "Knights of Columbus Chapter",
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
        """Generate Statement of Cash Flows (simplified)"""
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
        
        # Beginning cash balance
        beginning_cash = sum(
            self.get_account_balance(acc.account_number, start_date - datetime.timedelta(days=1))
            for acc in cash_accounts
        )
        
        # Ending cash balance
        ending_cash = sum(
            self.get_account_balance(acc.account_number, end_date)
            for acc in cash_accounts
        )
        
        # Net change in cash
        net_change = ending_cash - beginning_cash
        
        # Get income statement to derive operating cash flow
        income_stmt = self.income_statement(start_date, end_date)
        operating_cash = income_stmt['net_income']
        
        return {
            'organization': org.name if org else "Knights of Columbus Chapter",
            'period': f'{start_date.strftime("%B %d, %Y")} to {end_date.strftime("%B %d, %Y")}',
            'operating_activities': float(operating_cash),
            'investing_activities': 0.0,
            'financing_activities': 0.0,
            'net_change_in_cash': float(net_change),
            'beginning_cash': float(beginning_cash),
            'ending_cash': float(ending_cash)
        }

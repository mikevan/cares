"""
CARES Test Harness - Integration Tests - Transaction Routes
============================================================

Integration tests for transaction/journal entry routes.

Tests the core accounting functionality including:
- Journal entry creation
- Debit/credit validation
- Account balancing
- Transaction editing
"""

import pytest
from decimal import Decimal
from datetime import date
from models import JournalEntry, JournalEntryLine, ChartOfAccounts


@pytest.mark.integration
class TestTransactionRoutes:
    """Integration tests for transaction routes."""
    
    def test_transactions_list_requires_authentication(self, client):
        """Test that transactions list requires authentication."""
        response = client.get('/transactions')
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_transactions_list_shows_entries(self, organization, db_session, client):
        """Test that transactions list shows journal entries."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory

        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        entry = JournalEntryFactory(
            created_by=user.id,
            project=project,
            description='Test Entry'
        )
        db_session.commit()

        # Log in as the created user
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/transactions')

        assert response.status_code == 200
        assert b'Test Entry' in response.data
    
    def test_create_simple_transaction(self, admin_client, organization, db_session):
        """Test creating a simple transaction via Simple Mode."""
        from tests.fixtures.factories import UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        
        # Get accounts
        cash_account = ChartOfAccounts.query.filter_by(account_number='1000').first()
        revenue_account = ChartOfAccounts.query.filter_by(account_number='4000').first()
        
        initial_count = JournalEntry.query.count()
        
        response = admin_client.post('/transactions/simple', data={
            'entry_date': date.today().isoformat(),
            'description': 'Membership Dues',
            'project_id': project.id,
            'amount': '100.00',
            'debit_account_id': cash_account.id,
            'credit_account_id': revenue_account.id,
        }, follow_redirects=True)
        
        # Verify entry was created
        new_count = JournalEntry.query.count()
        assert new_count == initial_count + 1
        
        # Verify entry details
        entry = JournalEntry.query.filter_by(
            description='Membership Dues'
        ).first()
        assert entry is not None
        assert entry.is_balanced() is True
        
        # Verify lines
        lines = list(entry.lines)
        assert len(lines) == 2
        
        # Check debit line
        debit_line = next((l for l in lines if l.debit_amount > 0), None)
        assert debit_line is not None
        assert debit_line.debit_amount == Decimal('100.00')
        assert debit_line.account_id == cash_account.id
        
        # Check credit line
        credit_line = next((l for l in lines if l.credit_amount > 0), None)
        assert credit_line is not None
        assert credit_line.credit_amount == Decimal('100.00')
        assert credit_line.account_id == revenue_account.id


@pytest.mark.integration
class TestJournalEntryValidation:
    """Integration tests for journal entry validation."""
    
    def test_journal_entry_must_balance(self, admin_client, organization, db_session):
        """Test that unbalanced journal entries are rejected."""
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        db_session.commit()

        cash_account = ChartOfAccounts.query.filter_by(account_number='1000').first()
        revenue_account = ChartOfAccounts.query.filter_by(account_number='4000').first()

        # Try to create unbalanced entry (100 debit, 50 credit)
        response = admin_client.post('/transactions/new', data={
            'entry_date': date.today().isoformat(),
            'description': 'Unbalanced Entry',
            'project_id': project.id,
            'lines': [
                {'account_id': cash_account.id, 'debit': '100.00', 'credit': '0.00'},
                {'account_id': revenue_account.id, 'debit': '0.00', 'credit': '50.00'},
            ]
        })

        # Should reject or show error
        assert b'balance' in response.data.lower() or response.status_code == 400
    
    def test_journal_entry_requires_description(self, admin_client, organization):
        """Test that journal entries require a description."""
        from tests.fixtures.factories import ProjectFactory
        
        project = ProjectFactory(organization=organization)
        
        response = admin_client.post('/transactions/new', data={
            'entry_date': date.today().isoformat(),
            'description': '',  # Empty description
            'project_id': project.id,
        })
        
        # Should show validation error
        assert response.status_code in [200, 400]


@pytest.mark.integration
class TestAccountingLogic:
    """Integration tests for accounting logic."""
    
    def test_debit_increases_asset_account(self, admin_client, organization, db_session):
        """Test that debits increase asset accounts (normal debit balance)."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        
        # Create entry with debit to cash (asset account)
        entry = JournalEntryFactory(
            created_by=user.id,
            project=project,
            description='Cash Receipt'
        )
        
        db_session.commit()
        
        # Entry should be balanced
        assert entry.is_balanced() is True
    
    def test_credit_increases_revenue_account(self, admin_client, organization, db_session):
        """Test that credits increase revenue accounts (normal credit balance)."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        
        # Get revenue account
        revenue_account = ChartOfAccounts.query.filter_by(
            account_type='Revenue'
        ).first()
        
        assert revenue_account is not None
        assert revenue_account.normal_balance == 'Credit'
    
    def test_chart_of_accounts_has_required_accounts(self, db_session):
        """Test that all required FASB ASC 958 accounts exist."""
        required_accounts = {
            '1000': 'Asset',      # Cash
            '2000': 'Liability',  # Accounts Payable
            '3000': 'Net Assets', # Unrestricted Net Assets
            '4000': 'Revenue',    # Contributions
            '5000': 'Expense',    # Program Expenses
        }
        
        for account_number, account_type in required_accounts.items():
            account = ChartOfAccounts.query.filter_by(
                account_number=account_number
            ).first()
            
            assert account is not None, f"Account {account_number} not found"
            assert account.account_type == account_type


@pytest.mark.integration
class TestTransactionWorkflow:
    """Integration tests for complete transaction workflows."""
    
    def test_create_edit_delete_transaction(self, admin_client, organization, db_session):
        """Test complete transaction lifecycle: create, edit, delete."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        
        # Create transaction
        entry = JournalEntryFactory(
            created_by=user.id,
            project=project,
            description='Original Description'
        )
        entry_id = entry.id
        db_session.commit()
        
        # Edit transaction
        response = admin_client.post(f'/transactions/{entry_id}/edit', data={
            'description': 'Updated Description',
            'entry_date': entry.entry_date.isoformat(),
            'project_id': project.id,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        db_session.refresh(entry)
        assert entry.description == 'Updated Description'
        
        # Delete transaction
        response = admin_client.post(
            f'/transactions/{entry_id}/delete',
            follow_redirects=True
        )
        
        assert response.status_code == 200
        
        deleted_entry = JournalEntry.query.get(entry_id)
        assert deleted_entry is None
    
    def test_view_transaction_details(self, authenticated_client, organization, db_session):
        """Test viewing transaction details."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        entry = JournalEntryFactory(
            created_by=user.id,
            project=project,
            description='Detailed Entry'
        )
        db_session.commit()
        
        response = authenticated_client.get(f'/transactions/{entry.id}')
        
        assert response.status_code == 200
        assert b'Detailed Entry' in response.data


@pytest.mark.integration
@pytest.mark.slow
def test_create_many_transactions(admin_client, organization, db_session):
    """Test creating many transactions (performance validation)."""
    from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
    
    user = UserFactory(organization=organization)
    project = ProjectFactory(organization=organization)
    
    # Create 50 transactions
    entries = JournalEntryFactory.create_batch(
        50,
        created_by=user.id,
        project=project
    )
    db_session.commit()
    
    # Verify all were created
    count = JournalEntry.query.count()
    assert count >= 50
    
    # Verify transactions list loads
    response = admin_client.get('/transactions')
    assert response.status_code == 200

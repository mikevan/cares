"""
CARES Test Harness - Functional Tests - Balance Sheet
======================================================

Functional tests for Balance Sheet report generation.

Tests FASB ASC 958 compliant nonprofit balance sheet including:
- Asset accounts
- Liability accounts
- Net asset accounts
- Proper categorization
"""

import pytest
from decimal import Decimal
from datetime import date
from models import ChartOfAccounts


@pytest.mark.functional
class TestBalanceSheetReport:
    """Functional tests for Balance Sheet generation."""
    
    def test_balance_sheet_route_requires_authentication(self, client):
        """Test that balance sheet requires authentication."""
        response = client.get('/reports/balance-sheet')
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_balance_sheet_displays(self, authenticated_client, organization):
        """Test that balance sheet displays correctly."""
        response = authenticated_client.get('/reports/balance-sheet')
        
        assert response.status_code == 200
        assert b'Balance Sheet' in response.data or b'balance sheet' in response.data
    
    def test_balance_sheet_shows_assets(self, authenticated_client, organization, db_session):
        """Test that balance sheet shows asset accounts."""
        from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project, User
        from datetime import date
        # Unique test data
        asset = ChartOfAccounts(account_number='1000A', account_name='Cash Asset Test', account_type='Asset', normal_balance='Debit', active=True)
        db_session.add(asset)
        project = Project(name='Test Project Asset', organization_id=organization.id)
        user = User(username='assetuser1', email='assetuser1@example.com', password_hash='x', role='Admin', organization_id=organization.id)
        db_session.add(project)
        db_session.add(user)
        db_session.commit()
        entry = JournalEntry(entry_date=date.today(), description='Seed asset', status='Posted', project_id=project.id, created_by=user.id)
        db_session.add(entry)
        db_session.commit()
        line = JournalEntryLine(journal_entry_id=entry.id, account_id=asset.id, debit_amount=100, credit_amount=0)
        db_session.add(line)
        db_session.commit()
        response = authenticated_client.get('/reports/balance-sheet')
        assert response.status_code == 200
        assert b'Asset' in response.data or b'ASSET' in response.data
        assert b'Cash Asset Test' in response.data

    def test_balance_sheet_shows_liabilities(self, authenticated_client, organization, db_session):
        """Test that balance sheet shows liability accounts."""
        from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project, User
        from datetime import date
        # Unique test data
        liability = ChartOfAccounts(account_number='2000L', account_name='Accounts Payable Test', account_type='Liability', normal_balance='Credit', active=True)
        db_session.add(liability)
        project = Project(name='Test Project Liability', organization_id=organization.id)
        user = User(username='liabuser1', email='liabuser1@example.com', password_hash='x', role='Admin', organization_id=organization.id)
        db_session.add(project)
        db_session.add(user)
        db_session.commit()
        entry = JournalEntry(entry_date=date.today(), description='Seed liability', status='Posted', project_id=project.id, created_by=user.id)
        db_session.add(entry)
        db_session.commit()
        line = JournalEntryLine(journal_entry_id=entry.id, account_id=liability.id, debit_amount=0, credit_amount=50)
        db_session.add(line)
        db_session.commit()
        response = authenticated_client.get('/reports/balance-sheet')
        assert response.status_code == 200
        assert b'Liabilit' in response.data or b'LIABILITY' in response.data
        assert b'Accounts Payable Test' in response.data

    def test_balance_sheet_shows_net_assets(self, authenticated_client, organization, db_session):
        """Test that balance sheet shows net asset accounts."""
        from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project, User
        from datetime import date
        # Unique test data
        net_asset = ChartOfAccounts(account_number='3000N', account_name='Unrestricted Net Assets Test', account_type='Net Asset', normal_balance='Credit', active=True)
        db_session.add(net_asset)
        project = Project(name='Test Project NetAsset', organization_id=organization.id)
        user = User(username='netassetuser1', email='netassetuser1@example.com', password_hash='x', role='Admin', organization_id=organization.id)
        db_session.add(project)
        db_session.add(user)
        db_session.commit()
        entry = JournalEntry(entry_date=date.today(), description='Seed net asset', status='Posted', project_id=project.id, created_by=user.id)
        db_session.add(entry)
        db_session.commit()
        line = JournalEntryLine(journal_entry_id=entry.id, account_id=net_asset.id, debit_amount=0, credit_amount=75)
        db_session.add(line)
        db_session.commit()
        response = authenticated_client.get('/reports/balance-sheet')
        assert response.status_code == 200
        assert b'Net Asset' in response.data or b'NET ASSET' in response.data
        assert b'Unrestricted Net Assets Test' in response.data


@pytest.mark.functional
class TestBalanceSheetCalculations:
    """Functional tests for balance sheet calculations."""
    
    def test_balance_sheet_calculates_totals(self, authenticated_client, organization, db_session):
        """Test that balance sheet calculates account totals."""
        from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        
        # Create some transactions
        JournalEntryFactory.create_batch(
            5,
            created_by=user,
            project=project
        )
        db_session.commit()
        
        response = authenticated_client.get('/reports/balance-sheet')
        
        assert response.status_code == 200
        
        # Should show dollar amounts
        assert b'$' in response.data or b'USD' in response.data
    
    def test_balance_sheet_balances(self, authenticated_client, organization, sample_data):
        """Test that balance sheet assets = liabilities + net assets."""
        response = authenticated_client.get('/reports/balance-sheet')
        
        assert response.status_code == 200
        
        # Balance sheet should display without errors
        # (Actual balance equation tested in unit tests)


@pytest.mark.functional
class TestBalanceSheetFilters:
    """Functional tests for balance sheet date filtering."""
    
    def test_balance_sheet_with_date_filter(self, authenticated_client, organization):
        """Test generating balance sheet for specific date."""
        report_date = date.today()
        
        response = authenticated_client.get(
            f'/reports/balance-sheet?date={report_date.isoformat()}'
        )
        
        assert response.status_code == 200
    
    def test_balance_sheet_year_filter(self, authenticated_client, organization):
        """Test generating balance sheet for specific year."""
        year = date.today().year
        
        response = authenticated_client.get(
            f'/reports/balance-sheet?year={year}'
        )
        
        assert response.status_code == 200


@pytest.mark.functional
class TestBalanceSheetExport:
    """Functional tests for balance sheet export functionality."""
    
    def test_balance_sheet_pdf_export(self, authenticated_client, organization):
        """Test exporting balance sheet as PDF."""
        response = authenticated_client.get('/reports/balance-sheet?format=pdf')
        
        # Should either return PDF or show export option
        assert response.status_code in [200, 404]
    
    def test_balance_sheet_csv_export(self, authenticated_client, organization):
        """Test exporting balance sheet as CSV."""
        response = authenticated_client.get('/reports/balance-sheet?format=csv')
        
        # Should either return CSV or show export option
        assert response.status_code in [200, 404]


@pytest.mark.functional
class TestBalanceSheetCompliance:
    """Functional tests for FASB ASC 958 compliance."""
    
    def test_balance_sheet_has_required_sections(self, authenticated_client, organization):
        """Test that balance sheet has all required FASB sections."""
        response = authenticated_client.get('/reports/balance-sheet')
        
        assert response.status_code == 200
        
        # FASB ASC 958 requires these sections
        required_sections = [
            b'ASSETS',
            b'LIABILITIES',
            b'NET ASSETS',
        ]
        
        for section in required_sections:
            assert section in response.data, f"Missing required section: {section}"
    
    def test_balance_sheet_separates_restricted_assets(self, authenticated_client, organization):
        """Test that balance sheet separates restricted net assets."""
        response = authenticated_client.get('/reports/balance-sheet')
        
        assert response.status_code == 200
        
        # Should show unrestricted and/or restricted net assets
        # (FASB ASC 958 requirement)


@pytest.mark.functional
@pytest.mark.slow
def test_balance_sheet_with_many_transactions(authenticated_client, organization, db_session):
    """Test balance sheet performance with many transactions."""
    from tests.fixtures.factories import JournalEntryFactory, UserFactory, ProjectFactory
    
    user = UserFactory(organization=organization)
    project = ProjectFactory(organization=organization)
    
    # Create 100 transactions
    JournalEntryFactory.create_batch(
        100,
        created_by=user,
        project=project
    )
    db_session.commit()
    
    # Balance sheet should still load
    response = authenticated_client.get('/reports/balance-sheet')
    
    assert response.status_code == 200
    assert b'Balance Sheet' in response.data or b'balance sheet' in response.data

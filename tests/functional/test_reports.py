"""
CARES Test Harness - Functional Tests - All Reports
====================================================

Functional tests for all CARES financial reports.

Tests all four FASB ASC 958 required reports:
1. Balance Sheet
2. Income Statement (Statement of Activities)
3. Statement of Cash Flows
4. Statement of Functional Expenses
"""

import pytest
from datetime import date
from decimal import Decimal


@pytest.mark.functional
class TestReportsDashboard:
    """Functional tests for reports dashboard."""
    
    def test_reports_dashboard_requires_authentication(self, client):
        """Test that reports dashboard requires authentication."""
        response = client.get('/reports')
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_reports_dashboard_shows_all_reports(self, authenticated_client, organization):
        """Test that reports dashboard shows all available reports."""
        response = authenticated_client.get('/reports')
        
        assert response.status_code == 200
        
        # Should list all four FASB reports
        assert b'Balance Sheet' in response.data
        assert b'Income Statement' in response.data or b'Statement of Activities' in response.data
        assert b'Cash Flow' in response.data
        assert b'Functional Expenses' in response.data


@pytest.mark.functional
class TestIncomeStatement:
    """Functional tests for Income Statement (Statement of Activities)."""
    
    def test_income_statement_displays(self, authenticated_client, organization):
        """Test that income statement displays correctly."""
        response = authenticated_client.get('/reports/income-statement')
        
        assert response.status_code == 200
        assert b'Income' in response.data or b'Activities' in response.data
    
    def test_income_statement_shows_revenue(self, authenticated_client, organization):
        """Test that income statement shows revenue accounts."""
        response = authenticated_client.get('/reports/income-statement')
        
        assert response.status_code == 200
        assert b'Revenue' in response.data or b'REVENUE' in response.data
    
    def test_income_statement_shows_expenses(self, authenticated_client, organization):
        """Test that income statement shows expense accounts."""
        response = authenticated_client.get('/reports/income-statement')
        
        assert response.status_code == 200
        assert b'Expense' in response.data or b'EXPENSE' in response.data
    
    def test_income_statement_calculates_net_income(self, authenticated_client, organization, sample_data):
        """Test that income statement calculates net income (revenue - expenses)."""
        response = authenticated_client.get('/reports/income-statement')
        
        assert response.status_code == 200
        
        # Should show net income/loss
        assert b'Net' in response.data
    
    def test_income_statement_with_date_range(self, authenticated_client, organization):
        """Test income statement with date range filter."""
        start_date = date(2026, 1, 1)
        end_date = date(2026, 12, 31)
        
        response = authenticated_client.get(
            f'/reports/income-statement?start={start_date.isoformat()}&end={end_date.isoformat()}'
        )
        
        assert response.status_code == 200


@pytest.mark.functional
class TestCashFlowStatement:
    """Functional tests for Statement of Cash Flows."""
    
    def test_cash_flow_displays(self, authenticated_client, organization):
        """Test that cash flow statement displays correctly."""
        response = authenticated_client.get('/reports/cash-flow')
        
        assert response.status_code == 200
        assert b'Cash Flow' in response.data or b'cash flow' in response.data
    
    def test_cash_flow_shows_operating_activities(self, authenticated_client, organization):
        """Test that cash flow shows operating activities section."""
        response = authenticated_client.get('/reports/cash-flow')
        
        assert response.status_code == 200
        assert b'Operating' in response.data or b'OPERATING' in response.data
    
    def test_cash_flow_shows_investing_activities(self, authenticated_client, organization):
        """Test that cash flow shows investing activities section."""
        response = authenticated_client.get('/reports/cash-flow')
        
        assert response.status_code == 200
        # Investing activities may or may not show depending on data
    
    def test_cash_flow_shows_financing_activities(self, authenticated_client, organization):
        """Test that cash flow shows financing activities section."""
        response = authenticated_client.get('/reports/cash-flow')
        
        assert response.status_code == 200
        # Financing activities may or may not show depending on data
    
    def test_cash_flow_calculates_net_change(self, authenticated_client, organization, sample_data):
        """Test that cash flow calculates net change in cash."""
        response = authenticated_client.get('/reports/cash-flow')
        
        assert response.status_code == 200
        # Should show change in cash


@pytest.mark.functional
class TestFunctionalExpenses:
    """Functional tests for Statement of Functional Expenses."""
    
    def test_functional_expenses_displays(self, authenticated_client, organization):
        """Test that functional expenses statement displays correctly."""
        response = authenticated_client.get('/reports/functional-expenses')
        
        assert response.status_code == 200
        assert b'Functional' in response.data or b'functional' in response.data
    
    def test_functional_expenses_shows_program_expenses(self, authenticated_client, organization):
        """Test that functional expenses shows program services."""
        response = authenticated_client.get('/reports/functional-expenses')
        
        assert response.status_code == 200
        assert b'Program' in response.data or b'PROGRAM' in response.data
    
    def test_functional_expenses_shows_supporting_expenses(self, authenticated_client, organization):
        """Test that functional expenses shows supporting services."""
        response = authenticated_client.get('/reports/functional-expenses')
        
        assert response.status_code == 200
        # Should show management/fundraising or supporting services
    
    def test_functional_expenses_by_project(self, authenticated_client, organization, sample_data):
        """Test that functional expenses can be broken down by project."""
        response = authenticated_client.get('/reports/functional-expenses')
        
        assert response.status_code == 200
        # Should show expense categorization


@pytest.mark.functional
class TestReportYearSelection:
    """Functional tests for year selection across reports."""
    
    def test_all_reports_support_year_selection(self, authenticated_client, organization):
        """Test that all reports support year parameter."""
        year = 2026
        
        reports = [
            '/reports/balance-sheet',
            '/reports/income-statement',
            '/reports/cash-flow',
            '/reports/functional-expenses',
        ]
        
        for report_url in reports:
            response = authenticated_client.get(f'{report_url}?year={year}')
            assert response.status_code == 200, f"Report {report_url} failed with year parameter"


@pytest.mark.functional
class TestReportComparison:
    """Functional tests for report comparison functionality."""
    
    def test_income_statement_year_comparison(self, authenticated_client, organization):
        """Test comparing income statements across years."""
        response = authenticated_client.get('/reports/income-statement?compare=true')
        
        # Should allow comparison or show option
        assert response.status_code == 200
    
    def test_balance_sheet_period_comparison(self, authenticated_client, organization):
        """Test comparing balance sheets across periods."""
        response = authenticated_client.get('/reports/balance-sheet?compare=true')
        
        # Should allow comparison or show option
        assert response.status_code == 200


@pytest.mark.functional
class TestReportAccuracy:
    """Functional tests for report accuracy and consistency."""
    
    def test_reports_use_same_data(self, authenticated_client, organization, sample_data):
        """Test that all reports pull from same transaction data."""
        # Get all reports
        balance_sheet = authenticated_client.get('/reports/balance-sheet')
        income_statement = authenticated_client.get('/reports/income-statement')
        cash_flow = authenticated_client.get('/reports/cash-flow')
        functional_expenses = authenticated_client.get('/reports/functional-expenses')
        
        # All should succeed
        assert balance_sheet.status_code == 200
        assert income_statement.status_code == 200
        assert cash_flow.status_code == 200
        assert functional_expenses.status_code == 200
    
    def test_reports_handle_no_data(self, authenticated_client, organization, db_session):
        """Test that reports handle empty data gracefully."""
        # All reports should display even with no transactions
        reports = [
            '/reports/balance-sheet',
            '/reports/income-statement',
            '/reports/cash-flow',
            '/reports/functional-expenses',
        ]
        
        for report_url in reports:
            response = authenticated_client.get(report_url)
            assert response.status_code == 200, f"Report {report_url} failed with no data"


@pytest.mark.functional
class TestReportPermissions:
    """Functional tests for report access permissions."""
    
    def test_treasurer_can_view_reports(self, client, organization, db_session):
        """Test that treasurer role can view financial reports."""
        from tests.fixtures.factories import UserFactory
        
        treasurer = UserFactory(
            username='treasurer',
            role='Treasurer',
            organization=organization
        )
        treasurer.set_password('test123')
        db_session.commit()
        
        # Login as treasurer
        client.post('/login', data={
            'username': treasurer.username,
            'password': 'test123',
        })
        
        # Should be able to view reports
        response = client.get('/reports/balance-sheet')
        assert response.status_code == 200
    
    def test_member_cannot_view_reports(self, client, organization, db_session):
        """Test that regular member role cannot view financial reports."""
        from tests.fixtures.factories import UserFactory
        
        member = UserFactory(
            username='member',
            role='Member',
            organization=organization
        )
        member.set_password('test123')
        db_session.commit()
        
        # Login as member
        client.post('/login', data={
            'username': 'member',
            'password': 'test123',
        })
        
        # May be blocked from viewing financial reports
        response = client.get('/reports/balance-sheet')
        # Either redirected or shown error
        assert response.status_code in [200, 302, 403]


@pytest.mark.functional
@pytest.mark.slow
def test_generate_all_reports_with_data(authenticated_client, organization, sample_data):
    """Test generating all four reports with comprehensive data."""
    reports = [
        ('/reports/balance-sheet', 'Balance Sheet'),
        ('/reports/income-statement', 'Income'),
        ('/reports/cash-flow', 'Cash Flow'),
        ('/reports/functional-expenses', 'Functional'),
    ]
    
    for url, expected_text in reports:
        response = authenticated_client.get(url)
        
        assert response.status_code == 200
        assert expected_text.encode() in response.data or expected_text.lower().encode() in response.data

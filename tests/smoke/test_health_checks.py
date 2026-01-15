"""
CARES Test Harness - Smoke Tests - Health Checks
=================================================

Production-safe health checks for CARES system.

These tests verify basic system functionality without modifying data.
Safe to run in production environment.
"""

import pytest
from sqlalchemy import text


@pytest.mark.smoke
class TestDatabaseConnectivity:
    """Smoke tests for database connectivity."""
    
    def test_database_connection(self, app, db_session):
        """Test that database connection is working."""
        # Simple query to verify connection
        result = db_session.execute(text('SELECT 1 as test'))
        row = result.fetchone()
        
        assert row is not None
        assert row[0] == 1
    
    def test_database_tables_exist(self, app, db_session):
        """Test that all required tables exist in database."""
        # Check for key tables
        required_tables = [
            'organizations',
            'users',
            'members',
            'projects',
            'chart_of_accounts',
            'journal_entries',
        ]
        
        for table_name in required_tables:
            result = db_session.execute(text(
                f"SELECT EXISTS (SELECT FROM information_schema.tables "
                f"WHERE table_name = '{table_name}')"
            ))
            exists = result.scalar()
            assert exists is True, f"Table {table_name} does not exist"
    
    def test_chart_of_accounts_initialized(self, app, db_session):
        """Test that Chart of Accounts has been initialized."""
        from models import ChartOfAccounts
        
        account_count = ChartOfAccounts.query.count()
        
        # Should have at least the standard accounts
        assert account_count >= 20, "Chart of Accounts not properly initialized"


@pytest.mark.smoke
class TestRouteAvailability:
    """Smoke tests for route availability."""
    
    def test_login_page_accessible(self, client):
        """Test that login page is accessible."""
        response = client.get('/login')
        
        assert response.status_code == 200
        assert b'login' in response.data.lower()
    
    def test_members_route_exists(self, client):
        """Test that members route exists (even if redirects to login)."""
        response = client.get('/members')
        
        # Either shows page or redirects to login
        assert response.status_code in [200, 302]
    
    def test_transactions_route_exists(self, client):
        """Test that transactions route exists."""
        response = client.get('/transactions')
        
        assert response.status_code in [200, 302]
    
    def test_projects_route_exists(self, client):
        """Test that projects route exists."""
        response = client.get('/projects')
        
        assert response.status_code in [200, 302]
    
    def test_reports_route_exists(self, client):
        """Test that reports route exists."""
        response = client.get('/reports')
        
        assert response.status_code in [200, 302]


@pytest.mark.smoke
class TestAuthenticationSystem:
    """Smoke tests for authentication system."""
    
    def test_unauthenticated_access_redirects(self, client):
        """Test that unauthenticated access to protected routes redirects."""
        protected_routes = [
            '/members',
            '/transactions',
            '/projects',
            '/reports',
        ]
        
        for route in protected_routes:
            response = client.get(route)
            # Should redirect to login
            assert response.status_code == 302
            assert '/login' in response.location
    
    def test_login_form_accepts_post(self, client):
        """Test that login form accepts POST requests."""
        response = client.post('/login', data={
            'username': 'nonexistent',
            'password': 'wrong',
        })
        
        # Should accept POST (even if credentials are wrong)
        assert response.status_code in [200, 302, 401]
    
    def test_authenticated_user_can_access_dashboard(self, authenticated_client):
        """Test that authenticated user can access protected routes."""
        # Test dashboard/index
        response = authenticated_client.get('/')
        
        # Should be accessible
        assert response.status_code == 200


@pytest.mark.smoke
class TestSystemConfiguration:
    """Smoke tests for system configuration."""
    
    def test_flask_app_configured(self, app):
        """Test that Flask app is properly configured."""
        assert app is not None
        assert app.config['TESTING'] is True
    
    def test_database_uri_configured(self, app):
        """Test that database URI is configured."""
        assert 'SQLALCHEMY_DATABASE_URI' in app.config
        assert app.config['SQLALCHEMY_DATABASE_URI'] is not None
    
    def test_secret_key_configured(self, app):
        """Test that secret key is configured."""
        assert 'SECRET_KEY' in app.config
        assert app.config['SECRET_KEY'] is not None
        assert len(app.config['SECRET_KEY']) > 10


@pytest.mark.smoke
def test_basic_read_operations(app, organization, db_session):
    """Test that basic read operations work without errors."""
    from models import User, Member, Project
    
    # These should execute without errors (results don't matter)
    User.query.filter_by(organization=organization).all()
    Member.query.filter_by(organization=organization).all()
    Project.query.filter_by(organization=organization).all()
    
    # If we got here, database reads are working
    assert True


@pytest.mark.smoke
def test_chart_of_accounts_structure(app, db_session):
    """Test that Chart of Accounts has correct structure."""
    from models import ChartOfAccounts
    
    # Get sample accounts
    asset_account = ChartOfAccounts.query.filter_by(
        account_type='Asset'
    ).first()
    revenue_account = ChartOfAccounts.query.filter_by(
        account_type='Revenue'
    ).first()
    
    # Verify accounts exist
    assert asset_account is not None, "No Asset accounts found"
    assert revenue_account is not None, "No Revenue accounts found"
    
    # Verify account structure
    assert asset_account.normal_balance in ['Debit', 'Credit']
    assert revenue_account.normal_balance in ['Debit', 'Credit']

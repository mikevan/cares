import traceback

# Module-level guard to ensure only one PostgresContainer per process
_POSTGRES_CONTAINER_STARTED = False
"""
CARES Test Harness - Core Fixtures
===================================

This is the heart of the CARES Test Harness. It provides:
- PostgreSQL container management via Testcontainers
- Flask application fixture with test configuration
- Database session with automatic transaction rollback
- Test client fixtures (authenticated and unauthenticated)
- Factory Boy integration for test data generation

Fixture Scopes:
- session: Created once for entire test run (container, app)
- function: Created fresh for each test (db_session, client)
- autouse: Automatically used by all tests (factory setup)

Usage:
    def test_something(db_session, client):
        # db_session provides clean database
        # client provides test HTTP client
        pass
"""

import pytest
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from testcontainers.postgres import PostgresContainer
from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import Flask

# Import application modules
from models import db, User, Organization, Member, Project, ChartOfAccounts, JournalEntry
from config import Config

# Import and register Factory Boy factories
from tests.fixtures.factories import (
    OrganizationFactory,
    UserFactory,
    MemberFactory,
    ProjectFactory,
    JournalEntryFactory,
    VendorFactory,
)

from pytest_factoryboy import register

# Register factories as pytest fixtures
register(OrganizationFactory)
register(UserFactory)
register(MemberFactory)
register(ProjectFactory)
register(JournalEntryFactory)


# =============================================================================
# POSTGRESQL CONTAINER FIXTURE (Session-scoped)
# =============================================================================

import time

@pytest.fixture(scope='session')
def postgres_container():
    """
    Create and manage a single PostgreSQL container for the entire test session.
    
    This fixture:
    - Starts ONE container at test session start
    - Provides unique database name and connection URL
    - Stops container at test session end
    - Uses module-level guard to prevent multiple containers
    
    Yields:
        dict: Contains 'container', 'db_name', and 'connection_url' keys
    """
    global _POSTGRES_CONTAINER_STARTED
    
    if _POSTGRES_CONTAINER_STARTED:
        raise RuntimeError("Only one PostgresContainer should be started per test process!")
    
    _POSTGRES_CONTAINER_STARTED = True
    
    print("\n" + "="*80)
    print("Starting PostgreSQL Test Container (Session-scoped)")
    print("="*80)
    
    # Generate unique database name for this test run
    timestamp = int(time.time())
    db_name = f"kofc_test_{timestamp}"
    
    # Create and start container
    postgres = PostgresContainer(
        image="postgres:15-alpine",
        username="postgres",
        password="test123",
        dbname=db_name
    )
    postgres.start()
    
    # Build connection URL
    port = postgres.get_exposed_port(5432)
    conn_url = f"postgresql+psycopg2://{postgres.username}:{postgres.password}@{postgres.get_container_host_ip()}:{port}/{db_name}"
    
    print(f"PostgreSQL Container Started")
    print(f"  Database: {db_name}")
    print(f"  URL: {conn_url}")
    print("="*80 + "\n")
    
    # Yield configuration to tests
    yield {
        'container': postgres,
        'db_name': db_name,
        'connection_url': conn_url
    }
    
    # Cleanup
    print("\n" + "="*80)
    print("Stopping PostgreSQL Test Container")
    print("="*80)
    postgres.stop()
    print("Container stopped and cleaned up")
    print("="*80 + "\n")


# =============================================================================
# FLASK APPLICATION FIXTURE (Session-scoped)
# =============================================================================

@pytest.fixture(scope='session')
def app(postgres_container):
    """
    Create Flask application configured for testing.
    
    Creates application once per test session with:
    - PostgreSQL test database connection
    - Testing mode enabled
    - CSRF protection disabled for easier testing
    - All blueprints registered
    
    Database schema is created once and reused across tests.
    Individual tests use transaction rollback for isolation.
    
    Args:
        postgres_container: PostgreSQL container fixture
        
    Yields:
        Flask: Configured Flask application
    """
    print("Setting up Flask application for testing...")
    
    # Import blueprints
    from blueprints.auth_routes import auth_bp
    from blueprints.member_routes import members_bp
    from blueprints.user_routes import users_bp
    from blueprints.chart_of_accounts import chart_of_accounts_bp
    from blueprints.transaction_routes import transactions_bp
    from blueprints.project_routes import projects_bp
    from blueprints.report_routes import reports_bp
    from blueprints.settings_routes import settings_bp
    from blueprints.ap_routes import ap_bp
    from blueprints.audit_routes import audit_bp
    
    # Create Flask app
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    app.url_map.strict_slashes = False  # Treat /route and /route/ as equivalent, fixes 308/302 redirect issue
    
    # Configure for testing
    # Use the dynamic connection URL from the postgres_container fixture
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': postgres_container['connection_url'],
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'SERVER_NAME': 'localhost:5000',
        'APP_NAME': 'CARES Test',
        'DEFAULT_ORGANIZATION': 'Test Council',
        # Rate limiting is on by default, mirroring production. Flask-Limiter
        # fixes enabled/disabled at limiter.init_app() time (it does not
        # re-read this setting per-request), so toggling it after startup in
        # an individual test has no effect. The autouse reset_rate_limiter
        # fixture below clears counters between tests so the shared 127.0.0.1
        # test-client address doesn't accumulate a quota across the suite.
        'RATELIMIT_ENABLED': True,
    })
    
    # Initialize database
    db.init_app(app)
    
    # Initialize Flask-Login
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    @login_manager.user_loader
    def load_user(user_id):
        from sqlalchemy.orm import joinedload
        user = db.session.query(User).options(
            joinedload(User.organization)
        ).filter_by(id=int(user_id)).first()
        return user

    # Mirror app.py's CSRFProtect wiring so tests exercise the same
    # protection production uses. WTF_CSRF_ENABLED=False above makes this a
    # no-op for every existing test; test_csrf_protection.py flips that
    # config on for the duration of its own tests only.
    from flask_wtf import CSRFProtect
    CSRFProtect(app)

    # Mirror app.py's rate limiter wiring. RATELIMIT_ENABLED=True above, so
    # @limiter.limit(...) on the login route is live for the whole suite;
    # the autouse reset_rate_limiter fixture below clears counters between
    # tests.
    from extensions import limiter
    limiter.init_app(app)

    # Mirror app.py's forced-password-change redirect so tests exercise the
    # same behavior production uses.
    from flask import request, redirect, url_for, flash
    from flask_login import current_user

    @app.before_request
    def require_password_change():
        if not current_user.is_authenticated:
            return None
        if not getattr(current_user, 'must_change_password', False):
            return None
        if request.endpoint in {'users.change_password', 'auth.logout', 'static'}:
            return None
        flash('Please choose a new password before continuing.', 'warning')
        return redirect(url_for('users.change_password', id=current_user.id))

    # Mirror app.py's audit-trail actor-context hooks so tests exercise the
    # same attribution production uses -- see services/audit_context.py.
    from services.audit_context import set_current_actor, clear_current_actor

    @app.before_request
    def apply_audit_actor():
        set_current_actor(current_user.id if current_user.is_authenticated else None)

    @app.teardown_request
    def clear_audit_actor(exc=None):
        clear_current_actor()

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(chart_of_accounts_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(ap_bp)
    app.register_blueprint(audit_bp)

    @app.route('/')
    def index():
        return 'OK', 200
    
    # Create all database tables
    with app.app_context():
        print("Creating database schema...")
        db.create_all()
        print("✓ Database schema created")
        # Initialize Chart of Accounts and default data
        if ChartOfAccounts.query.count() == 0:
            print("Initializing Chart of Accounts...")
            from blueprints.auth_routes import init_database
            init_database(app)
            print(f"✓ Chart of Accounts initialized ({ChartOfAccounts.query.count()} accounts)")

        # A handful of tests (test_transaction_routes.py) and the shared
        # JournalEntryFactory (tests/fixtures/factories.py) look up generic
        # bucket accounts -- '1000' Cash, '2000' Accounts Payable, '3000'
        # Net Assets, '4000' Revenue, '5000' Expense -- rather than a real
        # account number like '1010' or '4010'. Those bucket accounts used
        # to live permanently in init_database()'s own seed list (comments
        # there literally said "add 1000 for tests"), which meant every
        # fresh production/dev deployment got them too. They're test-only
        # convenience, so they're added here instead, only for the test
        # database, and only if a test still references them.
        legacy_test_only_accounts = [
            ('1000', 'Cash', 'Asset', 'Cash', 'Debit'),
            ('2000', 'Accounts Payable', 'Liability', 'Current Liability', 'Credit'),
            ('3000', 'Net Assets', 'Net Assets', 'Unrestricted', 'Credit'),
            ('4000', 'Revenue', 'Revenue', 'Contributions', 'Credit'),
            ('5000', 'Expense', 'Expense', 'General', 'Debit'),
        ]
        for acc_number, acc_name, acc_type, acc_subtype, normal_balance in legacy_test_only_accounts:
            if not ChartOfAccounts.query.filter_by(account_number=acc_number).first():
                db.session.add(ChartOfAccounts(
                    account_number=acc_number,
                    account_name=acc_name,
                    account_type=acc_type,
                    account_subtype=acc_subtype,
                    normal_balance=normal_balance,
                ))
        db.session.commit()

        # Load comprehensive sample data for all tests. target_app is a
        # required (no-default) parameter on main() specifically so this
        # call site can't silently drift back to the real app.py app --
        # that used to happen implicitly and would bind these destructive
        # queries to the real DATABASE_URL (a developer's real local
        # Postgres) instead of this disposable test container.
        with app.app_context():
            import load_comprehensive_data
            load_comprehensive_data.main(target_app=app)
            print(f"✓ Comprehensive sample data loaded (Journal Entries: {JournalEntry.query.count()})")

        # --- SESSION UNIFICATION PATCH ---
        # Always use the test session for db.session in app context
        import flask
        @app.before_request
        def _force_test_session():
            # If pytest has set a test session, use it
            from flask import g
            import pytest
            # Use the session set by db_session fixture if present
            if hasattr(db, '_test_session') and db._test_session is not None:
                db.session = db._test_session

        yield app
        # Cleanup
        print("Cleaning up database...")
        try:
            db.session.remove()  # Remove scoped session
            db.get_engine(app).dispose()  # Close all connections
            db.drop_all()
            print("✓ Database cleaned up")
        except Exception as e:
            print(f"Error during database cleanup: {e}")
# =============================================================================
# ENFORCE TEST SESSION FOR ALL DB OPERATIONS (Auto-use fixture)
# =============================================================================

import pytest


@pytest.fixture(autouse=True, scope='function')
def reset_rate_limiter():
    """
    Clear Flask-Limiter's counters before every test.

    RATELIMIT_ENABLED=True is set on the shared session-scoped app, so the
    login rate limit (and any other @limiter.limit(...) routes) is live for
    the whole suite. Without a reset, requests from earlier tests (which all
    share 127.0.0.1 as the Werkzeug test client's remote address) would
    accumulate against the same quota and could trip a 429 in an unrelated
    test.
    """
    from extensions import limiter
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True, scope='function')
def enforce_test_session(db_session):
    """
    Ensure db.session always points to the test session for the duration of each test.
    This prevents session scoping issues between test data creation and app requests.
    """
    from models import db
    db.session = db_session
    db._test_session = db_session
    yield
    # Do not remove or expire session here; let db_session fixture handle cleanup.


# =============================================================================
# DATABASE SESSION FIXTURE (Function-scoped)
# =============================================================================

@pytest.fixture(scope='function')
def db_session(app):
    """
    Create fresh database session for each test with automatic rollback.
    
    This is the key to test isolation. Each test:
    1. Gets a fresh database connection
    2. Starts a transaction
    3. Runs test code
    4. Rolls back transaction (undoing all changes)
    5. Closes connection
    
    This means tests can modify the database without affecting other tests.
    Very fast (~10-20ms overhead per test).
    
    Args:
        app: Flask application fixture
        
    Yields:
        scoped_session: SQLAlchemy session bound to test transaction
    """
    # WARNING: Dropping/creating tables per test can hang with PostgreSQL and Flask-SQLAlchemy due to open connections.
    # Use transaction/rollback strategy for test isolation.
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        session = scoped_session(
            sessionmaker(
                bind=connection,
                autocommit=False,
                autoflush=False,
            )
        )
        db.session = session
        db._test_session = session
        try:
            yield session
        finally:
            transaction.rollback()
            connection.close()
            session.remove()
            db._test_session = None


# =============================================================================
# FACTORY BOY SETUP (Auto-use fixture)
# =============================================================================

@pytest.fixture(autouse=True)
def setup_factory_session(db_session):
    """
    Automatically bind all Factory Boy factories to test database session.
    
    This fixture runs automatically before every test (autouse=True).
    It ensures all factories use the test database session with proper
    transaction rollback.
    
    Args:
        db_session: Test database session fixture
    """
    # Bind all factories to test session
    for factory_class in [
        OrganizationFactory,
        UserFactory,
        MemberFactory,
        ProjectFactory,
        JournalEntryFactory,
        VendorFactory,
    ]:
        factory_class._meta.sqlalchemy_session = db_session


# =============================================================================
# TEST CLIENT FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def client(app, db_session):
    """
    Create test HTTP client for making requests.
    
    Args:
        app: Flask application
        db_session: Database session (ensures DB is ready)
        
    Returns:
        FlaskClient: Test client for HTTP requests
    """
    return app.test_client()


@pytest.fixture(scope='function')
def authenticated_client(client, organization, user):
    """
    Create test client with authenticated user session.
    
    Automatically creates:
    - Organization (via organization fixture)
    - User (via user fixture)
    - Logs in the user
    
    Args:
        client: Test HTTP client
        organization: Organization fixture (auto-created)
        user: User fixture (auto-created)
        
    Returns:
        FlaskClient: Authenticated test client
    """
    # Commit to ensure user is visible to the test client
    from models import db
    db.session.commit()
    db.session.refresh(user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True
    return client


@pytest.fixture(scope='function')
def admin_client(client, organization):
    """
    Create test client with admin user session.
    
    Args:
        client: Test HTTP client
        organization: Organization fixture
        
    Returns:
        FlaskClient: Authenticated admin test client
    """
    admin_user = UserFactory(
        username='admin',
        email='admin@test.com',
        role='Admin',
        organization=organization
    )
    admin_user.set_password('admin123')
    # Commit to ensure admin user is visible to the test client
    from models import db
    db.session.commit()
    db.session.refresh(admin_user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
    return client


# =============================================================================
# UTILITY FIXTURES
# =============================================================================

@pytest.fixture(scope='function')
def sample_data(db_session, organization):
    """
    Load comprehensive sample data for testing.
    
    Creates realistic test data including:
    - 5 members
    - 3 projects
    - 10 journal entries
    
    Args:
        db_session: Database session
        organization: Organization fixture
        
    Returns:
        dict: Dictionary with all created objects
    """
    # Create members
    members = [
        MemberFactory(organization=organization, name=f"Test Member {i}")
        for i in range(1, 6)
    ]
    
    # Create projects
    projects = [
        ProjectFactory(
            organization=organization,
            name=f"Test Project {i}",
            budget=1000 * i
        )
        for i in range(1, 4)
    ]
    
    # Create some journal entries
    entries = []
    for i in range(10):
        entry = JournalEntryFactory()
        entries.append(entry)
    
    db_session.commit()
    
    return {
        'organization': organization,
        'members': members,
        'projects': projects,
        'entries': entries,
    }


# =============================================================================
# TEST CONFIGURATION
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom settings."""
    # Create reports directory if it doesn't exist
    import os
    reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    print("\n" + "="*80)
    print("CARES TEST HARNESS v1.0")
    print("Community Accounting & Resource Engagement System")
    print("="*80)
    print("Test Configuration:")
    print(f"  - Database: PostgreSQL 15 (Testcontainers)")
    print(f"  - Coverage: Enabled (minimum 70%)")
    print(f"  - Reports: HTML + Terminal + XML")
    print(f"  - Timeout: 30 seconds per test")
    print("="*80 + "\n")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Auto-mark tests based on directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "functional" in str(item.fspath):
            item.add_marker(pytest.mark.functional)
        elif "uat" in str(item.fspath):
            item.add_marker(pytest.mark.uat)
        elif "smoke" in str(item.fspath):
            item.add_marker(pytest.mark.smoke)

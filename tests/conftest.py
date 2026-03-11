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

        # Load comprehensive sample data for all tests
        with app.app_context():
            import load_comprehensive_data
            load_comprehensive_data.main()
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

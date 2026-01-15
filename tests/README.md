# CARES Test Harness

**Community Accounting & Resource Engagement System - Comprehensive Testing Suite**

Version 1.0 | Last Updated: January 2026

---

## 📋 Overview

The CARES Test Harness provides comprehensive automated testing for the CARES nonprofit accounting system. It uses pytest, Testcontainers, and Factory Boy to ensure code quality and prevent regressions.

### Key Features

✅ **PostgreSQL Integration** - Real database testing (no SQLite compatibility issues)  
✅ **Testcontainers** - Automatic Docker container management  
✅ **Factory Boy** - Realistic test data generation  
✅ **Coverage Reporting** - HTML, terminal, and XML reports  
✅ **Multiple Test Types** - Unit, integration, functional, UAT, and smoke tests  
✅ **Production-Safe Smoke Tests** - Can run in production environment  

---

## 🚀 Quick Start

### Prerequisites

1. **Docker** must be running
2. **Python 3.8+** installed
3. **Dependencies** installed

### Installation

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Verify installation
python run_tests.py --help
```

### Run Tests

```bash
# Run all tests
python run_tests.py

# Windows
run_tests.bat

# Linux/Mac
./run_tests.sh
```

---

## 📁 Directory Structure

```
tests/                           # CARES Test Harness
├── conftest.py                  # Core fixtures (PostgreSQL, Flask, DB session)
├── pytest.ini                   # Pytest configuration
├── __init__.py                  # Package marker
│
├── fixtures/                    # Test data factories
│   ├── __init__.py
│   └── factories.py             # Factory Boy definitions
│
├── unit/                        # Unit tests (fast, isolated)
│   ├── __init__.py
│   └── test_models.py           # Example unit test
│
├── integration/                 # Integration tests (routes + DB)
│   ├── __init__.py
│   └── test_member_routes.py    # Example integration test
│
├── functional/                  # Functional tests (end-to-end)
│   └── __init__.py
│
├── uat/                         # User acceptance tests
│   └── __init__.py
│
├── smoke/                       # Smoke tests (PRODUCTION-SAFE)
│   ├── __init__.py
│   └── test_health_checks.py    # Health check tests
│
└── reports/                     # Generated test reports
    └── test_report.html         # HTML test report
```

---

## 🧪 Test Types

### Unit Tests
**Purpose:** Test individual functions/methods in isolation  
**Database:** None (uses mocks)  
**Speed:** Very fast (<1ms per test)  
**Command:** `python run_tests.py --unit`

**Example:**
```python
@pytest.mark.unit
def test_user_password_hashing():
    user = User()
    user.set_password('test123')
    assert user.check_password('test123') is True
```

### Integration Tests
**Purpose:** Test routes and database integration  
**Database:** PostgreSQL (Testcontainers)  
**Speed:** Fast (~10-20ms per test)  
**Command:** `python run_tests.py --integration`

**Example:**
```python
@pytest.mark.integration
def test_create_member(admin_client, organization, db_session):
    response = admin_client.post('/members/new', data={
        'name': 'Test Member',
        'email': 'test@example.com',
    })
    assert response.status_code == 200
    assert Member.query.filter_by(name='Test Member').first() is not None
```

### Functional Tests
**Purpose:** Test complete features end-to-end  
**Database:** PostgreSQL  
**Speed:** Medium (~100-500ms per test)  
**Command:** `python run_tests.py --functional`

### UAT Tests
**Purpose:** Test real-world user scenarios  
**Database:** PostgreSQL  
**Speed:** Slower (~500ms-2s per test)  
**Command:** `python run_tests.py --uat`

### Smoke Tests
**Purpose:** Production health checks  
**Database:** PostgreSQL  
**Speed:** Fast  
**Command:** `python run_tests.py --smoke`  
**⚠️ PRODUCTION-SAFE:** These tests can run in production

---

## 🛠️ Usage

### Basic Commands

```bash
# Run all tests
python run_tests.py

# Run specific test type
python run_tests.py --unit
python run_tests.py --integration
python run_tests.py --smoke

# Run with options
python run_tests.py --fast          # Skip slow tests
python run_tests.py --failfast      # Stop on first failure
python run_tests.py --verbose       # Verbose output
python run_tests.py --coverage      # Open coverage report after tests

# Combine options
python run_tests.py --unit --fast --verbose
```

### Advanced Usage

```bash
# Run specific test file
pytest tests/integration/test_member_routes.py

# Run specific test function
pytest tests/unit/test_models.py::test_user_password_hashing

# Run tests matching pattern
pytest -k "member"

# Re-run only failed tests
python run_tests.py --lf

# Run tests in parallel (faster)
python run_tests.py --parallel
```

---

## 📊 Coverage Reports

The test harness automatically generates coverage reports:

### HTML Report
- **Location:** `htmlcov/index.html`
- **View:** Open in browser
- **Content:** Line-by-line coverage with color coding

### Terminal Report
- **Location:** Console output
- **Content:** Summary with missing lines

### XML Report
- **Location:** `coverage.xml`
- **Use:** CI/CD integration

### Coverage Requirements
- **Minimum:** 70% coverage required
- Tests fail if coverage drops below threshold

---

## 🏗️ Writing Tests

### Using Fixtures

```python
def test_something(db_session, organization, user):
    """
    Fixtures are automatically provided by pytest.
    
    Available fixtures:
    - db_session: Clean database session
    - client: Test HTTP client
    - authenticated_client: Logged-in client
    - admin_client: Admin user client
    - organization: Test organization
    - user: Test user
    - member: Test member
    - project: Test project
    """
    # Your test code here
    pass
```

### Using Factories

```python
def test_with_factories(db_session, organization):
    """Create test data with Factory Boy."""
    from tests.fixtures.factories import MemberFactory
    
    # Create single member
    member = MemberFactory(organization=organization)
    
    # Create with custom values
    member = MemberFactory(
        name='John Doe',
        email='john@example.com',
        organization=organization
    )
    
    # Create batch
    members = MemberFactory.create_batch(10, organization=organization)
```

### Test Markers

```python
@pytest.mark.unit           # Mark as unit test
@pytest.mark.integration    # Mark as integration test
@pytest.mark.slow           # Mark as slow test
@pytest.mark.smoke          # Mark as smoke test
```

---

## 🔧 Configuration

### pytest.ini

Located in `tests/pytest.ini`. Key settings:

```ini
[pytest]
markers =
    unit: Unit tests
    integration: Integration tests
    functional: Functional tests
    uat: UAT tests
    smoke: Smoke tests
    slow: Slow tests

addopts = 
    -v                      # Verbose
    --cov=.                 # Coverage
    --cov-fail-under=70     # Min 70% coverage
```

### conftest.py

Core fixtures defined in `tests/conftest.py`:

- **postgres_container** - PostgreSQL Docker container
- **app** - Flask application
- **db_session** - Database session with rollback
- **client** - Test HTTP client
- **authenticated_client** - Logged-in client
- **admin_client** - Admin user client

---

## 🚢 Deployment

### Production Exclusions

The following are **NOT deployed** to production:

❌ `tests/unit/`  
❌ `tests/integration/`  
❌ `tests/functional/`  
❌ `tests/uat/`  
❌ `tests/fixtures/`  
❌ `tests/conftest.py`  
❌ `run_tests.py`  
❌ `run_tests.bat`  
❌ `run_tests.sh`  
❌ `requirements-dev.txt`  

### Production Inclusions

Only **smoke tests** are deployed:

✅ `tests/smoke/` - Production health checks

---

## 🐛 Troubleshooting

### Docker Not Running

```
ERROR: Docker is not running!
```

**Solution:** Start Docker Desktop and try again.

### Missing Dependencies

```
ERROR: Missing dependency: pytest
```

**Solution:** `pip install -r requirements-dev.txt`

### Container Already Exists

```
ERROR: Container kofc-postgres-test already exists
```

**Solution:** Stop and remove container:
```bash
docker stop kofc-postgres-test
docker rm kofc-postgres-test
```

### Tests Hanging

**Solution:** Use timeout option:
```bash
pytest --timeout=30
```

### Coverage Too Low

```
ERROR: coverage: total of 65% is below required 70%
```

**Solution:** Write more tests or adjust threshold in pytest.ini

---

## 📚 Best Practices

### DO ✅

- Write tests for new features
- Use descriptive test names
- Keep tests independent
- Use factories for test data
- Mock external dependencies
- Test edge cases
- Use appropriate test markers

### DON'T ❌

- Modify production data
- Use hardcoded IDs
- Share state between tests
- Skip cleanup (fixtures handle this)
- Test implementation details
- Write brittle tests

---

## 🤝 Contributing

When adding new tests:

1. Place in appropriate directory (unit/integration/functional/uat/smoke)
2. Use existing factories when possible
3. Add appropriate markers
4. Ensure tests pass before committing
5. Maintain >70% coverage

---

## 📞 Support

For issues or questions:

1. Check this README
2. Review existing tests for examples
3. Check pytest documentation: https://docs.pytest.org
4. Check Factory Boy docs: https://factoryboy.readthedocs.io

---

## 📝 Changelog

### Version 1.0 (January 2026)
- Initial release
- Testcontainers integration
- Factory Boy setup
- Coverage reporting
- Smoke tests for production

---

**Built with ❤️ for the Knights of Columbus**

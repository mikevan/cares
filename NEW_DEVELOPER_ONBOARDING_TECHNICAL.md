# Welcome to CARES! A Friendly and Technical Guide for New Developers and Volunteers

## Table of Contents
1. What is CARES? (And why is it awesome?)
2. The CARES Way: Our Happy Philosophy
3. Meet the Test Harness: Your Superhero Sidekick
4. Let’s Write Your First Test—Step by Step!
5. How the Project is Organized (A Tour!)
6. CARES Coding Habits: Best Practices for Everyone
7. How to Make CARES Work for Your Organization
8. Technical Deep Dive: How CARES Works Under the Hood
9. Oops! Troubleshooting and Getting Help
10. CARES Words: A Simple Glossary
11. You Belong Here! (Final Encouragement)

---

## 1. What is CARES? (And why is it awesome?)
CARES (Community Accounting & Resource Engagement System) is a modern, open-source accounting and resource management platform for nonprofits. It’s built with Python, Flask, SQLAlchemy, and PostgreSQL. CARES is designed to be robust, secure, and easy to customize for any organization’s needs. It supports multi-user authentication, role-based permissions, double-entry accounting, and flexible reporting.

## 2. The CARES Way: Our Happy Philosophy
- **Safety First!** No test or code should ever risk production data. All tests run in isolated environments.
- **Clarity:** Code and tests should be easy to read and understand. We use clear naming and lots of comments.
- **Reliability:** If it works in the test harness, it works everywhere.
- **Community:** We welcome contributions from all backgrounds and skill levels. If you’re here, you’re part of the team.
- **Learning is Fun!** Don’t worry if you’re new. We’ll help you learn as you go.

## 3. Meet the Test Harness: Your Superhero Sidekick
- **Isolated Environment:** Every test runs in a fresh, containerized PostgreSQL database (using Testcontainers). No production or local data is ever touched.
- **Automatic Data Loading:** Sample data is loaded for you—no manual setup required. This is done via scripts like `load_comprehensive_data.py`.
- **Pytest Fixtures:** Use fixtures like `client`, `authenticated_client`, `organization`, and `db_session` to interact with the app and database. These are defined in `tests/conftest.py`.
- **No Side Effects:** Each test is independent. You can run tests in any order, and they’ll always work the same way.
- **Session Management:** SQLAlchemy sessions are managed per test, ensuring no data leaks between tests.
- **Coverage Reporting:** Tests are run with coverage enabled, so you can see how much of the codebase is tested.

### What to Watch Out For
- Never connect to app.db or production data in a test.
- Don’t write tests that depend on other tests.
- Use the fixtures—don’t roll your own setup/teardown.
- Don’t manually commit or rollback the database unless you know what you’re doing.

## 4. Let’s Write Your First Test—Step by Step!
Suppose you want to test that the login page is accessible.

```python
import pytest

@pytest.mark.functional
def test_login_page_accessible(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data
```

**Key Points:**
- The `client` fixture simulates an unauthenticated user using Flask’s test client.
- The test checks for a 200 OK response and verifies the login page content.
- No setup or teardown code is needed—just focus on the behavior you want to verify.

### More Example Fixtures
- `authenticated_client`: A test client that is already logged in as a test user.
- `organization`: A test organization object, created fresh for each test.
- `db_session`: The SQLAlchemy session for direct DB access (useful for setup/teardown in advanced tests).

### Example: Testing a Protected Route
```python
@pytest.mark.functional
def test_balance_sheet_requires_authentication(client):
    response = client.get('/reports/balance-sheet')
    assert response.status_code == 302  # Redirect to login
    assert '/login' in response.location
```

## 5. How the Project is Organized (A Tour!)
- `app.py` – Main Flask application entry point. Sets up the app, config, and blueprints.
- `models.py` – SQLAlchemy models for all core entities (User, Organization, ChartOfAccounts, JournalEntry, etc.).
- `blueprints/` – Modular route handlers (auth_routes.py, report_routes.py, transaction_routes.py, etc.).
- `services/` – Business logic and reporting utilities (e.g., `reports.py`).
- `templates/` – Jinja2 HTML templates for all pages (e.g., `balance_sheet.html`).
- `static/` – CSS, JS, and static assets (e.g., `branding.css`).
- `tests/` – All test code, organized by type:
  - `functional/` – End-to-end tests of user-facing features.
  - `integration/` – Tests that check how different parts of the system work together.
  - `unit/` – Tests for individual functions or classes.
  - `fixtures/` – Factory Boy factories for generating test data.
- `scripts/` – Utility scripts for DB and data management (e.g., `init_db.py`, `load_comprehensive_data.py`).
- `instance/` – Local instance configuration (never checked into version control).

## 6. CARES Coding Habits: Best Practices for Everyone
- **One Test, One Job:** Each test should check just one thing. If you want to check more, write another test!
- **Keep it Simple:** Try not to use “if” or “for” in your tests. If you need them, maybe split the test up.
- **Small Files:** No more than 2 test cases (functions or classes) in a file, unless you really need more (and then explain why at the top).
- **Clear Names:** Name your files and tests so anyone can guess what they do.
- **Use the Helpers:** Always use the fixtures for setup. Don’t try to set up the database yourself.
- **No Sneaky Stuff:** Don’t change the database by hand in your tests. The harness does it for you!
- **Cyclomatic Complexity:** Each test function should have a cyclomatic complexity ≤ 2 (no unnecessary branching or loops).
- **Documentation:** If you break a convention, explain why at the top of the file.
- **Version Control:** Use git for all changes. Commit messages should be clear and descriptive.

## 7. How to Make CARES Work for Your Organization
### Step 1: Define Your Organization’s Structure
- Update or extend `models.py` if your org has unique entities.
- Add new account types or categories in the Chart of Accounts.

### Step 2: Configure Organization Settings
- Use the `settings_routes.py` blueprint to add or modify organization-specific settings.
- Update templates in `templates/` to reflect your org’s branding (logo, colors, etc.).
- Add custom CSS in `static/css/`.

### Step 3: Load Custom Data
- Create a new data loader script in `scripts/` to populate your org’s initial data.
- Use the test harness to verify your data loads and displays correctly.

### Step 4: Add Custom Reports or Features
- Add new blueprints in `blueprints/` for custom routes.
- Add new templates or extend existing ones.
- Write tests for every new feature!

### Step 5: Test Everything
- Use the test harness to run all tests: `pytest --disable-warnings -v`
- Add new tests for your customizations.
- Never skip tests—if something fails, fix it or ask for help.

## 8. Technical Deep Dive: How CARES Works Under the Hood
### Application Stack
- **Python 3.12+**: The main programming language.
- **Flask**: The web framework. Handles routing, requests, and responses.
- **SQLAlchemy**: ORM (Object-Relational Mapper) for database access.
- **PostgreSQL**: The database engine.
- **Jinja2**: Template engine for HTML pages.
- **pytest**: The testing framework.
- **Testcontainers**: Spins up a real PostgreSQL database in Docker for tests.
- **Factory Boy**: Generates fake data for tests.

### How a Test Runs
1. pytest starts and loads all fixtures from `conftest.py`.
2. Testcontainers launches a new PostgreSQL Docker container.
3. The database schema is created from SQLAlchemy models.
4. Sample data is loaded using scripts like `load_comprehensive_data.py`.
5. Each test gets its own app context and database session.
6. Tests use fixtures to interact with the app and database.
7. After tests finish, the database is destroyed—no data is kept.

### Example: Creating a Test User
```python
from tests.fixtures.factories import UserFactory

def test_create_user(db_session):
    user = UserFactory(username='testuser')
    db_session.commit()
    assert user.id is not None
```

### Example: Testing a View with Authentication
```python
@pytest.mark.functional
def test_dashboard_access(authenticated_client):
    response = authenticated_client.get('/')
    assert response.status_code == 200
    assert b'Dashboard' in response.data
```

### How to Add a New Fixture
- Define it in `tests/conftest.py` using the `@pytest.fixture` decorator.
- Use `scope='function'` for most fixtures (fresh for each test).
- Use `scope='session'` for expensive setup (like starting Testcontainers).

### How to Add a New Model
- Add a new class to `models.py` inheriting from `db.Model`.
- Add fields as SQLAlchemy columns.
- Run migrations if needed (see `alembic/`).
- Add factories in `tests/fixtures/factories.py` for test data.

### How to Add a New Route
- Create a new function in the appropriate blueprint (e.g., `blueprints/report_routes.py`).
- Use Flask’s `@app.route` or `@blueprint.route` decorator.
- Add a template in `templates/` if needed.
- Write a test for the new route!

### How to Add a New Test
- Create a new file in the appropriate `tests/` subfolder.
- Use the provided fixtures for setup.
- Keep the test simple and focused.
- Run `pytest` to make sure it passes.

## 9. Oops! Troubleshooting and Getting Help
- **Tests Failing?**
  - Check the test output for clues.
  - Make sure you’re using the right fixtures.
  - Re-read the DEVELOPER_TEST_GUIDE.md and TESTING_ENVIRONMENT.md.
- **Need More Data?**
  - Update your data loader or fixtures.
- **Stuck?**
  - Ask in the project’s chat, open an issue, or reach out to a maintainer.
- **Docker Issues?**
  - Make sure Docker is running and accessible from your environment.
- **Database Connection Errors?**
  - Check that Testcontainers is able to start the PostgreSQL container.
  - Make sure ports are not blocked by a firewall.

## 10. CARES Words: A Simple Glossary
- **Test Harness:** The system that runs tests in a safe, isolated environment.
- **Fixture:** A reusable setup for tests (e.g., a test client or database session).
- **Blueprint:** A modular group of routes in Flask.
- **Chart of Accounts:** The list of all accounts used by the organization.
- **Session:** A SQLAlchemy database session.
- **App Context:** The Flask context for handling requests and DB access.
- **Migration:** A script that updates the database schema.
- **Factory:** A tool for generating fake data for tests.

## 11. You Belong Here! (Final Encouragement)
We’re so glad you’re here! CARES is built by people like you—volunteers who want to help their communities. You don’t have to be a computer whiz. If you can read, ask questions, and try new things, you can help make CARES better. Every test you write, every page you help with, and every question you ask makes a difference. Let’s build something great together!

---
_Last updated: January 14, 2026_

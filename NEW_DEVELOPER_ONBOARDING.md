# Welcome to CARES: The New Developer’s Onboarding Guide

## Table of Contents
1. What is CARES?
2. The CARES Philosophy
3. The Test Harness: Your Best Friend
4. Writing Your First Test
5. Understanding the Project Structure
6. Key Conventions and Best Practices
7. How to Customize CARES for a New Organization
8. Troubleshooting & Where to Get Help
9. Glossary of CARES Terms
10. Final Words of Encouragement

---

## 1. What is CARES?
CARES (Community Accounting & Resource Engagement System) is a modern, open-source accounting and resource management platform for nonprofits. It’s built to be robust, secure, and easy to customize for any organization’s needs.

## 2. The CARES Philosophy
- **Safety First:** No test or code should ever risk production data.
- **Clarity:** Code and tests should be easy to read and understand.
- **Reliability:** If it works in the test harness, it works everywhere.
- **Community:** We welcome contributions from all backgrounds and skill levels.

## 3. The Test Harness: Your Best Friend
- **Isolated Environment:** Every test runs in a fresh, containerized PostgreSQL database. No production or local data is ever touched.
- **Automatic Data Loading:** Sample data is loaded for you—no manual setup required.
- **Pytest Fixtures:** Use fixtures like `client`, `authenticated_client`, `organization`, and `db_session` to interact with the app and database.
- **No Side Effects:** Each test is independent. You can run tests in any order, and they’ll always work the same way.

### What to Watch Out For
- Never connect to app.db or production data in a test.
- Don’t write tests that depend on other tests.
- Use the fixtures—don’t roll your own setup/teardown.

## 4. Writing Your First Test
Let’s walk through a simple example: testing that the login page is accessible.

```python
import pytest

@pytest.mark.functional
def test_login_page_accessible(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Login' in response.data
```

**Key Points:**
- Use the `client` fixture for unauthenticated requests.
- Keep the test focused: one behavior per test.
- No setup or teardown code needed!

## 5. Understanding the Project Structure
- `app.py` – Main application entry point.
- `models.py` – SQLAlchemy models for all core entities.
- `blueprints/` – Modular route handlers (auth, reports, transactions, etc.).
- `services/` – Business logic and reporting utilities.
- `templates/` – Jinja2 HTML templates for all pages.
- `static/` – CSS, JS, and static assets.
- `tests/` – All test code, organized by type (functional, integration, unit, etc.).
- `scripts/` – Utility scripts for DB and data management.

## 6. Key Conventions and Best Practices
- **Test Simplicity:** Cyclomatic complexity ≤ 2 per test function.
- **File Size:** No more than 2 test cases per file unless justified.
- **Naming:** Name files and functions to clearly indicate what they test.
- **Documentation:** If you break a convention, explain why at the top of the file.
- **Use Fixtures:** Always use provided fixtures for setup.
- **No Manual DB Manipulation:** Let the harness handle it.

## 7. How to Customize CARES for a New Organization
CARES is designed to be flexible! Here’s how you can adapt it:

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

## 8. Troubleshooting & Where to Get Help
- **Tests Failing?**
  - Check the test output for clues.
  - Make sure you’re using the right fixtures.
  - Re-read the DEVELOPER_TEST_GUIDE.md and TESTING_ENVIRONMENT.md.
- **Need More Data?**
  - Update your data loader or fixtures.
- **Stuck?**
  - Ask in the project’s chat, open an issue, or reach out to a maintainer.

## 9. Glossary of CARES Terms
- **Test Harness:** The system that runs tests in a safe, isolated environment.
- **Fixture:** A reusable setup for tests (e.g., a test client or database session).
- **Blueprint:** A modular group of routes in Flask.
- **Chart of Accounts:** The list of all accounts used by the organization.
- **Session:** A SQLAlchemy database session.

## 10. Final Words of Encouragement
Welcome to the CARES community! Your contributions matter. Don’t be afraid to ask questions, suggest improvements, or try new things. Every test you write and every feature you build helps nonprofits do more good in the world. Have fun, and happy coding!

---
_Last updated: January 14, 2026_

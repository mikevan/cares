
# CARES Developer’s Guide: Creating Tests with the Test Harness

## Why This Test Harness Exists

The CARES test harness is designed to make testing safe, reliable, and easy for all contributors. Its main goal is to ensure that every test runs in a clean, isolated environment—so you never have to worry about breaking production data, polluting your local database, or having tests interfere with each other. The harness gives you confidence that if a test passes here, it will pass anywhere.

## How the Test Harness Works

- **Isolated Database:** Every test session spins up a fresh, containerized PostgreSQL database using Testcontainers. This means your tests never touch production or app.db, and every run starts from a known state.
- **Automatic Data Loading:** After the schema is created, a minimal but representative set of sample data is loaded. This ensures that all tests have the context they need, without relying on leftover data from previous runs.
- **Pytest Fixtures:** Fixtures manage the app context, database session, and test data lifecycle for you. You don’t need to write setup or teardown code for the database—just use the fixtures provided.
- **No Side Effects:** Each test is fully isolated. There’s no risk of data leaking between tests or persisting after the test run.

## What to Look Out For

- **Fixture Use:** Always use the provided fixtures (`client`, `authenticated_client`, `organization`, `db_session`, etc.) for setup. Don’t try to manually create or tear down the database.
- **Test Simplicity:** Each test should cover only one method or function, and should be as simple as possible. If you find yourself writing `if` statements or loops in a test, consider splitting it up.
- **File Organization:** Limit each test file to 2 test cases (functions or classes). If you need more, document the reason at the top of the file. This keeps tests easy to find and maintain.
- **Naming:** Name your test files and functions to clearly indicate what they test. This helps others (and future you) quickly understand what’s being checked.
- **No Manual DB Manipulation:** Never connect to or modify the database directly in your tests. The harness and fixtures handle everything.

## What to Avoid

- Don’t use or depend on app.db or production data in any test.
- Don’t write tests that depend on the order of execution or on data created by other tests.
- Don’t add unnecessary complexity—keep each test focused and direct.
- Don’t bypass fixtures or the harness for setup/teardown.

## Example: Testing a Protected Route

Suppose you want to verify that the balance sheet page requires authentication. Here’s how you’d do it:

```python
import pytest

@pytest.mark.functional
def test_balance_sheet_requires_authentication(client):
    response = client.get('/reports/balance-sheet')
    assert response.status_code == 302  # Should redirect to login
    assert '/login' in response.location
```

Notice how there’s no setup or teardown code. The `client` fixture gives you an unauthenticated test client, and the harness ensures the database is ready.

## Running Your Tests

- Run all tests: `pytest --disable-warnings -v`
- Run a specific test file: `pytest tests/functional/test_balance_sheet_auth.py`
- Run a specific test: `pytest tests/functional/test_balance_sheet_auth.py::test_balance_sheet_requires_authentication`

## Best Practices

- Keep tests focused and simple—one behavior per test.
- Use fixtures for all setup; never manipulate the DB directly.
- Name everything clearly.
- If you need more than 2 test cases per file, explain why at the top of the file.

---
For more details, see `TESTING_ENVIRONMENT.md`.

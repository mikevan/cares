# CARES Test Environment & Testing Approach

## Overview
This project uses a robust, isolated test harness to ensure reliable, repeatable, and production-safe testing for the Community Accounting & Resource Engagement System (CARES).

## Test Harness Design
- **Isolated Test Database:** All tests run against a dedicated, containerized PostgreSQL database (via Testcontainers), never touching production data or app.db.
- **Automated Data Loading:** Minimal, representative sample data is loaded after schema creation for each test run, ensuring all tests have the required context.
- **Session-Scoped Fixtures:** Pytest fixtures manage app context, database sessions, and test data lifecycle.
- **No Side Effects:** Tests are fully isolated; no persistent state or data leaks between tests.
- **Data-loading helpers take the target app explicitly:** any script that seeds or wipes data (e.g. `load_comprehensive_data.py`) takes the Flask app to run against as a required, no-default argument. A prior version defaulted to importing the real app.py app directly; because Flask-SQLAlchemy resolves `db.session`'s bind from whichever app is current on the context stack, that default silently pointed the test harness's seeding at a developer's real local database instead of the disposable test container -- exactly the kind of production-data leak this file promises never happens. Keep new data-loading helpers to the same no-default-target rule.

## Test Organization & Philosophy
- **One Test per Method/Function:** Each test function covers only one method or function.
- **Cyclomatic Complexity ≤ 2:** Each test function is simple, with at most one decision point (if/else, loop, etc.).
- **Max 2 Test Cases per File:** Each test file contains no more than 2 test cases (functions or classes), unless a clear, documented need exists for more.
- **File Splitting:** If more than 2 test cases are needed, document the reason at the top of the file and split tests into multiple files as appropriate.
- **Clear Naming:** Test files and functions are named to clearly indicate the method/function and behavior being tested.
- **Refactoring Legacy Tests:** Older tests are being refactored to meet these standards for clarity, maintainability, and reliability.

## CI/CD Compatibility
- The test harness is designed to run identically in local and CI environments (e.g., GitHub Actions), provided Docker is available and environment variables are set.
- No production data or configuration is ever touched during CI runs.

## How to Use This Document
If you start a new chat or onboard a new AI assistant, reference this file to:
- Explain the test harness architecture
- Communicate the test writing and organization standards
- Ensure all future test work aligns with these principles

---
_Last updated: January 14, 2026_

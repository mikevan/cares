import pytest
from app import app as flask_app
from models import User, Organization, ChartOfAccounts, Project, JournalEntry

# This test should run first to ensure the test DB is loaded and seeded correctly.
def test_harness_db_load():
    with flask_app.app_context():
        # Check at least one user and one organization
        assert User.query.count() > 0, "No users found in test database. DB load failed."
        assert Organization.query.count() > 0, "No organizations found in test database. DB load failed."
        # Check chart of accounts is complete (at least 20 accounts)
        assert ChartOfAccounts.query.count() >= 20, "Chart of accounts incomplete. DB load failed."
        # Check at least one project and one journal entry (sample data)
        assert Project.query.count() > 0, "No projects found. Sample data load failed."
        assert JournalEntry.query.count() > 0, "No journal entries found. Sample data load failed."

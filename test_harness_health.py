import pytest
from models import User, Organization, ChartOfAccounts, Project, JournalEntry

# Uses the session-scoped app fixture from conftest so it runs against
# the testcontainer DB with committed sample data, not a rolled-back transaction.
def test_harness_db_load(app):
    with app.app_context():
        assert User.query.count() > 0, "No users found in test database. DB load failed."
        assert Organization.query.count() > 0, "No organizations found in test database. DB load failed."
        assert ChartOfAccounts.query.count() >= 20, "Chart of accounts incomplete. DB load failed."
        assert Project.query.count() > 0, "No projects found. Sample data load failed."
        assert JournalEntry.query.count() > 0, "No journal entries found. Sample data load failed."

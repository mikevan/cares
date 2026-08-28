import pytest
from models import User, Organization, ChartOfAccounts, Project, JournalEntry

# This test should run first to ensure the test DB is loaded and seeded correctly.
#
# NOTE: this must use the `app` *fixture* (the isolated test-container app),
# not `from app import app` (the real dev/production app). Importing the
# real app here always queried the developer's real local database rather
# than the test database -- it happened to look like it worked only because
# of a since-fixed bug in load_comprehensive_data.main() that was also
# writing demo data into the real database as a side effect of running the
# test suite. See load_comprehensive_data.py's target_app parameter.
def test_harness_db_load(app):
    with app.app_context():
        # Check at least one user and one organization
        assert User.query.count() > 0, "No users found in test database. DB load failed."
        assert Organization.query.count() > 0, "No organizations found in test database. DB load failed."
        # Check chart of accounts is complete (at least 20 accounts)
        assert ChartOfAccounts.query.count() >= 20, "Chart of accounts incomplete. DB load failed."
        # Check at least one project and one journal entry (sample data)
        assert Project.query.count() > 0, "No projects found. Sample data load failed."
        assert JournalEntry.query.count() > 0, "No journal entries found. Sample data load failed."

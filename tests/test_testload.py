import pytest
from app import app as flask_app

# This test checks if the test database is loaded and seeded with at least one user and one organization.
def test_testload_works():
    with flask_app.app_context():
        from models import User, Organization
        user_count = User.query.count()
        org_count = Organization.query.count()
        # If test data is loaded, there should be at least one user and one organization
        assert user_count > 0, f"Expected at least 1 user, found {user_count}"
        assert org_count > 0, f"Expected at least 1 organization, found {org_count}"

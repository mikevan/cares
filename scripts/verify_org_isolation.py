"""
One-time helper: sets up a throwaway second organization + user so you can
manually verify the cross-tenant authorization fix (project view/edit,
transaction view, journal entry void).

Run locally:
    python scripts/verify_org_isolation.py

Safe to re-run — reuses the test org/user if they already exist. Delete the
"ISOLATION-TEST ORG (delete me)" organization and its user when you're done
testing (Settings won't do it — this script's cleanup instructions are at
the bottom of its output, or just do it via psql / a DB client).
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from models import db, Organization, User, Project, JournalEntry

TEST_ORG_NAME = "ISOLATION-TEST ORG (delete me)"
TEST_USERNAME = "isolation_test"
TEST_PASSWORD = "IsolationTest123!"

with app.app_context():
    real_org = Organization.query.filter(Organization.name != TEST_ORG_NAME).first()
    if not real_org:
        print("No real organization found — run the app once first so it seeds one.")
        sys.exit(1)

    sample_project = Project.query.filter_by(organization_id=real_org.id).first()
    sample_entry = (
        JournalEntry.query.join(Project)
        .filter(Project.organization_id == real_org.id)
        .first()
    )

    test_org = Organization.query.filter_by(name=TEST_ORG_NAME).first()
    if not test_org:
        test_org = Organization(name=TEST_ORG_NAME, org_type='Chapter', fiscal_year_start=1)
        db.session.add(test_org)
        db.session.commit()
        print(f"Created test organization (id={test_org.id})")
    else:
        print(f"Test organization already exists (id={test_org.id})")

    test_user = User.query.filter_by(username=TEST_USERNAME).first()
    if not test_user:
        test_user = User(
            username=TEST_USERNAME,
            email='isolation_test@example.com',
            role='Admin',
            organization_id=test_org.id,
            active=True,
        )
        test_user.set_password(TEST_PASSWORD)
        db.session.add(test_user)
        db.session.commit()
        print(f"Created test user (id={test_user.id})")
    else:
        print("Test user already exists")

    print("\n" + "=" * 60)
    print("MANUAL VERIFICATION STEPS")
    print("=" * 60)
    print(f"1. Log out of admin, log in as:")
    print(f"   username: {TEST_USERNAME}")
    print(f"   password: {TEST_PASSWORD}")
    print(f"   (this user belongs to '{TEST_ORG_NAME}', NOT your real org)")
    print()
    if sample_project:
        print(f"2. Try:  /projects/{sample_project.id}/view")
        print(f"         /projects/{sample_project.id}/edit")
        print(f"   Expect: 404 Not Found (before the fix, this showed/edited")
        print(f"   your real org's project \"{sample_project.name}\").")
    else:
        print("2. (No project found in your real org to test against.)")
    print()
    if sample_entry:
        print(f"3. Try:  /transactions/{sample_entry.id}")
        print(f"   Expect: 404 Not Found (before the fix, this showed the")
        print(f"   real transaction's amounts and memo).")
    else:
        print("3. (No journal entry found in your real org to test against.)")
    print()
    print("4. When done, delete the test data:")
    print(f"   DELETE FROM users WHERE username = '{TEST_USERNAME}';")
    print(f"   DELETE FROM organizations WHERE name = '{TEST_ORG_NAME}';")
    print("=" * 60)

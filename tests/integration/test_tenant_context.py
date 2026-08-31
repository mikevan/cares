"""
CARES Test Harness - Integration Tests - Tenant context
====================================================================

Guards the plumbing that carries the acting organization from a Flask
request into the Postgres session settings every row-level security policy
reads (services/tenancy.py -> rls_schema.current_org()).

WHY THIS FILE EXISTS
--------------------
A deployment served its first ever request as the restricted runtime role
and showed an entirely empty application: zero members, zero projects, zero
transactions, while the same database answered 38 members to a query that
set the session settings by hand. Nothing errored. RLS was working
perfectly; the request simply never told the database which organization it
was acting for, so every policy compared against NULL and returned nothing.

The cause was ordering. app.py registers require_password_change() before
apply_tenant_context(), and its first statement reads current_user -- which
fires Flask-Login's user loader, which runs the request's first query, which
begins the transaction. services/tenancy.py pushes the settings on
after_begin, so they were pushed EMPTY, and after_begin does not fire again
when the organization changes mid-transaction. The fix is a commit inside
apply_tenant_context(), closing that transaction so the settings land on the
next one.

Two independent reasons the existing suite could not catch it:

  1. Tests connect as the table OWNER, and an owner is exempt from its own
     tables' policies (they are ENABLE'd, not FORCE'd -- see rls_schema.py).
     Missing tenant context changes no result.
  2. tests/conftest.py builds its own Flask app and mirrors app.py's request
     hooks by hand. It mirrored require_password_change and the audit actor
     but never mirrored apply_tenant_context, so no test had ever executed
     it.

Both are addressed: conftest now mirrors the hook, and the tests below
assert what the DATABASE sees rather than what the contextvar holds -- a
contextvar assertion would have passed throughout the outage.
"""
import pytest
from flask_login import login_user
from sqlalchemy import text

from models import db


def _run_before_request_handlers(app):
    """Run the app's before_request chain in registration order.

    This is what Flask itself does. Calling the handlers directly, rather
    than issuing a request through the test client, lets the assertions
    below inspect the session settings from inside the same transaction the
    view functions would have used.
    """
    for handler in app.before_request_funcs.get(None, []):
        handler()


def _setting(name):
    return db.session.execute(
        text("SELECT current_setting(:name, true)"), {'name': name}
    ).scalar()


@pytest.mark.integration
class TestTenantContextReachesTheDatabase:

    def test_organization_setting_is_set_for_an_authenticated_request(
            self, app, db_session, organization, user):
        """The setting every RLS policy reads must be populated by the time
        a view runs -- not merely present in a Python contextvar."""
        db_session.commit()

        with app.test_request_context('/'):
            login_user(user)
            # Reproduce production's ordering explicitly: something reads
            # the database before the tenant hook runs. In production that
            # is require_password_change touching current_user; here the
            # login_user() above has already done it, and this makes the
            # dependency impossible to remove by accident.
            db.session.execute(text('SELECT 1'))

            _run_before_request_handlers(app)

            assert _setting('app.current_organization_id') == str(user.organization_id), (
                "the database cannot see the acting organization, so every "
                "RLS policy would compare against NULL and return zero rows"
            )

    def test_read_scope_setting_includes_the_acting_organization(
            self, app, db_session, organization, user):
        """Scope drives the USING clause. Empty scope means every protected
        table returns nothing, which reads as an empty application."""
        db_session.commit()

        with app.test_request_context('/'):
            login_user(user)
            db.session.execute(text('SELECT 1'))
            _run_before_request_handlers(app)

            scope = _setting('app.current_organization_scope')

        assert scope, "read scope was never pushed to the database"
        assert str(user.organization_id) in scope.split(','), (
            f"acting organization {user.organization_id} missing from scope {scope!r}"
        )

    def test_anonymous_request_declares_no_organization(self, app, db_session):
        """Failing closed is the design: no context must mean no rows, never
        every organization's rows. Asserts the settings stay empty rather
        than inheriting whoever the worker thread served last."""
        with app.test_request_context('/'):
            _run_before_request_handlers(app)
            assert _setting('app.current_organization_id') in ('', None)

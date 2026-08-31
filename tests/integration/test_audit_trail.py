"""
CARES Test Harness - Integration Tests - Audit Trail
====================================================================

Covers audit_schema.py's trigger function, services/audit_context.py's
actor-attribution plumbing, models.AuditLog, and blueprints/audit_routes.py
(the Trustee Audit Report). See models.py::AuditLog for the full design
rationale (why a DB trigger, why hash-chained, why a restricted role).
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

from models import db, AuditLog
from audit_schema import grant_restricted_runtime_role
from tests.fixtures.factories import UserFactory


@pytest.mark.integration
class TestTriggerCapturesChanges:
    """The Postgres trigger itself -- not the app -- is what writes these
    rows, so these tests exercise it directly through ordinary ORM
    writes rather than mocking anything."""

    def test_insert_is_captured_with_full_new_data(self, db_session, organization):
        user = UserFactory(organization=organization, username='audit_insert_target')
        db_session.commit()

        entry = AuditLog.query.filter_by(table_name='users', row_id=user.id, operation='INSERT').first()
        assert entry is not None
        assert entry.old_data is None
        assert entry.new_data['username'] == user.username
        assert entry.row_hash is not None
        assert entry.changed_at is not None

    def test_update_is_captured_with_old_and_new_data(self, db_session, organization):
        user = UserFactory(organization=organization, role='Member')
        db_session.commit()

        user.role = 'Treasurer'
        db_session.commit()

        entry = AuditLog.query.filter_by(
            table_name='users', row_id=user.id, operation='UPDATE'
        ).order_by(AuditLog.id.desc()).first()
        assert entry is not None
        assert entry.old_data['role'] == 'Member'
        assert entry.new_data['role'] == 'Treasurer'

    def test_delete_is_captured_with_full_old_data(self, db_session, organization):
        user = UserFactory(organization=organization)
        db_session.commit()
        user_id = user.id
        username = user.username

        db_session.delete(user)
        db_session.commit()

        entry = AuditLog.query.filter_by(table_name='users', row_id=user_id, operation='DELETE').first()
        assert entry is not None
        assert entry.old_data['username'] == username
        assert entry.new_data is None

    def test_a_change_made_with_no_actor_context_is_recorded_with_a_null_actor(self, db_session, organization):
        """
        No Flask request is in progress in this test, so
        services/audit_context.py's contextvar is at its default (None) --
        exactly like a raw SQL statement run outside the application
        entirely. That's the scenario a real trustee audit needs to be
        able to spot: a change nobody's login shows responsibility for.
        """
        user = UserFactory(organization=organization, username='audit_null_actor_target')
        db_session.commit()

        entry = AuditLog.query.filter_by(table_name='users', row_id=user.id, operation='INSERT').first()
        assert entry is not None
        assert entry.changed_by_user_id is None


@pytest.mark.integration
class TestActorAttribution:
    """Verifies services/audit_context.py actually threads the logged-in
    user through to the trigger, via a real HTTP request rather than
    calling set_current_actor() directly."""

    def test_logging_in_attributes_the_last_login_update_to_the_user_who_logged_in(self, client, organization, db_session):
        user = UserFactory(organization=organization)
        user.set_password('CorrectHorseBattery1')
        db_session.commit()
        # UserFactory silently appends a random suffix to any explicitly
        # given username (see tests/fixtures/factories.py) -- read back the
        # real value rather than assuming what was passed in survived.
        real_username = user.username

        response = client.post('/login', data={'username': real_username, 'password': 'CorrectHorseBattery1'})
        assert response.status_code in (302, 200)

        entry = AuditLog.query.filter_by(
            table_name='users', row_id=user.id, operation='UPDATE'
        ).order_by(AuditLog.id.desc()).first()
        assert entry is not None
        assert entry.changed_by_user_id == user.id


@pytest.mark.integration
class TestRestrictedRuntimeRole:
    """
    Proves the actual security property this whole design exists for:
    the role the application connects as in production can write new
    audit rows but cannot edit or delete existing ones -- not because the
    application chooses not to, but because Postgres refuses.
    """

    def test_restricted_role_can_write_business_data_but_not_touch_audit_log(self, app):
        # Deliberately does NOT take the `organization` (or `db_session`)
        # fixture. `organization` is created via factory_boy with
        # sqlalchemy_session_persistence='flush' -- a flush, not a commit
        # -- so it leaves an INSERT into `organizations` sitting inside
        # db_session's still-open outer transaction for the rest of the
        # test. That INSERT already fired the audit trigger and is
        # holding cares_audit_log_chain's advisory lock, which isn't
        # released until db_session's transaction ends at teardown
        # (rollback). This test's own INSERT below, issued through a
        # completely separate connection/role, needs that same lock --
        # so pulling in `organization` here self-deadlocks: this test
        # can't finish until teardown, and teardown can't run until this
        # test finishes. Everything this test needs it creates itself.
        with app.app_context():
            db_url = db.engine.url
            with db.engine.begin() as connection:
                grant_restricted_runtime_role(connection, 'test_cares_restricted_role', 'test_pw_x7q9')

            restricted_engine = create_engine(db_url.set(
                username='test_cares_restricted_role', password='test_pw_x7q9'
            ))
            try:
                with restricted_engine.begin() as conn:
                    conn.execute(text(
                        "INSERT INTO organizations (name, org_type) VALUES ('Restricted Role Test Org', 'Chapter')"
                    ))

                with restricted_engine.connect() as conn:
                    for statement in [
                        "DELETE FROM audit_log",
                        "UPDATE audit_log SET operation = 'INSERT'",
                        "TRUNCATE audit_log",
                    ]:
                        with pytest.raises(Exception):
                            conn.execute(text(statement))
                            conn.commit()
                        conn.rollback()
            finally:
                restricted_engine.dispose()

            entry = AuditLog.query.filter_by(table_name='organizations', operation='INSERT').filter(
                AuditLog.new_data['name'].astext == 'Restricted Role Test Org'
            ).first()
            assert entry is not None, "the restricted role's own insert should still be captured"


@pytest.mark.integration
class TestChainVerification:

    def test_freshly_written_rows_verify_as_intact(self, db_session, organization):
        """Verify through the application's own verifier, not a copy of it.

        This test previously inlined its own recomputation of the hash
        payload and its own chain-link check. Both went stale when
        audit_trigger_fn() moved to per-organization chains: the payload
        gained an organization_id segment and prev_hash began being read
        from the writing row's own organization partition. A second copy of
        a calculation is how the contra-asset bug got reintroduced in
        schedule_c(); calling verify_chain() means there is exactly one
        definition of what "intact" means, and it is the one the Trustee
        Audit Report and the signed PDF both read from.
        """
        # Imported inside the test deliberately: no other test module
        # imports a blueprint at module scope, and this keeps collection
        # of this file independent of blueprint import order.
        from blueprints.audit_routes import verify_chain

        UserFactory(organization=organization)
        db_session.commit()

        result = verify_chain()
        assert result['total_rows'] > 0, (
            'the factory write above should have produced audit rows: %r' % (result,))
        assert result['intact'], (
            'freshly written rows failed verification: %r' % (result,))


@pytest.mark.integration
class TestTrusteeAuditReport:

    def test_non_admin_cannot_view_the_audit_log(self, authenticated_client):
        # Not follow_redirects=True + checking the landing page's body: the
        # test harness's own `index` route (tests/conftest.py) is a bare
        # stub -- `return 'OK', 200` -- that exists only to give routes
        # somewhere to redirect to, and never renders flashed messages (or
        # anything else). That's true regardless of which admin-gated
        # blueprint is under test, so asserting against the post-redirect
        # body would never see the flash no matter how _require_admin()
        # behaved. Assert the two things that actually matter instead:
        # the request gets redirected away (the report itself never
        # renders) and flash() actually queued the denial message.
        response = authenticated_client.get('/audit/log')
        assert response.status_code == 302

        with authenticated_client.session_transaction() as sess:
            flashed_messages = [message for _category, message in sess.get('_flashes', [])]
        assert any('Permission denied' in message for message in flashed_messages)

    def test_admin_can_view_the_audit_log_and_see_a_recent_change(self, admin_client, organization, db_session):
        UserFactory(organization=organization, username='visible_in_audit_report')
        db_session.commit()

        response = admin_client.get('/audit/log')
        assert response.status_code == 200
        assert b'users' in response.data

    def test_verify_route_reports_an_intact_chain(self, admin_client, organization, db_session):
        UserFactory(organization=organization)
        db_session.commit()

        response = admin_client.post('/audit/verify', follow_redirects=True)
        assert response.status_code == 200
        assert b'chain is intact' in response.data

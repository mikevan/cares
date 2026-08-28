"""
CARES Test Harness - Integration Tests - Auth Hardening
==========================================================

Covers the §4 auth-hardening fixes: forcing a real password change off the
seeded admin123 default, and rate limiting on /login. (SECRET_KEY/
DATABASE_URL fail-loud logic is covered separately, as plain unit tests,
in tests/unit/test_config_helpers.py -- that logic runs at app.py import
time, outside of what this test harness's own hand-built app can exercise.)
"""

import pytest
from models import db
from tests.fixtures.factories import UserFactory


def _login_as(client, user):
    """Log `client` in as `user` by writing the session directly, the same
    way the admin_client/authenticated_client fixtures in conftest.py do --
    this test needs a user with a specific must_change_password value,
    which those fixtures don't parameterize."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user.id)
        sess['_fresh'] = True


@pytest.mark.integration
class TestForcedPasswordChange:
    """A user flagged must_change_password must be redirected to the
    change-password page for every request until they change it."""

    def test_flagged_user_is_redirected_away_from_a_normal_page(self, client, organization, db_session):
        user = UserFactory(organization=organization, role='Admin')
        user.must_change_password = True
        db_session.commit()
        _login_as(client, user)

        response = client.get('/members')

        assert response.status_code == 302
        assert f'/users/{user.id}/change-password' in response.location

    def test_unflagged_user_is_not_redirected(self, client, organization, db_session):
        user = UserFactory(organization=organization, role='Admin')
        user.must_change_password = False
        db_session.commit()
        _login_as(client, user)

        response = client.get('/members')

        assert response.status_code == 200

    def test_flagged_user_can_still_reach_the_change_password_page(self, client, organization, db_session):
        user = UserFactory(organization=organization, role='Admin')
        user.must_change_password = True
        db_session.commit()
        _login_as(client, user)

        response = client.get(f'/users/{user.id}/change-password')

        assert response.status_code == 200

    def test_flagged_user_can_still_log_out(self, client, organization, db_session):
        user = UserFactory(organization=organization, role='Admin')
        user.must_change_password = True
        db_session.commit()
        _login_as(client, user)

        response = client.get('/logout')

        assert response.status_code == 302
        assert '/login' in response.location

    def test_changing_password_clears_the_flag_and_lifts_the_redirect(self, client, organization, db_session):
        user = UserFactory(organization=organization, role='Admin')
        user.set_password('OldPassword123')
        user.must_change_password = True
        db_session.commit()
        _login_as(client, user)

        response = client.post(f'/users/{user.id}/change-password', data={
            'current_password': 'OldPassword123',
            'new_password': 'BrandNewPassword456',
            'confirm_password': 'BrandNewPassword456',
        }, follow_redirects=True)

        assert response.status_code == 200
        db_session.refresh(user)
        assert user.must_change_password is False
        assert user.check_password('BrandNewPassword456')

        # The redirect is now lifted for ordinary pages.
        response = client.get('/members')
        assert response.status_code == 200


@pytest.mark.integration
class TestLoginRateLimiting:
    """/login must reject repeated attempts past a per-IP quota.

    RATELIMIT_ENABLED is True for the whole suite (see conftest.py) --
    Flask-Limiter fixes enabled/disabled at limiter.init_app() time, so it
    can't be toggled per-test. The autouse reset_rate_limiter fixture in
    conftest.py clears counters before and after every test, so this test
    just needs to make its own repeated requests.
    """

    def test_repeated_failed_logins_are_rate_limited(self, client, organization, db_session):
        user = UserFactory(organization=organization, username='ratelimit_target')
        user.set_password('CorrectHorseBattery1')
        db_session.commit()

        responses = [
            client.post('/login', data={'username': 'ratelimit_target', 'password': 'wrong-password'})
            for _ in range(11)
        ]

        statuses = [r.status_code for r in responses]
        assert 429 in statuses, f"expected a 429 among {statuses} after exceeding the login rate limit"
        # The limit shouldn't fire before the configured quota is exhausted.
        assert statuses[0] != 429

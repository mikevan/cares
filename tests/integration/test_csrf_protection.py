"""
CARES Test Harness - Integration Tests - CSRF Protection
============================================================

Regression tests for the Flask-WTF CSRFProtect wiring added in app.py
(and mirrored onto the test app in conftest.py).

The shared `app` fixture disables CSRF (WTF_CSRF_ENABLED=False) so every
other integration test can keep posting plain form data without a token --
that's correct for testing route logic in isolation. These tests flip
protection ON for just their own duration to prove the mechanism itself
actually rejects unprotected requests, then turn it back off in a finally
block so no other test in the session is affected.
"""

import re
import pytest


def _extract_csrf_token(html_bytes):
    """Pull the token out of the <meta name="csrf-token" ...> tag base.html renders."""
    match = re.search(rb'name="csrf-token" content="([^"]+)"', html_bytes)
    assert match, "csrf-token meta tag not found in rendered page"
    return match.group(1).decode()


@pytest.mark.integration
class TestCSRFProtection:
    """A POST without a valid CSRF token must be rejected; one with a valid
    token must not be rejected for CSRF reasons."""

    def test_post_without_csrf_token_is_rejected(self, client, app):
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            response = client.post('/login', data={
                'username': 'nonexistent',
                'password': 'whatever',
            })
            assert response.status_code == 400
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

    def test_post_with_valid_csrf_token_is_not_rejected(self, client, app):
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            get_response = client.get('/login')
            token = _extract_csrf_token(get_response.data)

            response = client.post('/login', data={
                'username': 'nonexistent',
                'password': 'whatever',
                'csrf_token': token,
            })

            # A valid token clears CSRF validation. The login itself still
            # fails on bad credentials (re-render with a flash message),
            # but that is never CSRFProtect's 400.
            assert response.status_code != 400
        finally:
            app.config['WTF_CSRF_ENABLED'] = False


@pytest.mark.integration
class TestCSRFProtectionOnAjaxEndpoints:
    """The dues-roster toggles POST JSON via fetch(), not a form field, so
    they must supply the token via the X-CSRFToken header instead."""

    def test_dues_toggle_without_header_is_rejected(self, admin_client, app, organization, db_session):
        from tests.fixtures.factories import MemberFactory

        member = MemberFactory(organization=organization)
        db_session.commit()

        app.config['WTF_CSRF_ENABLED'] = True
        try:
            response = admin_client.post(
                '/members/dues/toggle',
                json={'member_id': member.id, 'year': 2026, 'paid': True},
            )
            assert response.status_code == 400
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

    def test_dues_toggle_with_header_is_not_rejected(self, admin_client, app, organization, db_session):
        from tests.fixtures.factories import MemberFactory

        member = MemberFactory(organization=organization)
        db_session.commit()

        app.config['WTF_CSRF_ENABLED'] = True
        try:
            get_response = admin_client.get('/members')
            token = _extract_csrf_token(get_response.data)

            response = admin_client.post(
                '/members/dues/toggle',
                json={'member_id': member.id, 'year': 2026, 'paid': True},
                headers={'X-CSRFToken': token},
            )
            assert response.status_code != 400
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

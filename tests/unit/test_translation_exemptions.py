"""The audit trail is never translated, by any route into the pipeline.

A translated before/after value is a rendering of the evidence, not the
evidence. audit_log is a hash-chained tamper-evident record and the Trustee
Audit Report exists so a trustee can read what was stored, exactly as stored.
These tests exist so that a later change cannot quietly reopen that door.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import pytest  # noqa: E402

from services.translation_service import is_translatable_route  # noqa: E402


@pytest.mark.parametrize('path', [
    '/audit',
    '/audit/log',
    '/audit/log.pdf',
    '/audit/verify',
    '/audit/form-1295/attest',
    '/audit/form-1295/schedule-a.pdf',
    '/audit/anything/added/later',
])
def test_audit_tree_is_never_translatable(path):
    assert is_translatable_route(path) is False


@pytest.mark.parametrize('path', ['/login', '/logout', '/static/css/app.css'])
def test_existing_exemptions_still_hold(path):
    assert is_translatable_route(path) is False


@pytest.mark.parametrize('path', [
    '/',
    '/members/',
    '/reports/balance-sheet',
    '/transactions/',
    '/chart-of-accounts/',
])
def test_ordinary_pages_remain_translatable(path):
    assert is_translatable_route(path) is True


def test_prefix_match_is_path_aware_not_substring():
    """'/auditors' is not '/audit' — a prefix check must respect the boundary."""
    assert is_translatable_route('/auditors') is True
    assert is_translatable_route('/audit-summary') is True


# ---------------------------------------------------------------------------
# The one deliberate carve-out
# ---------------------------------------------------------------------------

def test_form_1295_screen_is_translatable():
    """It computes schedules from the ledger; it reads nothing from audit_log."""
    assert is_translatable_route('/audit/form-1295') is True


@pytest.mark.parametrize('path', [
    '/audit/form-1295/attest',
    '/audit/form-1295/submission',
    '/audit/form-1295/schedule-a.pdf',
    '/audit/form-1295.pdf',
])
def test_the_carve_out_does_not_leak_to_children_or_pdfs(path):
    """Exact path only. The filed artifact stays in English."""
    assert is_translatable_route(path) is False

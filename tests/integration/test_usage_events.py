"""
CARES Test Harness - Integration Tests - Usage/Billing Telemetry
====================================================================

Covers services/usage_service.py's log_event() and the handful of call
sites wired to it (login, journal entry posted, invoice created, report
generated). See UsageEvent in models.py for what this data is for.
"""

from decimal import Decimal
from datetime import date, timedelta

import pytest

from models import db, UsageEvent, ChartOfAccounts, Vendor
from services.journal_service import post_entry
from services.usage_service import log_event


def _get_expense_account(db_session):
    account = db_session.query(ChartOfAccounts).filter_by(account_number='5010').first()
    assert account, "Account 5010 must exist (run chart of accounts init)"
    return account


@pytest.mark.integration
class TestLogEvent:
    """Unit-style tests for the log_event() helper itself."""

    def test_log_event_creates_a_row_with_the_given_fields(self, db_session, organization):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization)
        db_session.commit()

        log_event('test.something_happened', organization_id=organization.id,
                   user_id=user.id, meta={'foo': 'bar'})

        event = UsageEvent.query.filter_by(event_type='test.something_happened').first()
        assert event is not None
        assert event.organization_id == organization.id
        assert event.user_id == user.id
        assert event.event_meta == {'foo': 'bar'}
        assert event.created_at is not None

    def test_log_event_allows_missing_organization_and_user(self, db_session):
        log_event('test.anonymous_event')

        event = UsageEvent.query.filter_by(event_type='test.anonymous_event').first()
        assert event is not None
        assert event.organization_id is None
        assert event.user_id is None

    def test_log_event_swallows_a_bad_organization_id_without_raising(self, db_session):
        """
        A foreign-key violation (organization_id pointing at nothing) must
        not raise -- telemetry going down can never break the action it's
        recording. It also must not poison the session for whatever the
        caller does next.
        """
        log_event('test.bad_org_id', organization_id=999999)

        assert UsageEvent.query.filter_by(event_type='test.bad_org_id').first() is None

        # Session must still be usable after the swallowed failure.
        log_event('test.after_failure')
        assert UsageEvent.query.filter_by(event_type='test.after_failure').first() is not None


@pytest.mark.integration
class TestUsageEventsFromRealActions:
    """log_event() calls wired into real gateways actually fire."""

    def test_login_records_an_auth_login_event(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, username='usage_login_target')
        user.set_password('CorrectHorseBattery1')
        db_session.commit()
        # UserFactory silently appends a random suffix to any explicitly
        # given username (see tests/fixtures/factories.py) -- read back the
        # real value rather than assuming what was passed in survived, or
        # this login attempt 404s on username and never even reaches
        # log_event() (see tests/integration/test_audit_trail.py for the
        # same fix applied to the same underlying factory behavior).
        real_username = user.username

        client.post('/login', data={'username': real_username, 'password': 'CorrectHorseBattery1'})

        event = UsageEvent.query.filter_by(event_type='auth.login', user_id=user.id).first()
        assert event is not None
        assert event.organization_id == organization.id

    def test_posting_a_journal_entry_records_a_journal_entry_posted_event(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        expense = _get_expense_account(db_session)
        db_session.commit()

        entry = post_entry(
            entry_date=date.today(),
            description='Usage telemetry test entry',
            project_id=project.id,
            created_by=user.id,
            lines=[
                {'account_number': expense.account_number, 'debit': Decimal('25.00'), 'credit': Decimal('0')},
                {'account_number': '1010', 'debit': Decimal('0'), 'credit': Decimal('25.00')},
            ],
        )

        event = UsageEvent.query.filter_by(event_type='journal_entry.posted').first()
        assert event is not None
        assert event.organization_id == organization.id
        assert event.user_id == user.id
        assert event.event_meta['entry_id'] == entry.id

    def test_creating_an_invoice_records_an_ap_invoice_created_event(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        from services.ap_service import create_invoice

        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        expense = _get_expense_account(db_session)
        vendor = Vendor(organization_id=organization.id, name='Usage Test Vendor',
                         payment_terms='Net30', is_1099=False, active=True)
        db_session.add(vendor)
        db_session.flush()

        invoice = create_invoice(
            organization_id=organization.id,
            vendor_id=vendor.id,
            project_id=project.id,
            gl_account_number=expense.account_number,
            gl_account_id=expense.id,
            invoice_number='INV-USAGE-001',
            invoice_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            amount=Decimal('300.00'),
            notes='Usage telemetry test invoice',
            created_by=user.id,
        )

        event = UsageEvent.query.filter_by(event_type='ap.invoice_created').first()
        assert event is not None
        assert event.organization_id == organization.id
        assert event.event_meta['invoice_id'] == invoice.id

    def test_viewing_a_report_records_a_report_generated_event(self, admin_client, organization, db_session):
        response = admin_client.get('/reports/balance-sheet')
        assert response.status_code == 200

        event = UsageEvent.query.filter_by(event_type='report.generated').first()
        assert event is not None
        assert event.organization_id == organization.id
        assert event.event_meta['report'] == 'balance_sheet'

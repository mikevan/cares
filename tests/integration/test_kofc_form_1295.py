"""
CARES Test Harness - Integration Tests - Knights of Columbus Form 1295
========================================================================

Covers services/kofc_form_1295.py's Schedule A/B/C calculations (including
the Schedule A membership roll-forward and the Form1295Submission
explanation/attestation wizard), services/kofc_form_1295_pdf.py's PDF
rendering, and the routes in blueprints/audit_routes.py that expose all of
it. See services/kofc_form_1295.py for the recording convention these
figures depend on, models.py::MembershipEvent for why Schedule A needs its
own event log rather than a plain active/inactive flag, and
tests/integration/test_audit_trail.py for the underlying audit trail this
report sits on top of.
"""
from datetime import date, datetime
from decimal import Decimal

import pytest

from models import db, MembershipEvent
from services.journal_service import post_simple_entry
from services.kofc_form_1295 import (
    schedule_a, schedule_b, schedule_c, get_audit_period,
    get_submission, save_submission_explanations, attest_submission,
)
from tests.fixtures.factories import UserFactory, ProjectFactory, MemberFactory


PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 6, 30)
OUTSIDE_PERIOD = date(2026, 7, 15)  # deliberately outside [PERIOD_START, PERIOD_END]
BEFORE_PERIOD = date(2020, 1, 1)  # deliberately well before PERIOD_START


def _log_event(organization, member, event_type, event_date):
    event = MembershipEvent(
        member_id=member.id,
        organization_id=organization.id,
        event_type=event_type,
        event_date=event_date,
    )
    db.session.add(event)
    return event


@pytest.mark.integration
class TestGetAuditPeriod:

    def test_a_date_in_the_first_half_returns_the_prior_jul_dec_period(self):
        start, end, label = get_audit_period(as_of=date(2026, 3, 15))
        assert (start, end) == (date(2025, 7, 1), date(2025, 12, 31))
        assert '2025' in label

    def test_a_date_in_the_second_half_returns_the_same_year_jan_jun_period(self):
        start, end, label = get_audit_period(as_of=date(2026, 9, 1))
        assert (start, end) == (date(2026, 1, 1), date(2026, 6, 30))
        assert '2026' in label


@pytest.mark.integration
class TestScheduleA:

    def test_roll_forward_computes_start_additions_deductions_and_end(self, db_session, organization):
        # Three members initiated well before the period -- establishes a
        # start-of-period count of 3.
        starting_members = [MemberFactory(organization=organization) for _ in range(3)]
        db_session.commit()
        for member in starting_members:
            _log_event(organization, member, 'Initiation', BEFORE_PERIOD)

        # One addition and one deduction, both logged inside the period.
        new_member = MemberFactory(organization=organization)
        db_session.commit()
        _log_event(organization, new_member, 'Initiation', date(2026, 2, 1))
        _log_event(organization, starting_members[0], 'Death', date(2026, 3, 1))
        db_session.commit()

        result = schedule_a(organization.id, PERIOD_START, PERIOD_END)

        assert result['members_start_of_period'] == 3
        assert result['additions']['Initiation'] == 1
        assert result['total_additions'] == 1
        assert result['total_for_period'] == 4
        assert result['deductions']['Death'] == 1
        assert result['total_deductions'] == 1
        assert result['members_end_of_period'] == 3

    def test_events_outside_the_period_do_not_count_as_additions_or_deductions(self, db_session, organization):
        member = MemberFactory(organization=organization)
        db_session.commit()
        _log_event(organization, member, 'Initiation', BEFORE_PERIOD)
        _log_event(organization, member, 'Suspension', OUTSIDE_PERIOD)
        db_session.commit()

        result = schedule_a(organization.id, PERIOD_START, PERIOD_END)
        assert result['members_start_of_period'] == 1
        assert result['total_additions'] == 0
        assert result['total_deductions'] == 0
        assert result['members_end_of_period'] == 1

    def test_reconciled_is_true_when_roll_forward_matches_live_active_count(self, db_session, organization):
        members = [MemberFactory(organization=organization, active=True) for _ in range(2)]
        db_session.commit()
        for member in members:
            _log_event(organization, member, 'Initiation', BEFORE_PERIOD)
        db_session.commit()

        result = schedule_a(organization.id, PERIOD_START, PERIOD_END)
        assert result['members_end_of_period'] == 2
        assert result['active_members_actual'] == 2
        assert result['reconciled'] is True

    def test_reconciled_is_false_when_a_status_change_was_never_logged(self, db_session, organization):
        # Two members initiated and logged as such, but one was later
        # flipped to inactive directly (e.g. the Active checkbox toggled
        # with no reason recorded) -- the roll-forward and the live
        # member directory now disagree.
        member_a = MemberFactory(organization=organization, active=True)
        member_b = MemberFactory(organization=organization, active=False)
        db_session.commit()
        _log_event(organization, member_a, 'Initiation', BEFORE_PERIOD)
        _log_event(organization, member_b, 'Initiation', BEFORE_PERIOD)
        db_session.commit()

        result = schedule_a(organization.id, PERIOD_START, PERIOD_END)
        assert result['members_end_of_period'] == 2
        assert result['active_members_actual'] == 1
        assert result['reconciled'] is False

    def test_dues_collected_reflects_only_entries_posted_inside_the_period(self, db_session, organization, user):
        project = ProjectFactory(organization=organization)
        db_session.commit()
        post_simple_entry(
            entry_date=date(2026, 3, 1), description='Dues in period',
            project_id=project.id, created_by=user.id,
            debit_account='1010', credit_account='4110', amount=Decimal('150.00'),
        )
        post_simple_entry(
            entry_date=OUTSIDE_PERIOD, description='Dues outside period',
            project_id=project.id, created_by=user.id,
            debit_account='1010', credit_account='4110', amount=Decimal('999.00'),
        )

        result = schedule_a(organization.id, PERIOD_START, PERIOD_END)
        assert result['dues_collected_in_period'] == Decimal('150.00')


@pytest.mark.integration
class TestScheduleB:

    def test_dues_initiations_fundraiser_and_disbursements_are_categorized_correctly(self, db_session, organization, user):
        regular_project = ProjectFactory(organization=organization, is_fundraiser=False)
        fundraiser_project = ProjectFactory(organization=organization, is_fundraiser=True, name='Spring Raffle')
        db_session.commit()

        # Dues and initiation fees -- Form 1295's Financial Secretary side
        # reports these as one combined line.
        post_simple_entry(
            entry_date=date(2026, 2, 1), description='Dues', project_id=regular_project.id, created_by=user.id,
            debit_account='1010', credit_account='4110', amount=Decimal('500.00'),
        )
        post_simple_entry(
            entry_date=date(2026, 2, 5), description='Initiation fee', project_id=regular_project.id, created_by=user.id,
            debit_account='1010', credit_account='4115', amount=Decimal('120.00'),
        )
        # Fundraiser revenue, tied to the fundraiser-flagged project
        post_simple_entry(
            entry_date=date(2026, 3, 1), description='Raffle proceeds', project_id=fundraiser_project.id, created_by=user.id,
            debit_account='1010', credit_account='4210', amount=Decimal('1200.00'),
        )
        # Checking-account interest -- a Treasurer-side line, not FS cash received.
        post_simple_entry(
            entry_date=date(2026, 3, 10), description='Checking interest', project_id=regular_project.id, created_by=user.id,
            debit_account='1010', credit_account='4415', amount=Decimal('5.00'),
        )
        # Non-checking investment interest -- never cash anyone actually
        # handled, so it must not show up anywhere on Schedule B.
        post_simple_entry(
            entry_date=date(2026, 3, 10), description='Savings interest', project_id=regular_project.id, created_by=user.id,
            debit_account='1020', credit_account='4410', amount=Decimal('50.00'),
        )
        # Per capita disbursements
        post_simple_entry(
            entry_date=date(2026, 4, 1), description='Supreme per capita', project_id=regular_project.id, created_by=user.id,
            debit_account='5850', credit_account='1010', amount=Decimal('300.00'),
        )
        post_simple_entry(
            entry_date=date(2026, 4, 1), description='State per capita', project_id=regular_project.id, created_by=user.id,
            debit_account='5860', credit_account='1010', amount=Decimal('100.00'),
        )
        # Charitable donation given
        post_simple_entry(
            entry_date=date(2026, 5, 1), description='Charity', project_id=regular_project.id, created_by=user.id,
            debit_account='5870', credit_account='1010', amount=Decimal('75.00'),
        )
        # A pure transfer from checking to savings (both cash accounts, no revenue/expense)
        post_simple_entry(
            entry_date=date(2026, 5, 15), description='Move to savings', project_id=regular_project.id, created_by=user.id,
            debit_account='1020', credit_account='1010', amount=Decimal('200.00'),
        )
        # Outside the period -- must not be counted
        post_simple_entry(
            entry_date=OUTSIDE_PERIOD, description='Late per capita', project_id=regular_project.id, created_by=user.id,
            debit_account='5850', credit_account='1010', amount=Decimal('9999.00'),
        )

        result = schedule_b(organization.id, PERIOD_START, PERIOD_END)
        fs = result['financial_secretary']
        tr = result['treasurer']

        assert fs['dues_and_initiations_received'] == Decimal('500.00') + Decimal('120.00')
        assert fs['top_fundraisers'] == [{'name': 'Spring Raffle', 'amount': Decimal('1200.00')}]
        # Interest (checking or otherwise) never lands in "miscellaneous income".
        assert fs['misc_income'] == Decimal('0')
        assert fs['total_cash_received'] == Decimal('620.00') + Decimal('1200.00')
        # Nothing was ever recorded in the Financial Secretary Cash on Hand
        # account (1040), so every dollar received is modeled as
        # immediately transferred to the Treasurer -- see the module
        # docstring for why this is the correct behavior, not a gap.
        assert fs['transferred_to_treasurer'] == fs['total_cash_received']
        assert fs['opening_funds_in_possession'] == Decimal('0')
        assert fs['closing_funds_in_possession'] == Decimal('0')

        assert tr['checking_account_interest'] == Decimal('5.00')
        assert tr['per_capita_supreme_council'] == Decimal('300.00')
        assert tr['per_capita_state_council'] == Decimal('100.00')
        assert tr['charitable_donations'] == Decimal('75.00')
        assert tr['transfers_to_savings'] == Decimal('200.00')
        assert tr['transfers_from_savings'] == Decimal('0')


@pytest.mark.integration
class TestScheduleC:

    def test_current_and_long_term_assets_split_correctly(self, db_session, organization, user):
        project = ProjectFactory(organization=organization)
        db_session.commit()

        # Cash actually in checking as of period end
        post_simple_entry(
            entry_date=date(2026, 2, 1), description='Dues', project_id=project.id, created_by=user.id,
            debit_account='1010', credit_account='4110', amount=Decimal('800.00'),
        )
        # An accrued (unpaid) per capita liability: expense recognized now,
        # owed (not yet paid out of checking) as of period end.
        post_simple_entry(
            entry_date=date(2026, 6, 1), description='Accrued state per capita', project_id=project.id, created_by=user.id,
            debit_account='5860', credit_account='2140', amount=Decimal('120.00'),
        )
        # Moving part of that cash into a certificate of deposit -- a
        # long-term asset, not a current one, per Form 1295's own layout.
        post_simple_entry(
            entry_date=date(2026, 6, 15), description='Buy CD', project_id=project.id, created_by=user.id,
            debit_account='1340', credit_account='1010', amount=Decimal('300.00'),
        )

        result = schedule_c(organization.id, PERIOD_END)
        current = result['assets']['current']
        long_term = result['assets']['long_term']

        assert current['checking_account'] == Decimal('500.00')  # 800 - 300 moved to the CD
        assert current['total_current_assets'] == (
            current['financial_secretary_cash_on_hand'] + current['checking_account']
            + current['savings_account'] + current['money_market_account']
        )
        assert long_term['certificates_of_deposit'] == Decimal('300.00')
        assert long_term['total_long_term_assets'] == Decimal('300.00')
        assert result['assets']['total_assets'] == current['total_current_assets'] + Decimal('300.00')

        assert result['liabilities']['state_council_charges'] == Decimal('120.00')
        assert result['liabilities']['total_liabilities'] == Decimal('120.00')
        assert result['net_current_assets'] == current['total_current_assets'] - Decimal('120.00')
        assert result['total_net_assets'] == result['assets']['total_assets'] - Decimal('120.00')


@pytest.mark.integration
class TestForm1295Submission:

    def test_get_submission_returns_none_when_nothing_saved_yet(self, db_session, organization):
        assert get_submission(organization.id, PERIOD_START, PERIOD_END) is None

    def test_save_submission_explanations_creates_then_updates(self, db_session, organization):
        submission = save_submission_explanations(
            organization.id, PERIOD_START, PERIOD_END,
            'Raffle proceeds not tied to a project.', None,
        )
        assert submission.misc_income_explanation == 'Raffle proceeds not tied to a project.'
        assert submission.misc_liabilities_explanation is None

        updated = save_submission_explanations(
            organization.id, PERIOD_START, PERIOD_END,
            'Updated explanation.', 'An unpaid vendor invoice.',
        )
        assert updated.id == submission.id  # same row, not a duplicate
        assert updated.misc_income_explanation == 'Updated explanation.'
        assert updated.misc_liabilities_explanation == 'An unpaid vendor invoice.'

    def test_attest_submission_records_user_and_timestamp(self, db_session, organization, user):
        assert get_submission(organization.id, PERIOD_START, PERIOD_END) is None

        submission = attest_submission(organization.id, PERIOD_START, PERIOD_END, user.id)
        assert submission.attested_by_user_id == user.id
        assert submission.attested_at is not None
        assert submission.is_attested is True


@pytest.mark.integration
class TestForm1295Routes:

    def test_non_admin_cannot_view_form_1295(self, authenticated_client):
        response = authenticated_client.get('/audit/form-1295')
        assert response.status_code == 302
        with authenticated_client.session_transaction() as sess:
            flashed_messages = [message for _category, message in sess.get('_flashes', [])]
        assert any('Permission denied' in message for message in flashed_messages)

    def test_admin_can_view_form_1295(self, admin_client):
        response = admin_client.get('/audit/form-1295')
        assert response.status_code == 200
        assert b'Schedule A' in response.data
        assert b'Schedule B' in response.data
        assert b'Schedule C' in response.data
        assert b'Attestation' in response.data

    @pytest.mark.parametrize('endpoint', [
        '/audit/form-1295/schedule-a.pdf',
        '/audit/form-1295/schedule-b.pdf',
        '/audit/form-1295/schedule-c.pdf',
    ])
    def test_admin_can_download_each_schedule_as_a_pdf(self, admin_client, endpoint):
        response = admin_client.get(endpoint)
        assert response.status_code == 200
        assert response.content_type == 'application/pdf'
        assert response.data.startswith(b'%PDF')

    def test_non_admin_cannot_download_schedule_pdfs(self, authenticated_client):
        response = authenticated_client.get('/audit/form-1295/schedule-a.pdf')
        assert response.status_code == 302

    def test_admin_can_save_submission_explanations(self, admin_client, organization):
        response = admin_client.post(
            f'/audit/form-1295/submission?period_start={PERIOD_START.isoformat()}&period_end={PERIOD_END.isoformat()}',
            data={'misc_income_explanation': 'Member donation drive.', 'misc_liabilities_explanation': ''},
        )
        assert response.status_code == 302
        submission = get_submission(organization.id, PERIOD_START, PERIOD_END)
        assert submission is not None
        assert submission.misc_income_explanation == 'Member donation drive.'

    def test_admin_can_attest_schedules(self, admin_client, organization):
        response = admin_client.post(
            f'/audit/form-1295/attest?period_start={PERIOD_START.isoformat()}&period_end={PERIOD_END.isoformat()}',
        )
        assert response.status_code == 302
        submission = get_submission(organization.id, PERIOD_START, PERIOD_END)
        assert submission is not None
        assert submission.is_attested is True

    def test_non_admin_cannot_save_submission_or_attest(self, authenticated_client):
        response = authenticated_client.post('/audit/form-1295/submission')
        assert response.status_code == 302
        response = authenticated_client.post('/audit/form-1295/attest')
        assert response.status_code == 302

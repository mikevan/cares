"""
CARES Test Harness - Integration Tests - Organization Isolation
==================================================================

Regression tests for the cross-tenant authorization gaps fixed in
project_routes.view/edit, transaction_routes.view, journal_service.void_entry,
and the project volunteer/leader assignment routes.

Each test creates a SECOND organization (distinct from the `organization`
fixture used by `admin_client`) and confirms a user logged into org A cannot
read, edit, void, or attach records that belong to org B.
"""

import pytest
from decimal import Decimal
from models import Project, JournalEntry
from services.journal_service import void_entry, JournalServiceError
from tests.fixtures.factories import (
    OrganizationFactory, ProjectFactory, MemberFactory, JournalEntryFactory, UserFactory,
)


@pytest.mark.integration
class TestProjectIsolation:
    """A user in one organization must not be able to view or edit another's projects."""

    def test_view_project_in_other_org_returns_404(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org, name='Other Org Project')
        db_session.commit()

        response = admin_client.get(f'/projects/{other_project.id}/view')

        assert response.status_code == 404

    def test_edit_project_in_other_org_returns_404(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org, name='Other Org Project')
        db_session.commit()

        # GET the edit form
        response = admin_client.get(f'/projects/{other_project.id}/edit')
        assert response.status_code == 404

    def test_edit_project_in_other_org_does_not_modify_it(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(
            organization=other_org, name='Untouched Name', budget=Decimal('500.00')
        )
        db_session.commit()

        response = admin_client.post(f'/projects/{other_project.id}/edit', data={
            'name': 'Hijacked Name',
            'status': 'Active',
            'budget': '999999.00',
        })

        assert response.status_code == 404

        db_session.refresh(other_project)
        assert other_project.name == 'Untouched Name'
        assert other_project.budget == Decimal('500.00')

    def test_add_volunteer_from_other_org_is_rejected(self, admin_client, organization, db_session):
        """A member belonging to a different organization must not be attachable
        as a volunteer on this organization's project."""
        own_project = ProjectFactory(organization=organization, name='Own Project')
        other_org = OrganizationFactory()
        outside_member = MemberFactory(organization=other_org, name='Outsider')
        db_session.commit()

        response = admin_client.post(f'/projects/{own_project.id}/volunteers/add', data={
            'member_id': outside_member.id,
        }, follow_redirects=True)

        assert response.status_code == 200
        db_session.refresh(own_project)
        assert outside_member not in own_project.volunteers

    def test_add_leader_from_other_org_is_rejected(self, admin_client, organization, db_session):
        own_project = ProjectFactory(organization=organization, name='Own Project')
        other_org = OrganizationFactory()
        outside_member = MemberFactory(organization=other_org, name='Outsider')
        db_session.commit()

        response = admin_client.post(f'/projects/{own_project.id}/leaders/add', data={
            'member_id': outside_member.id,
        }, follow_redirects=True)

        assert response.status_code == 200
        db_session.refresh(own_project)
        assert outside_member not in own_project.leaders

    def test_new_project_ignores_volunteer_ids_from_other_org(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        outside_member = MemberFactory(organization=other_org, name='Outsider')
        db_session.commit()

        response = admin_client.post('/projects/new', data={
            'name': 'New Project With Outsider',
            'status': 'Active',
            'volunteers': [str(outside_member.id)],
        }, follow_redirects=True)

        assert response.status_code == 200
        project = Project.query.filter_by(name='New Project With Outsider').first()
        assert project is not None
        assert outside_member not in project.volunteers


@pytest.mark.integration
class TestTransactionIsolation:
    """A user in one organization must not be able to view or void another's transactions."""

    def test_view_transaction_in_other_org_returns_404(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org)
        other_entry = JournalEntryFactory(
            project=other_project, description='Other Org Transaction'
        )
        db_session.commit()

        response = admin_client.get(f'/transactions/{other_entry.id}')

        assert response.status_code == 404

    def test_void_transaction_in_other_org_does_not_void_it(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org)
        other_entry = JournalEntryFactory(project=other_project, status='Posted')
        db_session.commit()

        response = admin_client.post(
            f'/transactions/{other_entry.id}/void', follow_redirects=True
        )

        # The route redirects with a flash error rather than 404ing, but the
        # entry itself must be left completely untouched.
        assert response.status_code == 200
        db_session.refresh(other_entry)
        assert other_entry.status == 'Posted'


@pytest.mark.integration
class TestVoidEntryServiceIsolation:
    """Direct tests of services.journal_service.void_entry's organization scoping,
    independent of the HTTP layer."""

    def test_void_entry_succeeds_for_own_organization(self, organization, db_session):
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        entry = JournalEntryFactory(project=project, created_by=user.id, status='Posted')
        db_session.commit()

        result = void_entry(entry.id, voided_by=user.id, organization_id=organization.id)

        assert result.status == 'Voided'

    def test_void_entry_raises_for_other_organization(self, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org)
        other_entry = JournalEntryFactory(project=other_project, status='Posted')
        db_session.commit()

        with pytest.raises(JournalServiceError):
            # Calling with `organization.id` (a DIFFERENT org than the entry's)
            # must be treated the same as "not found" -- it must not void it.
            void_entry(other_entry.id, voided_by=1, organization_id=organization.id)

        db_session.refresh(other_entry)
        assert other_entry.status == 'Posted'

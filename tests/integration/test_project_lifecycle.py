"""
CARES Test Harness - Integration Tests - Project Leadership Lifecycle
=======================================================================

Covers services/project_service.py (assign_member, end_assignment,
close_project_for_year, restart_project) and the project_routes.py
endpoints that wrap them: appointing a leader/volunteer, resigning,
being dismissed, a project's year closing out, and restarting the
project for the next cycle as a new, linked Project row.
"""

import pytest
from datetime import date
from models import db, Project, ProjectAssignment, PROJECT_ASSIGNMENT_END_REASONS
from services.project_service import (
    assign_member, end_assignment, close_project_for_year, restart_project, ProjectServiceError
)
from tests.fixtures.factories import ProjectFactory, MemberFactory, OrganizationFactory


@pytest.mark.integration
class TestAssignMember:
    """services.project_service.assign_member"""

    def test_assign_member_creates_open_assignment(self, organization, db_session):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()

        assignment = assign_member(project, member, role='Leader')

        assert assignment.id is not None
        assert assignment.project_id == project.id
        assert assignment.member_id == member.id
        assert assignment.role == 'Leader'
        assert assignment.end_date is None
        assert assignment.is_active is True
        assert member in project.leaders

    def test_assign_member_is_idempotent(self, organization, db_session):
        """Assigning the same member to the same role twice returns the
        existing open assignment instead of creating a duplicate."""
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()

        first = assign_member(project, member, role='Volunteer')
        second = assign_member(project, member, role='Volunteer')

        assert first.id == second.id
        assert ProjectAssignment.query.filter_by(
            project_id=project.id, member_id=member.id, role='Volunteer'
        ).count() == 1

    def test_assign_member_rejects_invalid_role(self, organization, db_session):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()

        with pytest.raises(ProjectServiceError):
            assign_member(project, member, role='Manager')

    def test_assign_member_rejects_cross_organization_member(self, organization, db_session):
        project = ProjectFactory(organization=organization)
        other_org = OrganizationFactory()
        outside_member = MemberFactory(organization=other_org)
        db_session.commit()

        with pytest.raises(ProjectServiceError):
            assign_member(project, outside_member, role='Volunteer')


@pytest.mark.integration
class TestEndAssignment:
    """services.project_service.end_assignment"""

    @pytest.mark.parametrize('reason', PROJECT_ASSIGNMENT_END_REASONS)
    def test_end_assignment_accepts_every_defined_reason(self, organization, db_session, reason):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        assignment = assign_member(project, member, role='Leader')

        ended = end_assignment(assignment, end_reason=reason, end_notes='test note')

        assert ended.end_reason == reason
        assert ended.end_date is not None
        assert ended.end_notes == 'test note'
        assert ended.is_active is False
        assert member not in project.leaders

    def test_end_assignment_rejects_unknown_reason(self, organization, db_session):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        assignment = assign_member(project, member, role='Volunteer')

        with pytest.raises(ProjectServiceError):
            end_assignment(assignment, end_reason='Got Bored')

    def test_end_assignment_rejects_already_ended(self, organization, db_session):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        assignment = assign_member(project, member, role='Volunteer')
        end_assignment(assignment, end_reason='Resigned')

        with pytest.raises(ProjectServiceError):
            end_assignment(assignment, end_reason='Dismissed')

    def test_dismissed_and_resigned_are_distinguishable_in_history(self, organization, db_session):
        """Two different leaders leaving for two different reasons must each
        keep their own recorded reason -- this is the whole point of moving
        off a bare many-to-many table."""
        project = ProjectFactory(organization=organization)
        quitter = MemberFactory(organization=organization, name='Quitter')
        fired = MemberFactory(organization=organization, name='Fired')
        db_session.commit()

        quit_assignment = assign_member(project, quitter, role='Leader')
        fired_assignment = assign_member(project, fired, role='Leader')

        end_assignment(quit_assignment, end_reason='Resigned')
        end_assignment(fired_assignment, end_reason='Dismissed', end_notes='Repeated no-shows')

        assert quit_assignment.end_reason == 'Resigned'
        assert fired_assignment.end_reason == 'Dismissed'
        assert fired_assignment.end_notes == 'Repeated no-shows'
        assert quitter not in project.leaders
        assert fired not in project.leaders


@pytest.mark.integration
class TestCloseProjectForYear:
    """services.project_service.close_project_for_year"""

    def test_close_ends_every_open_assignment_as_term_completed(self, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        leader = MemberFactory(organization=organization)
        volunteer = MemberFactory(organization=organization)
        db_session.commit()
        assign_member(project, leader, role='Leader')
        assign_member(project, volunteer, role='Volunteer')

        close_project_for_year(project)

        assert project.status == 'Completed'
        assert project.active_assignments == []
        for assignment in project.assignments.all():
            assert assignment.end_reason == 'Term Completed'
            assert assignment.end_date is not None

    def test_close_does_not_touch_already_ended_assignments(self, organization, db_session):
        """A leader who resigned mid-year keeps 'Resigned' -- closing the
        project for the year must not overwrite that with 'Term Completed'."""
        project = ProjectFactory(organization=organization, status='Active')
        quitter = MemberFactory(organization=organization)
        stayed = MemberFactory(organization=organization)
        db_session.commit()
        quit_assignment = assign_member(project, quitter, role='Leader')
        end_assignment(quit_assignment, end_reason='Resigned')
        assign_member(project, stayed, role='Volunteer')

        close_project_for_year(project)

        assert quit_assignment.end_reason == 'Resigned'


@pytest.mark.integration
class TestRestartProject:
    """services.project_service.restart_project"""

    def test_restart_creates_new_linked_project(self, organization, db_session):
        project = ProjectFactory(organization=organization, name='Annual Fundraiser', status='Active')
        db_session.commit()
        close_project_for_year(project)

        new_project = restart_project(project, start_date=date(2027, 1, 1))

        assert new_project.id != project.id
        assert new_project.previous_project_id == project.id
        assert new_project.previous_project == project
        assert project.next_project == new_project
        assert new_project.name == project.name
        assert new_project.organization_id == project.organization_id
        assert new_project.status == 'Active'
        assert new_project.start_date == date(2027, 1, 1)

    def test_restart_carries_forward_only_term_completed_people(self, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        stayed_leader = MemberFactory(organization=organization, name='Stayed')
        quit_leader = MemberFactory(organization=organization, name='Quit')
        db_session.commit()

        stayed_assignment = assign_member(project, stayed_leader, role='Leader')
        quit_assignment = assign_member(project, quit_leader, role='Leader')
        end_assignment(quit_assignment, end_reason='Resigned')
        close_project_for_year(project)  # ends stayed_assignment as Term Completed

        new_project = restart_project(project, start_date=date(2027, 1, 1))

        assert stayed_leader in new_project.leaders
        assert quit_leader not in new_project.leaders

    def test_restart_without_carry_forward_starts_empty(self, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        leader = MemberFactory(organization=organization)
        db_session.commit()
        assign_member(project, leader, role='Leader')
        close_project_for_year(project)

        new_project = restart_project(project, carry_forward_people=False)

        assert new_project.leaders == []
        assert new_project.volunteers == []

    def test_restart_rejects_project_that_already_has_a_next_cycle(self, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        db_session.commit()
        close_project_for_year(project)
        restart_project(project)

        with pytest.raises(ProjectServiceError):
            restart_project(project)


@pytest.mark.integration
class TestProjectLifecycleRoutes:
    """HTTP-level coverage for the assignment/close/restart endpoints in
    blueprints/project_routes.py."""

    def test_end_assignment_route_requires_admin_or_treasurer(self, authenticated_client, organization, db_session):
        """The default factory role is 'Member' -- it must be denied."""
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        assignment = assign_member(project, member, role='Volunteer')

        response = authenticated_client.post(
            f'/projects/{project.id}/assignments/{assignment.id}/end',
            data={'end_reason': 'Resigned'},
        )

        assert response.status_code == 302
        db_session.refresh(assignment)
        assert assignment.end_date is None  # not ended

    def test_end_assignment_route_ends_assignment(self, admin_client, organization, db_session):
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        assignment = assign_member(project, member, role='Leader')

        response = admin_client.post(
            f'/projects/{project.id}/assignments/{assignment.id}/end',
            data={'end_reason': 'Dismissed', 'end_notes': 'Policy violation'},
            follow_redirects=True,
        )

        assert response.status_code == 200
        db_session.refresh(assignment)
        assert assignment.end_reason == 'Dismissed'
        assert assignment.end_date is not None

    def test_end_assignment_route_rejects_assignment_from_other_org_project(self, admin_client, organization, db_session):
        other_org = OrganizationFactory()
        other_project = ProjectFactory(organization=other_org)
        other_member = MemberFactory(organization=other_org)
        db_session.commit()
        other_assignment = assign_member(other_project, other_member, role='Leader')

        response = admin_client.post(
            f'/projects/{other_project.id}/assignments/{other_assignment.id}/end',
            data={'end_reason': 'Dismissed'},
        )

        assert response.status_code == 404
        db_session.refresh(other_assignment)
        assert other_assignment.end_date is None

    def test_close_route_closes_project(self, admin_client, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        member = MemberFactory(organization=organization)
        db_session.commit()
        assign_member(project, member, role='Volunteer')

        response = admin_client.post(f'/projects/{project.id}/close', follow_redirects=True)

        assert response.status_code == 200
        db_session.refresh(project)
        assert project.status == 'Completed'
        assert project.active_assignments == []

    def test_close_route_requires_admin_or_treasurer(self, authenticated_client, organization, db_session):
        project = ProjectFactory(organization=organization, status='Active')
        db_session.commit()

        response = authenticated_client.post(f'/projects/{project.id}/close')

        assert response.status_code == 302
        db_session.refresh(project)
        assert project.status == 'Active'

    def test_restart_route_creates_next_year_project(self, admin_client, organization, db_session):
        project = ProjectFactory(organization=organization, name='Fall Festival', status='Completed')
        db_session.commit()

        response = admin_client.post(
            f'/projects/{project.id}/restart',
            data={'start_date': '2027-02-01', 'carry_forward_people': 'on'},
            follow_redirects=True,
        )

        assert response.status_code == 200
        new_project = Project.query.filter_by(
            organization_id=organization.id, previous_project_id=project.id
        ).first()
        assert new_project is not None
        assert new_project.name == 'Fall Festival'

    def test_restart_route_requires_admin_or_treasurer(self, authenticated_client, organization, db_session):
        project = ProjectFactory(organization=organization, status='Completed')
        db_session.commit()

        response = authenticated_client.get(f'/projects/{project.id}/restart')

        assert response.status_code == 302
        assert Project.query.filter_by(previous_project_id=project.id).first() is None

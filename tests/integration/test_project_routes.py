"""
CARES Test Harness - Integration Tests - Project Routes
========================================================

Integration tests for project management routes.

Tests project creation, budget tracking, volunteer assignments,
and project-related workflows.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from models import Project, Member


@pytest.mark.integration
class TestProjectRoutes:
    """Integration tests for project routes."""
    
    def test_projects_list_requires_authentication(self, client):
        """Test that projects list requires authentication."""
        response = client.get('/projects')
        
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_projects_list_shows_projects(self, organization, db_session, client):
        """Test that projects list shows existing projects."""
        from tests.fixtures.factories import ProjectFactory, UserFactory

        user = UserFactory(organization=organization)
        project = ProjectFactory(
            organization=organization,
            name='Test Project',
            status='Active'
        )
        db_session.commit()

        # Log in as the created user
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/projects')

        assert response.status_code == 200
        assert b'Test Project' in response.data
    
    def test_create_project(self, admin_client, organization, db_session):
        """Test creating a new project."""
        initial_count = Project.query.filter_by(organization=organization).count()
        
        response = admin_client.post('/projects/new', data={
            'name': 'Food Drive 2026',
            'description': 'Annual food drive program',
            'start_date': date.today().isoformat(),
            'end_date': (date.today() + timedelta(days=90)).isoformat(),
            'budget': '5000.00',
            'status': 'Active',
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify project was created
        new_count = Project.query.filter_by(organization=organization).count()
        assert new_count == initial_count + 1
        
        # Verify project details
        project = Project.query.filter_by(
            name='Food Drive 2026',
            organization=organization
        ).first()
        assert project is not None
        assert project.budget == Decimal('5000.00')
        assert project.status == 'Active'
    
    def test_update_project(self, admin_client, organization, db_session):
        """Test updating project details."""
        from tests.fixtures.factories import ProjectFactory
        
        project = ProjectFactory(
            organization=organization,
            name='Original Name',
            budget=Decimal('1000.00')
        )
        original_id = project.id
        db_session.commit()
        
        response = admin_client.post(f'/projects/{project.id}/edit', data={
            'name': 'Updated Name',
            'description': project.description,
            'start_date': project.start_date.isoformat(),
            'budget': '2000.00',
            'status': project.status,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Refresh from database
        db_session.refresh(project)
        
        assert project.name == 'Updated Name'
        assert project.budget == Decimal('2000.00')
    
    def test_delete_project(self, admin_client, organization, db_session):
        """Test deleting a project."""
        from tests.fixtures.factories import ProjectFactory
        
        project = ProjectFactory(organization=organization)
        project_id = project.id
        db_session.commit()
        
        initial_count = Project.query.filter_by(organization=organization).count()
        
        response = admin_client.post(
            f'/projects/{project_id}/delete',
            follow_redirects=True
        )
        
        assert response.status_code == 200
        
        # Verify project was deleted
        new_count = Project.query.filter_by(organization=organization).count()
        assert new_count == initial_count - 1
        
        deleted_project = Project.query.get(project_id)
        assert deleted_project is None


@pytest.mark.integration
class TestProjectBudgets:
    """Integration tests for project budget functionality."""
    
    def test_project_budget_validation(self, admin_client, organization, db_session):
        """Test that project budget must be a valid number."""
        response = admin_client.post('/projects/new', data={
            'name': 'Test Project',
            'budget': 'not a number',  # Invalid budget
            'status': 'Active',
        })
        
        # Should show validation error or reject
        assert response.status_code in [200, 400]
    
    def test_project_budget_can_be_zero(self, admin_client, organization, db_session):
        """Test that projects can have zero budget."""
        response = admin_client.post('/projects/new', data={
            'name': 'No Budget Project',
            'budget': '0.00',
            'status': 'Active',
        }, follow_redirects=True)
        
        project = Project.query.filter_by(name='No Budget Project').first()
        assert project is not None
        assert project.budget == Decimal('0.00')
    
    def test_project_budget_tracks_spending(self, admin_client, organization, db_session):
        """Test that project tracks spending against budget."""
        from tests.fixtures.factories import ProjectFactory, JournalEntryFactory, UserFactory
        
        user = UserFactory(organization=organization)
        project = ProjectFactory(
            organization=organization,
            budget=Decimal('1000.00')
        )
        
        # Create some expenses for the project
        JournalEntryFactory.create_batch(
            3,
            project=project,
            created_by=user.id
        )
        db_session.commit()
        
        # Project should track these entries
        assert project.journal_entries.count() == 3


@pytest.mark.integration
class TestProjectVolunteers:
    """Integration tests for project volunteer assignments."""
    
    def test_assign_volunteer_to_project(self, admin_client, organization, db_session):
        """Test assigning a volunteer to a project."""
        from tests.fixtures.factories import ProjectFactory, MemberFactory
        
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        
        response = admin_client.post(f'/projects/{project.id}/volunteers/add', data={
            'member_id': member.id,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify assignment
        db_session.refresh(project)
        assert member in project.volunteers
    
    def test_remove_volunteer_from_project(self, admin_client, organization, db_session):
        """Test removing a volunteer from a project."""
        from tests.fixtures.factories import ProjectFactory, MemberFactory
        
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        
        # Add volunteer
        project.volunteers.append(member)
        db_session.commit()
        
        # Remove volunteer
        response = admin_client.post(
            f'/projects/{project.id}/volunteers/{member.id}/remove',
            follow_redirects=True
        )
        
        assert response.status_code == 200
        
        # Verify removal
        db_session.refresh(project)
        assert member not in project.volunteers
    
    def test_assign_project_leader(self, admin_client, organization, db_session):
        """Test assigning a project leader."""
        from tests.fixtures.factories import ProjectFactory, MemberFactory
        
        project = ProjectFactory(organization=organization)
        member = MemberFactory(organization=organization)
        db_session.commit()
        
        response = admin_client.post(f'/projects/{project.id}/leaders/add', data={
            'member_id': member.id,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify leadership assignment
        db_session.refresh(project)
        assert member in project.leaders


@pytest.mark.integration
class TestProjectStatus:
    """Integration tests for project status management."""
    
    def test_create_active_project(self, admin_client, organization, db_session):
        """Test creating an active project."""
        response = admin_client.post('/projects/new', data={
            'name': 'Active Project',
            'status': 'Active',
        }, follow_redirects=True)
        
        project = Project.query.filter_by(name='Active Project').first()
        assert project is not None
        assert project.status == 'Active'
    
    def test_complete_project(self, admin_client, organization, db_session):
        """Test marking a project as completed."""
        from tests.fixtures.factories import ProjectFactory
        
        project = ProjectFactory(
            organization=organization,
            status='Active'
        )
        db_session.commit()
        
        response = admin_client.post(f'/projects/{project.id}/edit', data={
            'name': project.name,
            'status': 'Completed',
            'end_date': date.today().isoformat(),
        }, follow_redirects=True)
        
        db_session.refresh(project)
        assert project.status == 'Completed'
    
    def test_filter_projects_by_status(self, authenticated_client, organization, db_session):
        """Test filtering projects by status."""
        from tests.fixtures.factories import ProjectFactory
        
        active_project = ProjectFactory(
            organization=organization,
            name='Active Project',
            status='Active'
        )
        completed_project = ProjectFactory(
            organization=organization,
            name='Completed Project',
            status='Completed'
        )
        db_session.commit()
        
        # Filter for active projects
        response = authenticated_client.get('/projects?status=Active')
        
        assert response.status_code == 200
        assert b'Active Project' in response.data


@pytest.mark.integration
class TestProjectDates:
    """Integration tests for project date management."""
    
    def test_project_end_date_after_start_date(self, admin_client, organization):
        """Test that project end date must be after start date."""
        start_date = date.today()
        end_date = start_date - timedelta(days=1)  # Invalid: before start
        
        response = admin_client.post('/projects/new', data={
            'name': 'Invalid Date Project',
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'status': 'Active',
        })
        
        # Should show validation error
        assert response.status_code in [200, 400]
    
    def test_project_dates_optional(self, admin_client, organization, db_session):
        """Test that project dates are optional."""
        response = admin_client.post('/projects/new', data={
            'name': 'No Dates Project',
            'status': 'Active',
        }, follow_redirects=True)
        
        project = Project.query.filter_by(name='No Dates Project').first()
        assert project is not None


@pytest.mark.integration
@pytest.mark.slow
def test_create_many_projects(admin_client, organization, db_session):
    """Test creating many projects (performance validation)."""
    from tests.fixtures.factories import ProjectFactory
    
    # Create 100 projects
    projects = ProjectFactory.create_batch(100, organization=organization)
    db_session.commit()
    
    # Verify all were created
    count = Project.query.filter_by(organization=organization).count()
    assert count >= 100
    
    # Verify projects list loads
    response = admin_client.get('/projects')
    assert response.status_code == 200

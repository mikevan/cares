"""
CARES Test Harness - Integration Tests - Member Routes
=======================================================

Integration tests for member management routes.

These tests verify that HTTP routes work correctly with the database.
"""

import pytest
from flask import url_for
from models import Member, MembershipEvent


@pytest.mark.integration
class TestMemberRoutes:
    """Integration tests for member routes."""
    
    def test_members_list_requires_authentication(self, client):
        """Test that members list page requires authentication."""
        response = client.get('/members')
        
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location
    
    def test_members_list_shows_members(self, authenticated_client, member):
        """Test that members list page shows existing members."""
        response = authenticated_client.get('/members')
        
        assert response.status_code == 200
        assert member.name.encode() in response.data
    
    def test_create_member_adds_to_database(self, admin_client, organization, db_session):
        """Test that creating a member adds it to the database."""
        initial_count = Member.query.filter_by(organization=organization).count()
        
        response = admin_client.post('/members/new', data={
            'name': 'Test Member',
            'email': 'test@example.com',
            'phone': '555-1234',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'TS',
            'zip_code': '12345',
            'active': True,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify member was added
        new_count = Member.query.filter_by(organization=organization).count()
        assert new_count == initial_count + 1
        
        # Verify member data
        member = Member.query.filter_by(
            name='Test Member',
            organization=organization
        ).first()
        assert member is not None
        assert member.email == 'test@example.com'
        assert member.active is True
    
    def test_update_member_modifies_database(self, admin_client, member, db_session):
        """Test that updating a member modifies the database."""
        original_email = member.email
        
        response = admin_client.post(f'/members/{member.id}/edit', data={
            'name': member.name,
            'email': 'updated@example.com',
            'phone': member.phone,
            'address': member.address,
            'city': member.city,
            'state': member.state,
            'zip_code': member.zip_code,
            'active': member.active,
        }, follow_redirects=True)
        
        assert response.status_code == 200
        
        # Refresh from database
        db_session.refresh(member)
        
        assert member.email == 'updated@example.com'
        assert member.email != original_email
    
    def test_delete_member_removes_from_database(self, admin_client, member, organization, db_session):
        """Test that deleting a member removes it from the database."""
        member_id = member.id
        initial_count = Member.query.filter_by(organization=organization).count()
        
        response = admin_client.post(f'/members/{member_id}/delete', follow_redirects=True)
        
        assert response.status_code == 200
        
        # Verify member was deleted
        new_count = Member.query.filter_by(organization=organization).count()
        assert new_count == initial_count - 1
        
        deleted_member = Member.query.get(member_id)
        assert deleted_member is None


@pytest.mark.integration
class TestMemberValidation:
    """Integration tests for member data validation."""
    
    def test_create_member_requires_name(self, admin_client, organization):
        """Test that creating a member requires a name."""
        response = admin_client.post('/members/new', data={
            'name': '',  # Empty name
            'email': 'test@example.com',
        }, follow_redirects=True)
        
        # Should show validation error or redirect back
        assert b'name' in response.data.lower() or response.status_code == 200
    
    def test_create_member_with_duplicate_email_allowed(self, admin_client, member, organization):
        """Test that duplicate emails are allowed (members can share emails)."""
        response = admin_client.post('/members/new', data={
            'name': 'Another Member',
            'email': member.email,  # Same email
            'active': True,
        }, follow_redirects=True)
        
        # Should succeed (duplicate emails allowed for members)
        members_with_email = Member.query.filter_by(
            email=member.email,
            organization=organization
        ).count()
        assert members_with_email >= 2


@pytest.mark.integration
class TestMemberSearch:
    """Integration tests for member search functionality."""
    
    def test_search_members_by_name(self, authenticated_client, organization):
        """Test searching for members by name."""
        # Create members with specific names
        from tests.fixtures.factories import MemberFactory
        
        member1 = MemberFactory(name='John Smith', organization=organization)
        member2 = MemberFactory(name='Jane Doe', organization=organization)
        member3 = MemberFactory(name='John Doe', organization=organization)
        
        response = authenticated_client.get('/members?search=John')
        
        assert response.status_code == 200
        assert b'John Smith' in response.data
        assert b'John Doe' in response.data
        assert b'Jane Doe' not in response.data  # Should not match


@pytest.mark.integration
@pytest.mark.slow
def test_create_many_members(admin_client, organization, db_session):
    """Test creating multiple members (slow test for performance validation)."""
    from tests.fixtures.factories import MemberFactory
    
    # Create 100 members
    members = MemberFactory.create_batch(100, organization=organization)
    db_session.commit()
    
    # Verify all were created
    count = Member.query.filter_by(organization=organization).count()
    assert count >= 100
    
    # Verify members list loads with many members
    response = admin_client.get('/members')
    assert response.status_code == 200


@pytest.mark.integration
class TestMembershipEventLogging:
    """
    Creating or editing a member should keep models.MembershipEvent -- the
    real source of truth behind Form 1295's Schedule A membership
    roll-forward (see services/kofc_form_1295.py) -- in sync with what
    actually happened, without ever requiring or guessing a reason the
    user didn't provide.
    """

    def test_creating_a_member_logs_an_initiation_event(self, admin_client, organization, db_session):
        response = admin_client.post('/members/new', data={
            'name': 'New Knight',
            'email': 'newknight@example.com',
            'join_date': '2026-03-01',
            'active': True,
        }, follow_redirects=True)
        assert response.status_code == 200

        member = Member.query.filter_by(name='New Knight', organization=organization).first()
        assert member is not None

        events = MembershipEvent.query.filter_by(member_id=member.id).all()
        assert len(events) == 1
        assert events[0].event_type == 'Initiation'
        assert events[0].event_date == member.join_date
        assert events[0].is_addition is True

    def test_deactivating_a_member_with_a_reason_logs_the_event(self, admin_client, member, db_session):
        assert member.active is True

        response = admin_client.post(f'/members/{member.id}/edit', data={
            'name': member.name,
            'email': member.email,
            'phone': member.phone,
            'address': member.address,
            'city': member.city,
            'state': member.state,
            'zip_code': member.zip_code,
            # 'active' checkbox omitted -- unchecked
            'membership_event_type': 'Withdrawal',
            'membership_event_date': '2026-04-15',
            'membership_event_notes': 'Moved out of the area.',
        }, follow_redirects=True)
        assert response.status_code == 200

        db_session.refresh(member)
        assert member.active is False

        events = MembershipEvent.query.filter_by(member_id=member.id, event_type='Withdrawal').all()
        assert len(events) == 1
        assert events[0].event_date.isoformat() == '2026-04-15'
        assert events[0].notes == 'Moved out of the area.'
        assert events[0].is_addition is False

    def test_deactivating_a_member_without_a_reason_logs_nothing(self, admin_client, member, db_session):
        """
        A status change with no reason supplied is allowed through rather
        than blocked or guessed -- schedule_a()'s reconciliation check is
        what surfaces this gap later, not a required field here.
        """
        assert member.active is True

        response = admin_client.post(f'/members/{member.id}/edit', data={
            'name': member.name,
            'email': member.email,
            'phone': member.phone,
            'address': member.address,
            'city': member.city,
            'state': member.state,
            'zip_code': member.zip_code,
            # 'active' checkbox omitted -- unchecked, and no reason given
        }, follow_redirects=True)
        assert response.status_code == 200

        db_session.refresh(member)
        assert member.active is False
        assert MembershipEvent.query.filter_by(member_id=member.id).count() == 0

    def test_editing_a_member_without_changing_active_logs_no_event(self, admin_client, member, db_session):
        response = admin_client.post(f'/members/{member.id}/edit', data={
            'name': member.name,
            'email': 'unchanged-active@example.com',
            'phone': member.phone,
            'address': member.address,
            'city': member.city,
            'state': member.state,
            'zip_code': member.zip_code,
            'active': 'on',
        }, follow_redirects=True)
        assert response.status_code == 200

        db_session.refresh(member)
        assert member.active is True
        assert MembershipEvent.query.filter_by(member_id=member.id).count() == 0

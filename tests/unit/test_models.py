"""
CARES Test Harness - Unit Tests - Models
=========================================

Unit tests for model business logic (no database required).

These tests use mocks and don't touch the database, making them very fast.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock
from datetime import date

from models import User, JournalEntry


# =============================================================================
# USER MODEL TESTS
# =============================================================================

@pytest.mark.unit
class TestUserModel:
    """Unit tests for User model methods."""
    
    def test_set_password_hashes_password(self):
        """Test that set_password creates a password hash."""
        user = User()
        user.set_password('testpass123')
        
        assert user.password_hash is not None
        assert user.password_hash != 'testpass123'
        assert len(user.password_hash) > 50  # Hashed passwords are long
    
    def test_check_password_validates_correct_password(self):
        """Test that check_password returns True for correct password."""
        user = User()
        user.set_password('testpass123')
        
        assert user.check_password('testpass123') is True
    
    def test_check_password_rejects_incorrect_password(self):
        """Test that check_password returns False for wrong password."""
        user = User()
        user.set_password('testpass123')
        
        assert user.check_password('wrongpass') is False
    
    def test_has_permission_admin_has_all_permissions(self):
        """Test that Admin role has all permissions."""
        user = User(role='Admin')
        
        assert user.has_permission('view_financials') is True
        assert user.has_permission('post_transactions') is True
        assert user.has_permission('any_permission') is True
    
    def test_has_permission_treasurer_has_financial_permissions(self):
        """Test that Treasurer has financial permissions."""
        user = User(role='Treasurer')
        
        assert user.has_permission('view_financials') is True
        assert user.has_permission('post_transactions') is True
        assert user.has_permission('generate_reports') is True
    
    def test_has_permission_member_has_limited_permissions(self):
        """Test that Member role has limited permissions."""
        user = User(role='Member')
        
        assert user.has_permission('view_dashboard') is True
        assert user.has_permission('view_profile') is True
        assert user.has_permission('post_transactions') is False


# =============================================================================
# JOURNAL ENTRY MODEL TESTS
# =============================================================================

@pytest.mark.unit
class TestJournalEntryModel:
    """Unit tests for JournalEntry model methods."""
    
    def test_is_balanced_returns_true_for_balanced_entry(self):
        """Test that is_balanced returns True for balanced entries."""
        # Create mock journal entry
        entry = JournalEntry()
        from types import SimpleNamespace
        line1 = SimpleNamespace(debit_amount=Decimal('100.00'), credit_amount=Decimal('0.00'))
        line2 = SimpleNamespace(debit_amount=Decimal('0.00'), credit_amount=Decimal('100.00'))
        lines = [line1, line2]
        assert entry.is_balanced(lines) is True
    
    def test_is_balanced_returns_false_for_unbalanced_entry(self):
        """Test that is_balanced returns False for unbalanced entries."""
        entry = JournalEntry()
        from types import SimpleNamespace
        line1 = SimpleNamespace(debit_amount=Decimal('100.00'), credit_amount=Decimal('0.00'))
        line2 = SimpleNamespace(debit_amount=Decimal('0.00'), credit_amount=Decimal('50.00'))
        lines = [line1, line2]
        assert entry.is_balanced(lines) is False
    
    def test_is_balanced_handles_rounding_errors(self):
        """Test that is_balanced handles small rounding differences."""
        entry = JournalEntry()
        from types import SimpleNamespace
        line1 = SimpleNamespace(debit_amount=Decimal('100.00'), credit_amount=Decimal('0.00'))
        line2 = SimpleNamespace(debit_amount=Decimal('0.00'), credit_amount=Decimal('100.005'))
        lines = [line1, line2]
        # Should still be considered balanced (difference < 0.01)
        assert entry.is_balanced(lines) is True
    
    def test_is_balanced_with_multiple_lines(self):
        """Test is_balanced with multiple debit and credit lines."""
        entry = JournalEntry()
        from types import SimpleNamespace
        lines = [
            SimpleNamespace(debit_amount=Decimal('100.00'), credit_amount=Decimal('0.00')),
            SimpleNamespace(debit_amount=Decimal('50.00'), credit_amount=Decimal('0.00')),
            SimpleNamespace(debit_amount=Decimal('0.00'), credit_amount=Decimal('75.00')),
            SimpleNamespace(debit_amount=Decimal('0.00'), credit_amount=Decimal('75.00')),
        ]
        # Total debits: 150, Total credits: 150
        assert entry.is_balanced(lines) is True


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

@pytest.mark.unit
def test_user_password_with_special_characters():
    """Test that passwords with special characters work correctly."""
    user = User()
    password = "p@$$w0rd!#123"
    
    user.set_password(password)
    
    assert user.check_password(password) is True
    assert user.check_password("wrong") is False


@pytest.mark.unit
def test_user_permission_with_unknown_role():
    """Test that unknown roles have no permissions."""
    user = User(role='UnknownRole')
    
    assert user.has_permission('view_financials') is False
    assert user.has_permission('any_permission') is False

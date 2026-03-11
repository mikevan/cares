"""
CARES Test Harness - Factory Boy Definitions
=============================================

Factory Boy factories for generating realistic test data.

Each factory:
- Creates instances with sensible defaults
- Uses Faker for realistic random data
- Handles relationships automatically
- Supports customization via parameters

Factories are automatically registered as pytest fixtures by conftest.py
"""

import factory
from factory import Faker, SubFactory, LazyAttribute, Sequence
from factory.alchemy import SQLAlchemyModelFactory
from datetime import datetime, date, timedelta
from decimal import Decimal
import uuid

# Import models
from models import (
    db, Organization, User, Member, Project,
    ChartOfAccounts, JournalEntry, JournalEntryLine,
    Donor, Donation, Vendor, Invoice
)


# =============================================================================
# BASE FACTORY
# =============================================================================

class BaseFactory(SQLAlchemyModelFactory):
    """Base factory with common configuration."""
    
    class Meta:
        abstract = True
        sqlalchemy_session = None  # Will be set by conftest.py
        sqlalchemy_session_persistence = 'flush'


# =============================================================================
# ORGANIZATION FACTORY
# =============================================================================

class OrganizationFactory(BaseFactory):
    """
    Factory for creating test organizations.
    
    Usage:
        # Default organization
        org = OrganizationFactory()
        
        # Custom organization
        org = OrganizationFactory(
            name="Council #12345",
            ein="12-3456789"
        )
    """
    
    class Meta:
        model = Organization
    
    name = Faker('company')
    org_type = 'Chapter'
    ein = Faker('ssn')  # Format: XXX-XX-XXXX
    address = Faker('street_address')
    city = Faker('city')
    state = Faker('state_abbr')
    zip_code = Faker('zipcode')
    phone = Faker('phone_number')
    email = Faker('company_email')
    website = Faker('url')
    fiscal_year_start = 1  # January
    created_at = LazyAttribute(lambda x: datetime.utcnow())
    updated_at = LazyAttribute(lambda x: datetime.utcnow())


# =============================================================================
# USER FACTORY
# =============================================================================

class UserFactory(BaseFactory):
    """
    Factory for creating test users.
    
    Usage:
        # Default user
        user = UserFactory(organization=org)
        
        # Admin user
        admin = UserFactory(role='Admin', organization=org)
        
        # With password
        user = UserFactory(organization=org)
        user.set_password('test123')
    """
    
    class Meta:
        model = User
    
    username = LazyAttribute(lambda x: f"testuser_{uuid.uuid4().hex}")
    email = Faker('email')
    role = 'Member'  # Default role
    organization = SubFactory(OrganizationFactory)
    active = True
    created_at = LazyAttribute(lambda x: datetime.utcnow())
    default_report_year = LazyAttribute(lambda x: datetime.utcnow().year)
    

    @classmethod
    def _build(cls, model_class, *args, **kwargs):
        """Override build to set password hash, but raise error to enforce create usage."""
        raise RuntimeError(
            "UserFactory: 'build' strategy is not allowed. Use 'create' to ensure password_hash is set."
        )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Remove 'uuid' and 'password' from kwargs if present
        kwargs.pop('uuid', None)
        password = kwargs.pop('password', None)
        # Ensure username uniqueness even if provided
        if 'username' in kwargs and kwargs['username']:
            # Append a unique suffix to any provided username
            kwargs['username'] = f"{kwargs['username']}_{uuid.uuid4().hex}"
        # Create the object without adding to session yet
        obj = model_class(*args, **kwargs)
        # Always set a password hash before adding to session
        if password:
            obj.set_password(password)
        else:
            obj.set_password('admin123')
        # Debug assertion: password_hash must be set
        assert obj.password_hash is not None and obj.password_hash != '', (
            f"UserFactory: password_hash was not set for user {getattr(obj, 'username', None)}!"
        )
        # Add to session and flush (not commit!)
        session = cls._meta.sqlalchemy_session
        if session is not None:
            session.add(obj)
            session.flush()
        return obj


# =============================================================================
# MEMBER FACTORY
# =============================================================================

class MemberFactory(BaseFactory):
    """
    Factory for creating test members.
    
    Usage:
        # Default member
        member = MemberFactory(organization=org)
        
        # Inactive member
        member = MemberFactory(
            organization=org,
            active=False
        )
        
        # With specific join date
        member = MemberFactory(
            organization=org,
            join_date=date(2020, 1, 1)
        )
    """
    
    class Meta:
        model = Member
    
    name = Faker('name')
    email = Faker('email')
    phone = Faker('phone_number')
    address = Faker('street_address')
    city = Faker('city')
    state = Faker('state_abbr')
    zip_code = Faker('zipcode')
    join_date = LazyAttribute(lambda x: date.today() - timedelta(days=365))
    active = True
    organization = SubFactory(OrganizationFactory)
    created_at = LazyAttribute(lambda x: datetime.utcnow())


# =============================================================================
# PROJECT FACTORY
# =============================================================================

class ProjectFactory(BaseFactory):
    """
    Factory for creating test projects.
    
    Usage:
        # Default project
        project = ProjectFactory(organization=org)
        
        # With specific budget
        project = ProjectFactory(
            organization=org,
            budget=Decimal('5000.00')
        )
        
        # Completed project
        project = ProjectFactory(
            organization=org,
            status='Completed',
            end_date=date.today()
        )
    """
    
    class Meta:
        model = Project
    
    name = Faker('catch_phrase')
    description = Faker('text', max_nb_chars=200)
    start_date = LazyAttribute(lambda x: date.today())
    end_date = LazyAttribute(lambda x: date.today() + timedelta(days=90))
    status = 'Active'
    budget = Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    organization = SubFactory(OrganizationFactory)
    created_at = LazyAttribute(lambda x: datetime.utcnow())


# =============================================================================
# CHART OF ACCOUNTS FACTORY
# =============================================================================

class AccountFactory(BaseFactory):
    """
    Factory for creating test chart of accounts entries.
    
    Note: In production, use ChartOfAccounts.initialize_standard_accounts()
    This factory is for testing custom accounts or additional accounts.
    
    Usage:
        # Asset account
        account = AccountFactory(
            account_type='Asset',
            normal_balance='Debit'
        )
        
        # Revenue account
        account = AccountFactory(
            account_type='Revenue',
            normal_balance='Credit'
        )
    """
    
    class Meta:
        model = ChartOfAccounts
    
    account_number = Sequence(lambda n: f'{9000 + n}')
    account_name = Faker('bs')
    account_type = 'Asset'
    account_subtype = 'Current Asset'
    normal_balance = 'Debit'
    active = True
    description = Faker('sentence')
    created_at = LazyAttribute(lambda x: datetime.utcnow())


# =============================================================================
# JOURNAL ENTRY FACTORY
# =============================================================================

class JournalEntryFactory(BaseFactory):
    """
    Factory for creating test journal entries.
    
    Creates a balanced journal entry with two lines (debit and credit).
    
    Usage:
        # Default entry
        entry = JournalEntryFactory(
            project=project,
            created_by=user.id
        )
        
        # Custom entry
        entry = JournalEntryFactory(
            project=project,
            created_by=user.id,
            description='Test transaction',
            entry_date=date.today()
        )
    """
    
    class Meta:
        model = JournalEntry
    
    entry_date = LazyAttribute(lambda x: date.today())
    description = Faker('sentence', nb_words=6)
    project = SubFactory(ProjectFactory)
    reference_number = Sequence(lambda n: f'REF-{n:05d}')
    @factory.lazy_attribute
    def created_by(self):
        user = UserFactory()
        return user.id

    @classmethod
    def _adjust_kwargs(cls, **kwargs):
        # Accept either a User object or an int for created_by
        created_by = kwargs.get('created_by')
        if created_by is not None:
            if hasattr(created_by, 'id'):
                kwargs['created_by'] = created_by.id
        return kwargs

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        kwargs = cls._adjust_kwargs(**kwargs)
        return super()._create(model_class, *args, **kwargs)
    created_at = LazyAttribute(lambda x: datetime.utcnow())
    status = 'Posted'
    
    @factory.post_generation
    def create_balanced_lines(obj, create, extracted, **kwargs):
        """Create balanced debit/credit lines after entry creation."""
        if not create:
            return
        
        # Get or create accounts
        cash_account = ChartOfAccounts.query.filter_by(
            account_number='1000'
        ).first()
        revenue_account = ChartOfAccounts.query.filter_by(
            account_number='4000'
        ).first()
        
        if not cash_account or not revenue_account:
            # Skip if accounts not initialized
            return
        
        amount = Decimal('100.00')
        
        # Debit line
        debit_line = JournalEntryLine(
            journal_entry=obj,
            account=cash_account,
            debit_amount=amount,
            credit_amount=Decimal('0.00'),
            memo='Test debit'
        )
        
        # Credit line
        credit_line = JournalEntryLine(
            journal_entry=obj,
            account=revenue_account,
            debit_amount=Decimal('0.00'),
            credit_amount=amount,
            memo='Test credit'
        )
        
        db.session.add(debit_line)
        db.session.add(credit_line)


# =============================================================================
# JOURNAL ENTRY LINE FACTORY
# =============================================================================

class JournalEntryLineFactory(BaseFactory):
    """
    Factory for creating individual journal entry lines.
    
    Usage:
        # Debit line
        line = JournalEntryLineFactory(
            journal_entry=entry,
            account=account,
            debit_amount=Decimal('100.00'),
            credit_amount=Decimal('0.00')
        )
        
        # Credit line
        line = JournalEntryLineFactory(
            journal_entry=entry,
            account=account,
            debit_amount=Decimal('0.00'),
            credit_amount=Decimal('100.00')
        )
    """
    
    class Meta:
        model = JournalEntryLine
    
    journal_entry = SubFactory(JournalEntryFactory)
    account = SubFactory(AccountFactory)
    debit_amount = Decimal('0.00')
    credit_amount = Decimal('0.00')
    memo = Faker('sentence', nb_words=4)


# =============================================================================
# DONOR FACTORY (Optional - for donation tracking)
# =============================================================================

class DonorFactory(BaseFactory):
    """
    Factory for creating test donors.
    
    Usage:
        donor = DonorFactory()
    """
    
    class Meta:
        model = Donor
    
    name = Faker('name')
    email = Faker('email')
    phone = Faker('phone_number')
    address = Faker('street_address')
    city = Faker('city')
    state = Faker('state_abbr')
    zip_code = Faker('zipcode')
    tax_id = Faker('ssn')
    donor_type = 'Individual'
    created_at = LazyAttribute(lambda x: datetime.utcnow())

# =============================================================================
# VENDOR FACTORY
# =============================================================================

class VendorFactory(BaseFactory):
    class Meta:
        model = Vendor

    name = Faker('company')
    contact_name = Faker('name')
    email = Faker('company_email')
    phone = Faker('phone_number')
    address = Faker('street_address')
    city = Faker('city')
    state = Faker('state_abbr')
    zip_code = Faker('zipcode')
    payment_terms = 'Net30'
    is_1099 = False
    active = True
    organization = SubFactory(OrganizationFactory)
    created_at = LazyAttribute(lambda x: datetime.utcnow())


# =============================================================================
# INVOICE FACTORY
# =============================================================================

class InvoiceFactory(BaseFactory):
    class Meta:
        model = Invoice

    organization = SubFactory(OrganizationFactory)
    vendor = SubFactory(VendorFactory)
    project = SubFactory(ProjectFactory)
    gl_account_id = 1  # Override in tests with a real account id
    invoice_number = Sequence(lambda n: f'INV-{n:05d}')
    invoice_date = LazyAttribute(lambda x: date.today())
    due_date = LazyAttribute(lambda x: date.today() + timedelta(days=30))
    amount = Faker('pydecimal', left_digits=4, right_digits=2, positive=True)
    amount_paid = Decimal('0.00')
    status = 'Open'
    created_by = 1  # Override in tests with a real user id
    created_at = LazyAttribute(lambda x: datetime.utcnow())
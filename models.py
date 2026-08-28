"""
CARES - Community Accounting & Resource Engagement System - Database Models
FASB ASC 958 Compliant Double-Entry Accounting
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import event as sa_event
from sqlalchemy.dialects.postgresql import JSONB
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from decimal import Decimal

db = SQLAlchemy()


# ==================== ORGANIZATION & USERS ====================


class Organization(db.Model):
    """Organization/Chapter information"""
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    org_type = db.Column(db.String(50), default='Chapter')
    ein = db.Column(db.String(20))
    # Knights of Columbus council identity -- used to fill in the
    # header of Form 1295 and to route it (see Form1295Submission
    # below). Optional/blank for any non-KofC deployment.
    council_number = db.Column(db.String(20))
    district_deputy_name = db.Column(db.String(200))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(200))
    website = db.Column(db.String(200))
    fiscal_year_start = db.Column(db.Integer, default=1)
    css_file = db.Column(db.String(100), nullable=True)
    dues_amount = db.Column(db.Numeric(12, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    children = db.relationship('Organization', backref=db.backref('parent', remote_side=[id]))
    users = db.relationship('User', backref='organization', lazy='dynamic')
    members = db.relationship('Member', backref='organization', lazy='dynamic')
    projects = db.relationship('Project', backref='organization', lazy='dynamic')


class User(UserMixin, db.Model):
    """System users with role-based access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    default_report_year = db.Column(db.Integer, nullable=True)
    # Forces a redirect to the change-password page on next login until
    # cleared. Set True whenever a password is assigned by someone other
    # than the user themself (the seeded default admin account above all).
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        permissions = {
            'Admin': ['all'],
            'Treasurer': ['view_financials', 'post_transactions', 'generate_reports'],
            'ProjectLeader': ['view_projects', 'submit_expenses'],
            'Membership Coordinator': ['view_members', 'manage_dues'],
            'Member': ['view_dashboard', 'view_profile']
        }
        role_perms = permissions.get(self.role, [])
        return 'all' in role_perms or permission in role_perms


class Member(db.Model):
    """Volunteer and member directory"""
    __tablename__ = 'members'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    join_date = db.Column(db.Date, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Knights of Columbus Form 1295 Schedule A is a membership ROLL-FORWARD --
# start-of-period count, plus categorized additions, minus categorized
# deductions, equals end-of-period count -- not a snapshot. A plain
# active/inactive flag can't reconstruct that, so every status change
# that matters for the schedule gets its own logged event instead.
#
# The real Form 1295 lists 'Transfers -- assoc. to insurance' and
# 'Transfers -- ins. to associate' under BOTH the additions and
# deductions columns -- that's the paper form using one generic label
# in both places as a template, not two ambiguous categories. Since
# what actually matters is whether a given transfer added or removed a
# member from the active-associate count, this app splits it into two
# unambiguous, strictly-directional event types instead of reproducing
# the paper form's ambiguity.
MEMBERSHIP_EVENT_ADDITION_TYPES = [
    'Initiation',
    'Transfer In (from another council)',
    'Re-entry',
    'Transfer from Insurance to Associate',
]

MEMBERSHIP_EVENT_DEDUCTION_TYPES = [
    'Suspension',
    'Death',
    'Withdrawal',
    'Transfer Out (to another council)',
    'Transfer from Associate to Insurance',
]

MEMBERSHIP_EVENT_TYPES = MEMBERSHIP_EVENT_ADDITION_TYPES + MEMBERSHIP_EVENT_DEDUCTION_TYPES


class MembershipEvent(db.Model):
    """One logged membership status change -- an initiation, a transfer,
    a suspension, and so on. This is the real source of truth Form
    1295's Schedule A roll-forward is computed from (see
    services/kofc_form_1295.py::schedule_a); Member.active is kept in
    sync with it (see blueprints/member_routes.py) but is a derived
    convenience flag, not the record of why or when a status changed."""
    __tablename__ = 'membership_events'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    member = db.relationship('Member', backref=db.backref('membership_events', order_by='MembershipEvent.event_date'))

    @property
    def is_addition(self):
        return self.event_type in MEMBERSHIP_EVENT_ADDITION_TYPES


class MemberDuesPayment(db.Model):
    """Tracks annual dues payments per member per year"""
    __tablename__ = 'member_dues_payments'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    paid_date = db.Column(db.Date, nullable=True)
    include_in_transaction = db.Column(db.Boolean, default=True, nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    member = db.relationship('Member', backref='dues_payments')
    journal_entry = db.relationship('JournalEntry')

    __table_args__ = (
        db.UniqueConstraint('member_id', 'year', name='uq_member_dues_year'),
    )

    @property
    def is_paid(self):
        return self.paid_date is not None


class Form1295Submission(db.Model):
    """The parts of Knights of Columbus Form 1295 that CARES cannot
    compute from the ledger, because they're narrative or
    administrative rather than financial: an explanation for any
    non-zero 'miscellaneous/other' line, and an in-app attestation
    that someone reviewed and finalized the schedules for a given
    period. This table is on the audit trail's AUDITED_TABLES list
    (see audit_schema.py) like everything else in this app, so a
    change to a saved explanation or a re-attestation is itself a
    tamper-evident record -- a stronger signature story than a wet
    signature on paper, not a weaker one.

    Deliberately does NOT duplicate any calculated figure from
    services/kofc_form_1295.py -- those numbers come from the ledger
    every time the report is viewed and are never stored (and
    therefore never editable) here."""
    __tablename__ = 'form_1295_submissions'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    # Schedule B Financial Secretary side: 'Cash received from other
    # sources: (Explain kind and amount)'.
    misc_income_explanation = db.Column(db.Text)
    # Schedule C liabilities: the miscellaneous/other liabilities line.
    misc_liabilities_explanation = db.Column(db.Text)
    attested_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    attested_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = db.relationship('Organization')
    attested_by = db.relationship('User')

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'period_start', 'period_end', name='uq_form1295_org_period'),
    )

    @property
    def is_attested(self):
        return self.attested_at is not None


PROJECT_ASSIGNMENT_ROLES = ['Leader', 'Volunteer']

PROJECT_ASSIGNMENT_END_REASONS = [
    'Resigned',
    'Dismissed',
    'Term Completed',
    'Replaced',
    'Project Cancelled',
]


class ProjectAssignment(db.Model):
    """History of who has served on a project, in what role, and why it ended.

    This is the single source of truth for project leadership/volunteer
    history. A "current" assignment is simply a row where end_date IS NULL --
    there is no separate flag to keep in sync. Nothing should write directly
    to this table except services/project_service.py.
    """
    __tablename__ = 'project_assignments'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'Leader' or 'Volunteer'

    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    end_reason = db.Column(db.String(50), nullable=True)  # see PROJECT_ASSIGNMENT_END_REASONS
    end_notes = db.Column(db.Text, nullable=True)

    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ended_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project = db.relationship('Project', backref=db.backref('assignments', lazy='dynamic'))
    member = db.relationship('Member', foreign_keys=[member_id], backref='project_assignments')
    assigned_by_user = db.relationship('User', foreign_keys=[assigned_by])
    ended_by_user = db.relationship('User', foreign_keys=[ended_by])

    @property
    def is_active(self):
        return self.end_date is None


class Project(db.Model):
    """Programs and initiatives with budgets"""
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='Active')
    budget = db.Column(db.Numeric(12, 2), default=0.00)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    # Flags a project as a fundraiser (vs. an ordinary program/expense
    # activity) so the Knights of Columbus Form 1295 Schedule B report
    # (see services/kofc_form_1295.py) can identify "the two largest
    # fundraisers by name" for a given audit period without guessing from
    # the project name or account activity.
    is_fundraiser = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Self-referential link: each year's re-run of a recurring project (e.g.
    # an annual fundraiser) is created as its own Project row, chained back
    # to the prior year's row, rather than mutating one Project in place.
    previous_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    previous_project = db.relationship(
        'Project', remote_side=[id],
        backref=db.backref('next_project', uselist=False)
    )

    journal_entries = db.relationship('JournalEntry', backref='project', lazy='dynamic')

    def _active_assignments_query(self, role=None):
        query = self.assignments.filter(ProjectAssignment.end_date.is_(None))
        if role:
            query = query.filter(ProjectAssignment.role == role)
        return query

    @property
    def leaders(self):
        """Members currently leading this project.

        Read-only -- use services/project_service.py to assign or end a
        leadership term. Kept as a property (instead of a relationship) so
        existing templates/queries that iterate project.leaders keep working
        unchanged even though leadership is now tracked via ProjectAssignment
        history rather than a plain many-to-many table.
        """
        return [a.member for a in self._active_assignments_query('Leader').all()]

    @property
    def volunteers(self):
        """Members currently volunteering on this project. Read-only -- see leaders above."""
        return [a.member for a in self._active_assignments_query('Volunteer').all()]

    @property
    def active_assignments(self):
        """All current (not-yet-ended) assignments, leaders and volunteers alike."""
        return self._active_assignments_query().all()


class ChartOfAccounts(db.Model):
    """FASB ASC 958 compliant Chart of Accounts"""
    __tablename__ = 'chart_of_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(10), nullable=False, unique=True)
    account_name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)
    account_subtype = db.Column(db.String(100))
    normal_balance = db.Column(db.String(10), nullable=False)
    active = db.Column(db.Boolean, default=True)
    parent_account_id = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.id'))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sub_accounts = db.relationship('ChartOfAccounts', backref=db.backref('parent_account', remote_side=[id]))
    journal_lines = db.relationship('JournalEntryLine', backref='account', lazy='dynamic')


class JournalEntry(db.Model):
    """Master transaction table"""
    __tablename__ = 'journal_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(500), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    reference_number = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Posted')
    
    lines = db.relationship('JournalEntryLine', backref='journal_entry', 
                           lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', backref='journal_entries')
    
    def is_balanced(self, lines=None):
        """Return True if debits and credits are balanced. Accepts optional lines for testing."""
        if lines is None:
            lines = self.lines
        total_debits = sum(line.debit_amount for line in lines)
        total_credits = sum(line.credit_amount for line in lines)
        return abs(total_debits - total_credits) < Decimal('0.01')


class JournalEntryLine(db.Model):
    """Individual debit/credit lines"""
    __tablename__ = 'journal_entry_lines'
    
    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.id'), nullable=False)
    debit_amount = db.Column(db.Numeric(12, 2), default=0.00)
    credit_amount = db.Column(db.Numeric(12, 2), default=0.00)
    memo = db.Column(db.String(500))


class Donor(db.Model):
    """Donor tracking"""
    __tablename__ = 'donors'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    tax_id = db.Column(db.String(20))
    donor_type = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    donations = db.relationship('Donation', backref='donor', lazy='dynamic')


class Donation(db.Model):
    """Links donors to journal entries"""
    __tablename__ = 'donations'
    
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('donors.id'), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    donation_type = db.Column(db.String(50))
    restriction = db.Column(db.String(100))
    is_tax_deductible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    journal_entry = db.relationship('JournalEntry', backref='donations')


class Currency(db.Model):
    """Multi-currency support"""
    __tablename__ = 'currencies'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(3), nullable=False, unique=True)
    symbol = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== ACCOUNTS PAYABLE ====================

class Vendor(db.Model):
    """Vendor/supplier directory for accounts payable"""
    __tablename__ = 'vendors'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    payment_terms = db.Column(db.String(50), default='Net30')
    is_1099 = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship('Invoice', backref='vendor', lazy='dynamic')


class Invoice(db.Model):
    """Vendor invoices — accounts payable"""
    __tablename__ = 'invoices'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendors.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    gl_account_id = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.id'), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))
    invoice_number = db.Column(db.String(100))
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    amount_paid = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    status = db.Column(db.String(20), default='Open')
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship('InvoicePayment', backref='invoice', lazy='dynamic',
                               cascade='all, delete-orphan')
    gl_account = db.relationship('ChartOfAccounts')
    journal_entry = db.relationship('JournalEntry')

    @property
    def amount_due(self):
        return (self.amount or Decimal('0.00')) - (self.amount_paid or Decimal('0.00'))

    @property
    def days_outstanding(self):
        if self.status in ('Paid', 'Voided'):
            return 0
        return (date.today() - self.due_date).days

    @property
    def aging_bucket(self):
        days = self.days_outstanding
        if days <= 0:
            return 'Current'
        elif days <= 30:
            return '1-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        return '90+'


class InvoicePayment(db.Model):
    """Payments applied against a vendor invoice"""
    __tablename__ = 'invoice_payments'

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ==================== ACCOUNTS RECEIVABLE ====================

# Receivable.receivable_type -- which body of guidance governs the row.
#
#   Exchange     The organization gave something and is owed payment: program
#                fees, hall rental, billed event tickets. Ordinary ASC 606
#                revenue. Recognized when earned; a receivable exists at once.
#   Contribution A donor promised money (a pledge). ASC 958-605. Recognized
#                only when UNCONDITIONAL -- see is_conditional below.
#   Grant        A grantor committed funding. Usually a conditional
#                contribution (a barrier plus a right of return), occasionally
#                an exchange transaction. Same conditional test applies.
#   Assessment   One organization billing another inside this deployment --
#                a state or regional council charging its chapters per capita.
#                See counterparty_organization_id.
RECEIVABLE_TYPES = ['Exchange', 'Contribution', 'Grant', 'Assessment']

# Net asset classification carried by the revenue this receivable recognizes.
# A promise collectible in a future period carries an implied TIME restriction
# even when the donor attached no purpose restriction -- which is why the
# time option exists separately from purpose.
RECEIVABLE_RESTRICTIONS = [
    'Without Donor Restrictions',
    'With Donor Restrictions - Purpose',
    'With Donor Restrictions - Time',
]

RECEIVABLE_STATUSES = ['Conditional', 'Open', 'Partial', 'Paid', 'Written Off', 'Voided']


class Payer(db.Model):
    """Someone who owes the organization money.

    Accounts receivable's counterpart to Vendor. A payer is deliberately a
    real row rather than the free-text name this table used to carry, because
    aging, statements and collection history are all per-payer and none of
    them work against a string that is spelled three different ways.

    counterparty_organization_id is what makes a state or regional council
    possible: when the payer IS another organization in this deployment (a
    chapter being billed per capita), that link is how the two sides of the
    transaction find each other. Null for ordinary external payers.
    """
    __tablename__ = 'payers'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    payer_type = db.Column(db.String(50), default='Individual')
    contact_name = db.Column(db.String(200))
    email = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    payment_terms = db.Column(db.String(50), default='Net30')
    counterparty_organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'),
                                              nullable=True)
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', foreign_keys=[organization_id])
    counterparty_organization = db.relationship('Organization',
                                                 foreign_keys=[counterparty_organization_id])

    @property
    def is_affiliated_organization(self):
        return self.counterparty_organization_id is not None


class Receivable(db.Model):
    """Amounts owed to the organization.

    Covers both things a nonprofit calls a receivable, which are not the same
    thing and must not be treated as one:

      an EXCHANGE receivable, where the organization delivered something and
      is owed payment; and

      a PROMISE TO GIVE, where a donor or grantor has committed money. Under
      ASC 958-605 an unconditional promise is recognized as revenue and an
      asset immediately, while a CONDITIONAL promise -- one with a measurable
      performance barrier and a right of return or release -- is recognized as
      NOTHING until that barrier is substantially met. Booking a conditional
      grant the day the award letter arrives is the single most common way a
      nonprofit overstates its assets, so this model refuses to post one: a
      conditional row carries status 'Conditional', has no journal entry, and
      appears on no balance sheet until recognize() is called.

    Amounts collectible beyond one year are discounted to present value; the
    face amount stays on `amount`, the recognized amount on `present_value`,
    and the difference sits in a contra-asset account that unwinds to
    contribution revenue over the collection period. See PledgeInstallment.
    """
    __tablename__ = 'receivables'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    gl_account_id = db.Column(db.Integer, db.ForeignKey('chart_of_accounts.id'), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('payers.id'), nullable=True)
    # Retained: rows created before payers existed, and a display fallback.
    payer_name = db.Column(db.String(200), nullable=False)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)

    invoice_number = db.Column(db.String(100))
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    amount_received = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    status = db.Column(db.String(20), default='Open')
    notes = db.Column(db.Text)

    # ---- ASC 958 ----------------------------------------------------------
    receivable_type = db.Column(db.String(20), default='Exchange', nullable=False)
    restriction = db.Column(db.String(40), default='Without Donor Restrictions')
    is_conditional = db.Column(db.Boolean, default=False, nullable=False)
    condition_description = db.Column(db.Text)
    condition_met_date = db.Column(db.Date, nullable=True)

    # ---- Present value (multi-year promises) -------------------------------
    discount_rate = db.Column(db.Numeric(6, 4), nullable=True)
    present_value = db.Column(db.Numeric(12, 2), nullable=True)
    discount_unamortized = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))

    # ---- Collectibility ----------------------------------------------------
    allowance_amount = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    written_off_date = db.Column(db.Date, nullable=True)

    # ---- Inter-organization billing ---------------------------------------
    # Set when this receivable is one organization billing another in this
    # same deployment. counterparty_invoice_id is the AP invoice posted into
    # the other organization's books, so the pairing is auditable from either
    # side rather than being inferred from matching amounts and dates.
    counterparty_organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'),
                                              nullable=True)
    counterparty_invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payer = db.relationship('Payer', backref='receivables')
    journal_entry = db.relationship('JournalEntry', foreign_keys=[journal_entry_id])
    organization = db.relationship('Organization', foreign_keys=[organization_id])
    counterparty_organization = db.relationship('Organization',
                                                 foreign_keys=[counterparty_organization_id])
    counterparty_invoice = db.relationship('Invoice', foreign_keys=[counterparty_invoice_id])

    ar_payments = db.relationship('ReceivablePayment', backref='receivable', lazy='dynamic',
                                  cascade='all, delete-orphan')
    installments = db.relationship('PledgeInstallment', backref='receivable', lazy='dynamic',
                                    cascade='all, delete-orphan',
                                    order_by='PledgeInstallment.due_date')

    @property
    def amount_due(self):
        return (self.amount or Decimal('0.00')) - (self.amount_received or Decimal('0.00'))

    @property
    def recognized_amount(self):
        """What actually hit the books. A discounted promise is recognized at
        present value, not face; a conditional promise at nothing at all."""
        if self.is_recognized is False:
            return Decimal('0.00')
        if self.present_value is not None:
            return self.present_value
        return self.amount or Decimal('0.00')

    @property
    def is_recognized(self):
        """False while a conditional promise's barrier is unmet -- no asset,
        no revenue, no journal entry, disclosure only."""
        if not self.is_conditional:
            return True
        return self.condition_met_date is not None

    @property
    def carrying_amount(self):
        """Balance-sheet value: face, less the unamortized discount, less the
        allowance for the portion not expected to be collected."""
        if not self.is_recognized:
            return Decimal('0.00')
        return (self.amount_due
                - (self.discount_unamortized or Decimal('0.00'))
                - (self.allowance_amount or Decimal('0.00')))

    @property
    def days_outstanding(self):
        if self.status in ('Paid', 'Voided', 'Written Off', 'Conditional'):
            return 0
        return (date.today() - self.due_date).days

    @property
    def aging_bucket(self):
        days = self.days_outstanding
        if days <= 0:
            return 'Current'
        elif days <= 30:
            return '1-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        return '90+'


class PledgeInstallment(db.Model):
    """One scheduled payment of a multi-year promise to give.

    A five-year $50,000 pledge is not a $50,000 receivable. Each installment
    is discounted to present value from its own due date, and the difference
    between face and present value unwinds to contribution revenue as the
    date approaches -- which is why the discount is tracked per installment
    rather than once on the parent.
    """
    __tablename__ = 'pledge_installments'

    id = db.Column(db.Integer, primary_key=True)
    receivable_id = db.Column(db.Integer, db.ForeignKey('receivables.id'), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    present_value = db.Column(db.Numeric(12, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    discount_amortized = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    amount_received = db.Column(db.Numeric(12, 2), default=Decimal('0.00'))
    status = db.Column(db.String(20), default='Scheduled')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('receivable_id', 'sequence', name='uq_pledge_installment_seq'),
    )

    @property
    def discount_remaining(self):
        return (self.discount_amount or Decimal('0.00')) - (self.discount_amortized or Decimal('0.00'))


class ReceivablePayment(db.Model):
    """Payments received against a receivable"""
    __tablename__ = 'receivable_payments'

    id = db.Column(db.Integer, primary_key=True)
    receivable_id = db.Column(db.Integer, db.ForeignKey('receivables.id'), nullable=False)
    installment_id = db.Column(db.Integer, db.ForeignKey('pledge_installments.id'), nullable=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    reference_number = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    installment = db.relationship('PledgeInstallment', backref='payments')


# ==================== TRANSLATION CACHE ====================

class TranslationCache(db.Model):
    """Cache for AI-translated page HTML. Survives demo reloads."""
    __tablename__ = 'translation_cache'

    id              = db.Column(db.Integer, primary_key=True)
    route           = db.Column(db.String(500), nullable=False)
    language_code   = db.Column(db.String(10),  nullable=False)
    content_hash    = db.Column(db.String(16),   nullable=False)
    translated_html = db.Column(db.Text,          nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            'route', 'language_code', 'content_hash',
            name='uq_translation_cache'
        ),
    )


# ==================== USAGE / BILLING TELEMETRY ====================

class UsageEvent(db.Model):
    """
    Lightweight usage telemetry, recorded at a handful of key gateway
    points (login, journal entry posted, invoice created, report
    generated). Exists so a vendor operating this app for multiple chapters
    has real usage data -- active organizations, activity per org, which
    features actually get used -- to inform how to bill for it, before
    picking a pricing model rather than after.

    Written only through services/usage_service.py::log_event(), which is
    deliberately best-effort: a failure recording telemetry must never
    break the real action it's recording (posting a journal entry, logging
    in, etc.).
    """
    __tablename__ = 'usage_events'

    id              = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    event_type      = db.Column(db.String(50), nullable=False)  # e.g. 'auth.login', 'journal_entry.posted'
    event_meta      = db.Column(db.JSON, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    organization = db.relationship('Organization')
    user = db.relationship('User')
# ==================== AUDIT TRAIL ====================

class AuditLog(db.Model):
    """
    Tamper-evident, append-only record of every INSERT/UPDATE/DELETE on
    every financial and access-control table in the system -- who changed
    what, when, and the full before/after state of the row.

    This exists so a council's trustees (Knights of Columbus Section 145
    requires them to audit the financial secretary's and treasurer's books
    at least every six months) and, if it ever comes to it, a forensic
    accountant can reconstruct exactly what happened to the books, even if
    someone with legitimate database access tries to edit or delete
    records to cover their tracks.

    Every row here is written EXCLUSIVELY by the audit_trigger_fn()
    Postgres trigger defined in audit_schema.py, attached to every table
    in AUDITED_TABLES -- never by this ORM class. That's deliberate and
    load-bearing: a trigger fires no matter how a row was changed (through
    the app, a script, or someone with a raw psql prompt), where an
    application-level hook could simply be bypassed by whoever the threat
    actually is. The before_insert/before_update/before_delete guard below
    makes sure nothing in this codebase quietly starts writing to this
    table through the ORM instead and losing that guarantee.

    Two more properties matter as much as capture:
      - The database role the app connects as in production is granted
        INSERT and SELECT on this table only -- never UPDATE, DELETE, or
        TRUNCATE (see audit_schema.py::grant_restricted_runtime_role).
        Even a SQL-injection bug or a treasurer with the app's own DB
        credentials cannot rewrite history.
      - Every row's row_hash is a SHA-256 of its own contents chained to
        the previous row's row_hash (prev_hash), computed and verified
        under a single advisory lock so concurrent writes can't fork the
        chain. Editing or deleting even one row -- however it's done --
        breaks the chain from that point forward, and that break is
        independently verifiable by anyone with read access, without
        having to trust the database's own guarantees.

    See AUDIT_TRAIL.md for the full design and required production
    setup (the restricted role above is a manual psql step, not something
    an app deploy can do to itself).
    """
    __tablename__ = 'audit_log'

    id = db.Column(db.BigInteger, primary_key=True)
    table_name = db.Column(db.String(64), nullable=False)
    row_id = db.Column(db.Integer, nullable=True)
    operation = db.Column(db.String(10), nullable=False)
    # JSONB specifically (not the generic db.JSON, which compiles to a
    # plain json column on Postgres) -- the trigger function builds these
    # with to_jsonb() and this needs to match exactly what audit_schema.py
    # and the trustee audit report's queries assume.
    old_data = db.Column(JSONB, nullable=True)
    new_data = db.Column(JSONB, nullable=True)
    # No ForeignKey to users.id on purpose: a user row can itself be
    # deleted or changed later, and this column must keep whatever value
    # the trigger captured at the time regardless of what happens to that
    # user afterward.
    changed_by_user_id = db.Column(db.Integer, nullable=True)
    db_role = db.Column(db.String(64), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False)
    prev_hash = db.Column(db.String(64), nullable=True)
    row_hash = db.Column(db.String(64), nullable=False)

    __table_args__ = (
        db.CheckConstraint("operation IN ('INSERT','UPDATE','DELETE')", name='ck_audit_log_operation'),
        db.Index('idx_audit_log_table_row', 'table_name', 'row_id'),
        db.Index('idx_audit_log_changed_at', 'changed_at'),
        db.Index('idx_audit_log_changed_by', 'changed_by_user_id'),
    )


def _forbid_orm_writes_to_audit_log(mapper, connection, target):
    raise RuntimeError(
        "AuditLog rows must never be written through the ORM -- only "
        "audit_trigger_fn() (see audit_schema.py) writes this table. If "
        "you're hitting this, something tried to db.session.add()/"
        "delete() an AuditLog row directly; let the database trigger "
        "capture the change on the real table you're modifying instead."
    )


sa_event.listen(AuditLog, 'before_insert', _forbid_orm_writes_to_audit_log)
sa_event.listen(AuditLog, 'before_update', _forbid_orm_writes_to_audit_log)
sa_event.listen(AuditLog, 'before_delete', _forbid_orm_writes_to_audit_log)

"""
CARES - Community Accounting & Resource Engagement System - Database Models
FASB ASC 958 Compliant Double-Entry Accounting
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
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
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(20))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(200))
    website = db.Column(db.String(200))
    fiscal_year_start = db.Column(db.Integer, default=1)
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
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        permissions = {
            'Admin': ['all'],
            'Treasurer': ['view_financials', 'post_transactions', 'generate_reports'],
            'ProjectLeader': ['view_projects', 'submit_expenses'],
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


project_members = db.Table('project_members',
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    db.Column('member_id', db.Integer, db.ForeignKey('members.id'), primary_key=True)
)

project_leaders = db.Table('project_leaders',
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    db.Column('member_id', db.Integer, db.ForeignKey('members.id'), primary_key=True)
)


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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    volunteers = db.relationship('Member', secondary=project_members, 
                                backref=db.backref('projects', lazy='dynamic'))
    leaders = db.relationship('Member', secondary=project_leaders,
                             backref=db.backref('led_projects', lazy='dynamic'))
    journal_entries = db.relationship('JournalEntry', backref='project', lazy='dynamic')


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

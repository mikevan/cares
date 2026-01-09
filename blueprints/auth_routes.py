"""
Authentication Blueprint
Handles authentication routes and initialization
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Organization, Project, ChartOfAccounts
from datetime import datetime

# Create the blueprint
auth_bp = Blueprint('auth', __name__)


# ==================== AUTHENTICATION ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout handler"""
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login'))


def init_database(app):
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()
        
        # Create default organization if none exists
        if not Organization.query.first():
            org = Organization(
                name=app.config.get('DEFAULT_ORGANIZATION', 'CARES - Example Chapter'),
                org_type='Chapter',
                fiscal_year_start=1
            )
            db.session.add(org)
            db.session.commit()
        
        # Create default admin user if none exists
        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@example.com',
                role='Admin',
                organization_id=1
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
        
        # Create default Dues project if it doesn't exist
        if not Project.query.filter_by(name='Dues').first():
            dues_project = Project(
                name='Dues',
                description='Member dues and subscription payments',
                status='Active',
                organization_id=1
            )
            db.session.add(dues_project)
            db.session.commit()
        
        # Create default Chart of Accounts if empty
        if ChartOfAccounts.query.count() == 0:
            default_accounts = [
                # Assets
                ('1010', 'Operating Checking Account', 'Asset', 'Cash', 'Debit'),
                ('1020', 'Savings Account', 'Asset', 'Cash', 'Debit'),
                ('1030', 'Petty Cash', 'Asset', 'Cash', 'Debit'),
                ('1210', 'Accounts Receivable', 'Asset', 'Receivables', 'Debit'),
                ('1510', 'Land', 'Asset', 'Fixed Assets', 'Debit'),
                ('1520', 'Buildings', 'Asset', 'Fixed Assets', 'Debit'),
                ('1530', 'Equipment & Furnishings', 'Asset', 'Fixed Assets', 'Debit'),
                ('1590', 'Accumulated Depreciation', 'Asset', 'Contra-Asset', 'Credit'),
                
                # Liabilities
                ('2010', 'Accounts Payable', 'Liability', 'Current Liability', 'Credit'),
                ('2020', 'Credit Card Payable', 'Liability', 'Current Liability', 'Credit'),
                ('2110', 'Accrued Salaries', 'Liability', 'Accrued Liability', 'Credit'),
                ('2510', 'Long-term Loans Payable', 'Liability', 'Long-term Liability', 'Credit'),
                
                # Net Assets
                ('3100', 'Net Assets Without Donor Restrictions', 'Net Asset', 'Unrestricted', 'Credit'),
                ('3200', 'Net Assets With Donor Restrictions - Time', 'Net Asset', 'Restricted', 'Credit'),
                ('3210', 'Net Assets With Donor Restrictions - Purpose', 'Net Asset', 'Restricted', 'Credit'),
                
                # Revenue
                ('4010', 'Individual Contributions', 'Revenue', 'Contributions', 'Credit'),
                ('4020', 'Corporate Contributions', 'Revenue', 'Contributions', 'Credit'),
                ('4030', 'Foundation Grants', 'Revenue', 'Grants', 'Credit'),
                ('4110', 'Membership Dues', 'Revenue', 'Dues', 'Credit'),
                ('4210', 'Special Event Revenue', 'Revenue', 'Events', 'Credit'),
                ('4310', 'Program Service Fees', 'Revenue', 'Program Revenue', 'Credit'),
                ('4410', 'Investment Income - Interest', 'Revenue', 'Investment Income', 'Credit'),
                
                # Expenses
                ('5010', 'Salaries & Wages', 'Expense', 'Personnel', 'Debit'),
                ('5020', 'Payroll Taxes', 'Expense', 'Personnel', 'Debit'),
                ('5110', 'Professional Fees', 'Expense', 'Administrative', 'Debit'),
                ('5210', 'Occupancy - Rent', 'Expense', 'Occupancy', 'Debit'),
                ('5220', 'Occupancy - Utilities', 'Expense', 'Occupancy', 'Debit'),
                ('5310', 'Office Supplies', 'Expense', 'Administrative', 'Debit'),
                ('5320', 'Program Supplies', 'Expense', 'Program Services', 'Debit'),
                ('5410', 'Travel & Meetings', 'Expense', 'General', 'Debit'),
                ('5510', 'Advertising & Promotion', 'Expense', 'Fundraising', 'Debit'),
                ('5610', 'Insurance', 'Expense', 'Administrative', 'Debit'),
                ('5710', 'Depreciation', 'Expense', 'Administrative', 'Debit'),
                ('5810', 'Bank Fees', 'Expense', 'Administrative', 'Debit'),
            ]
            
            for acc in default_accounts:
                account = ChartOfAccounts(
                    account_number=acc[0],
                    account_name=acc[1],
                    account_type=acc[2],
                    account_subtype=acc[3],
                    normal_balance=acc[4]
                )
                db.session.add(account)
            
            db.session.commit()

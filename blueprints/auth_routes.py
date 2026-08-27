"""
Authentication Blueprint
Handles authentication routes and initialization
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Organization, Project, ChartOfAccounts
from datetime import datetime
from sqlalchemy import text, inspect

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
    
    #return render_template('login.html')
    org = Organization.query.first()
    return render_template('login.html',
                       org_code=org.css_file[:-4] if org and org.css_file else None,
                       org_name=org.name if org else 'CARES')


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

        # Ensure the users table has the `default_report_year` column; add it if missing
        try:
            inspector = inspect(db.engine)
            cols = [c['name'] for c in inspector.get_columns('users')]
            if 'default_report_year' not in cols:
                app.logger.info('users.default_report_year not found; attempting to add column')
                try:
                    dialect = db.engine.dialect.name
                    if dialect == 'postgresql' or dialect == 'mysql':
                        # Use IF NOT EXISTS where supported to avoid race errors
                        alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_report_year INTEGER"
                    else:
                        # SQLite and other dialects: standard ADD COLUMN
                        alter_sql = "ALTER TABLE users ADD COLUMN default_report_year INTEGER"

                    db.session.execute(text(alter_sql))
                    db.session.commit()

                    # Re-create inspector to refresh metadata and verify the column was added
                    inspector = inspect(db.engine)
                    cols2 = [c['name'] for c in inspector.get_columns('users')]
                    if 'default_report_year' in cols2:
                        app.logger.info('Added users.default_report_year column successfully')
                    else:
                        app.logger.error('Failed to add users.default_report_year column (still missing)')
                        raise RuntimeError('Failed to add users.default_report_year column')
                except Exception as e:
                    app.logger.exception(f'Attempt to add users.default_report_year failed: {e}')
                    # Re-create inspector and re-check in case another process added the column concurrently
                    try:
                        inspector = inspect(db.engine)
                        cols2 = [c['name'] for c in inspector.get_columns('users')]
                        if 'default_report_year' in cols2:
                            app.logger.info('users.default_report_year appears to have been added by another process')
                            # success
                        else:
                            # Not present after retry -> raise so ops can run a migration manually
                            raise
                    except Exception:
                        raise
        except Exception as e:
            app.logger.exception(f'Could not inspect users table for default_report_year column: {e}')
            raise
        
        # Create default organization if none exists
        if not Organization.query.first():
            org = Organization(
                name=app.config.get('DEFAULT_ORGANIZATION', 'CARES - Example Chapter'),
                org_type='Chapter',
                fiscal_year_start=1,
                css_file='kofc.css'  # REGALIA (Knights of Columbus edition) branding by default
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
                # Assets (add 1000 for tests)
                ('1000', 'Cash', 'Asset', 'Cash', 'Debit'),
                ('1010', 'Operating Checking Account', 'Asset', 'Cash', 'Debit'),
                ('1020', 'Savings Account', 'Asset', 'Cash', 'Debit'),
                ('1030', 'Petty Cash', 'Asset', 'Cash', 'Debit'),
                ('1210', 'Accounts Receivable', 'Asset', 'Receivables', 'Debit'),
                ('1510', 'Land', 'Asset', 'Fixed Assets', 'Debit'),
                ('1520', 'Buildings', 'Asset', 'Fixed Assets', 'Debit'),
                ('1530', 'Equipment & Furnishings', 'Asset', 'Fixed Assets', 'Debit'),
                ('1590', 'Accumulated Depreciation', 'Asset', 'Contra-Asset', 'Credit'),
                
                # Liabilities (add 2000 for tests)
                ('2000', 'Accounts Payable', 'Liability', 'Current Liability', 'Credit'),
                ('2010', 'Accounts Payable', 'Liability', 'Current Liability', 'Credit'),
                ('2020', 'Credit Card Payable', 'Liability', 'Current Liability', 'Credit'),
                ('2110', 'Accrued Salaries', 'Liability', 'Accrued Liability', 'Credit'),
                ('2510', 'Long-term Loans Payable', 'Liability', 'Long-term Liability', 'Credit'),
                
                # Net Assets (add 3000 for tests)
                ('3000', 'Net Assets', 'Net Assets', 'Unrestricted', 'Credit'),
                ('3100', 'Net Assets Without Donor Restrictions', 'Net Asset', 'Unrestricted', 'Credit'),
                ('3200', 'Net Assets With Donor Restrictions - Time', 'Net Asset', 'Restricted', 'Credit'),
                ('3210', 'Net Assets With Donor Restrictions - Purpose', 'Net Asset', 'Restricted', 'Credit'),
                
                # Revenue (add 4000 for tests)
                ('4000', 'Revenue', 'Revenue', 'Contributions', 'Credit'),
                ('4010', 'Individual Contributions', 'Revenue', 'Contributions', 'Credit'),
                ('4020', 'Corporate Contributions', 'Revenue', 'Contributions', 'Credit'),
                ('4030', 'Foundation Grants', 'Revenue', 'Grants', 'Credit'),
                ('4110', 'Membership Dues', 'Revenue', 'Dues', 'Credit'),
                ('4210', 'Special Event Revenue', 'Revenue', 'Events', 'Credit'),
                ('4310', 'Program Service Fees', 'Revenue', 'Program Revenue', 'Credit'),
                ('4410', 'Investment Income - Interest', 'Revenue', 'Investment Income', 'Credit'),
                
                # Expenses (add 5000 for tests)
                ('5000', 'Expense', 'Expense', 'General', 'Debit'),
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

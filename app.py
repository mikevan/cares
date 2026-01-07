"""
Knights of Columbus Accounting System
Main Flask Application
"""

import os
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Organization, Member, Project, ChartOfAccounts, JournalEntry, JournalEntryLine
from reports import FinancialReports
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from blueprints.member_routes import members_bp

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///kofc_accounting.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.register_blueprint(members_bp)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def init_database():
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()
        
        # Create default organization if none exists
        if not Organization.query.first():
            org = Organization(
                name='Knights of Columbus - Example Chapter',
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


# ==================== AUTHENTICATION ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
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


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))


# ==================== DASHBOARD ====================

@app.route('/')
@login_required
def index():
    member_count = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).count()
    
    project_count = Project.query.filter_by(
        organization_id=current_user.organization_id,
        status='Active'
    ).count()
    
    # Get cash balance from Chart of Accounts
    reports = FinancialReports(db.session, current_user.organization_id)
    balance_sheet = reports.balance_sheet()
    cash_balance = sum(
        acc['balance'] for acc in balance_sheet['assets']['accounts']
        if acc['number'].startswith('10')
    )
    
    # Recent transactions
    recent_transactions = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)\
        .order_by(JournalEntry.entry_date.desc())\
        .limit(10)\
        .all()
    
    return render_template('index.html',
                         member_count=member_count,
                         project_count=project_count,
                         cash_balance=cash_balance,
                         recent_transactions=recent_transactions)
"""
Member Import Feature - Add these routes to your app.py
"""

# Decorator to require Admin or Treasurer role
def admin_or_treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/members/import', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def import_members():
    """Member CSV import page"""
    if request.method == 'POST':
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        if not file.filename.endswith('.csv'):
            flash('File must be a CSV file.', 'danger')
            return redirect(request.url)
        
        try:
            # Read CSV file
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream)
            
            # Validate headers
            required_headers = ['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active']
            if not all(header in csv_reader.fieldnames for header in required_headers):
                flash(f'CSV must contain these headers: {", ".join(required_headers)}', 'danger')
                return redirect(request.url)
            
            # Process rows
            success_count = 0
            error_count = 0
            errors = []
            row_num = 1  # Start at 1 (header is row 0)
            
            for row in csv_reader:
                row_num += 1
                try:
                    # Validate required fields
                    if not row['name'].strip():
                        errors.append(f"Row {row_num}: Name is required")
                        error_count += 1
                        continue
                    
                    # Parse join_date
                    join_date = None
                    if row['join_date'].strip():
                        try:
                            join_date = datetime.strptime(row['join_date'].strip(), '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid date format for '{row['join_date']}'. Use YYYY-MM-DD")
                            error_count += 1
                            continue
                    
                    # Parse active status
                    active = True  # Default to active
                    if row['active'].strip().lower() in ['false', '0', 'no', 'inactive']:
                        active = False
                    
                    # Check for duplicate email
                    if row['email'].strip():
                        existing = Member.query.filter_by(
                            email=row['email'].strip(),
                            organization_id=current_user.organization_id
                        ).first()
                        if existing:
                            errors.append(f"Row {row_num}: Member with email '{row['email']}' already exists")
                            error_count += 1
                            continue
                    
                    # Create member
                    member = Member(
                        name=row['name'].strip(),
                        email=row['email'].strip() if row['email'].strip() else None,
                        phone=row['phone'].strip() if row['phone'].strip() else None,
                        address=row['address'].strip() if row['address'].strip() else None,
                        city=row['city'].strip() if row['city'].strip() else None,
                        state=row['state'].strip() if row['state'].strip() else None,
                        zip=row['zip'].strip() if row['zip'].strip() else None,
                        join_date=join_date,
                        active=active,
                        organization_id=current_user.organization_id
                    )
                    
                    db.session.add(member)
                    success_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
                    error_count += 1
                    continue
            
            # Commit all successful imports
            if success_count > 0:
                db.session.commit()
                flash(f'Successfully imported {success_count} member(s).', 'success')
            
            # Show errors if any
            if error_count > 0:
                flash(f'Failed to import {error_count} member(s). See errors below.', 'warning')
                return render_template('member_import.html', errors=errors)
            
            return redirect(url_for('members'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CSV file: {str(e)}', 'danger')
            return redirect(request.url)
    
    return render_template('member_import.html', errors=None)


@app.route('/members/import/template')
@login_required
@admin_or_treasurer_required
def download_member_template():
    """Download CSV template for member import"""
    
    # Create CSV template
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active'])
    
    # Write example rows
    writer.writerow([
        'John Smith',
        'john.smith@example.com',
        '555-0123',
        '123 Main St',
        'Springfield',
        'IL',
        '62701',
        '2024-01-15',
        'true'
    ])
    writer.writerow([
        'Jane Doe',
        'jane.doe@example.com',
        '555-0124',
        '456 Oak Ave',
        'Springfield',
        'IL',
        '62702',
        '2024-03-20',
        'true'
    ])
    writer.writerow([
        'Bob Johnson',
        'bob.johnson@example.com',
        '555-0125',
        '789 Pine Rd',
        'Springfield',
        'IL',
        '62703',
        '2023-11-10',
        'false'
    ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=member_import_template.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


@app.route('/members/export')
@login_required
def export_members():
    """Export all members to CSV"""
    
    # Get all members for current organization
    members = Member.query.filter_by(organization_id=current_user.organization_id).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active'])
    
    # Write member data
    for member in members:
        writer.writerow([
            member.name,
            member.email or '',
            member.phone or '',
            member.address or '',
            member.city or '',
            member.state or '',
            member.zip or '',
            member.join_date.strftime('%Y-%m-%d') if member.join_date else '',
            'true' if member.active else 'false'
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=members_export_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response

# ==================== PROJECTS ====================

@app.route('/projects')
@login_required
def projects():
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Project.name).all()
    return render_template('projects.html', projects=projects)


@app.route('/projects/new', methods=['GET', 'POST'])
@login_required
def project_new():
    if request.method == 'POST':
        try:
            project = Project(
                name=request.form['name'],
                description=request.form.get('description'),
                start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else None,
                end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None,
                status=request.form.get('status', 'Active'),
                budget=Decimal(request.form.get('budget', 0)),
                organization_id=current_user.organization_id
            )
            
            # Add volunteers
            volunteer_ids = request.form.getlist('volunteers')
            for vid in volunteer_ids:
                if vid:
                    volunteer = Member.query.get(int(vid))
                    if volunteer:
                        project.volunteers.append(volunteer)
            
            # Add leaders
            leader_ids = request.form.getlist('leaders')
            for lid in leader_ids:
                if lid:
                    leader = Member.query.get(int(lid))
                    if leader:
                        project.leaders.append(leader)
            
            db.session.add(project)
            db.session.commit()
            flash('Project added successfully!', 'success')
            return redirect(url_for('projects'))
        except Exception as e:
            flash(f'Error adding project: {str(e)}', 'error')
            db.session.rollback()
    
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()
    return render_template('project_form.html', project=None, members=members)


@app.route('/projects/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def project_edit(id):
    project = Project.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            project.name = request.form['name']
            project.description = request.form.get('description')
            if request.form.get('start_date'):
                project.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            if request.form.get('end_date'):
                project.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            project.status = request.form.get('status', 'Active')
            project.budget = Decimal(request.form.get('budget', 0))
            
            # Update volunteers
            project.volunteers = []
            volunteer_ids = request.form.getlist('volunteers')
            for vid in volunteer_ids:
                if vid:
                    volunteer = Member.query.get(int(vid))
                    if volunteer:
                        project.volunteers.append(volunteer)
            
            # Update leaders
            project.leaders = []
            leader_ids = request.form.getlist('leaders')
            for lid in leader_ids:
                if lid:
                    leader = Member.query.get(int(lid))
                    if leader:
                        project.leaders.append(leader)
            
            db.session.commit()
            flash('Project updated successfully!', 'success')
            return redirect(url_for('projects'))
        except Exception as e:
            flash(f'Error updating project: {str(e)}', 'error')
            db.session.rollback()
    
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()
    return render_template('project_form.html', project=project, members=members)


# ==================== TRANSACTIONS ====================

@app.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    transactions_query = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)\
        .order_by(JournalEntry.entry_date.desc())
    
    transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('transactions.html', transactions=transactions)


@app.route('/transactions/<int:id>')
@login_required
def transaction_view(id):
    transaction = JournalEntry.query.get_or_404(id)
    lines = JournalEntryLine.query.filter_by(journal_entry_id=id).all()
    return render_template('transaction_view.html', transaction=transaction, lines=lines)


@app.route('/transactions/new', methods=['GET', 'POST'])
@login_required
def transaction_new():
    if current_user.role not in ['Admin', 'Treasurer']:
        flash('Permission denied - only Admin and Treasurer can post transactions', 'error')
        return redirect(url_for('transactions'))
    
    if request.method == 'POST':
        try:
            entry_mode = request.form.get('entry_mode', 'simple')
            
            if entry_mode == 'simple':
                # Simple mode - create pre-defined transaction types
                return handle_simple_transaction()
            else:
                # Accountant mode - full journal entry
                return handle_accountant_transaction()
                
        except Exception as e:
            flash(f'Error creating transaction: {str(e)}', 'error')
            db.session.rollback()
    
    # GET request - show form
    projects = Project.query.filter_by(organization_id=current_user.organization_id).all()
    accounts = ChartOfAccounts.query.filter_by(active=True).order_by(ChartOfAccounts.account_number).all()
    #return render_template('transaction_form.html', projects=projects, accounts=accounts)
    today = date.today().strftime('%Y-%m-%d')
    return render_template('transaction_form.html', projects=projects, accounts=accounts, today=today)

def handle_simple_transaction():
    """Handle simple transaction entry for non-accountants"""
    transaction_type = request.form.get('transaction_type')
    amount = Decimal(request.form.get('amount', 0))
    project_id = int(request.form.get('project_id'))
    description = request.form.get('description')
    entry_date = datetime.strptime(request.form.get('entry_date'), '%Y-%m-%d').date()
    reference = request.form.get('reference_number')
    
    # Create journal entry
    journal_entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        reference_number=reference,
        created_by=current_user.id,
        status='Posted'
    )
    db.session.add(journal_entry)
    db.session.flush()  # Get the ID
    
    # Create debit and credit lines based on transaction type
    transaction_templates = {
        'received_dues': {
            'debit_account': '1010',  # Operating Checking
            'credit_account': '4110'  # Membership Dues
        },
        'received_donation': {
            'debit_account': '1010',  # Operating Checking
            'credit_account': '4010'  # Individual Contributions
        },
        'received_grant': {
            'debit_account': '1010',  # Operating Checking
            'credit_account': '4030'  # Foundation Grants
        },
        'paid_vendor': {
            'debit_account': '5320',  # Program Supplies
            'credit_account': '1010'  # Operating Checking
        },
        'paid_rent': {
            'debit_account': '5210',  # Occupancy - Rent
            'credit_account': '1010'  # Operating Checking
        },
        'paid_utilities': {
            'debit_account': '5220',  # Occupancy - Utilities
            'credit_account': '1010'  # Operating Checking
        },
        'paid_salary': {
            'debit_account': '5010',  # Salaries & Wages
            'credit_account': '1010'  # Operating Checking
        }
    }
    
    template = transaction_templates.get(transaction_type)
    if not template:
        raise ValueError(f"Unknown transaction type: {transaction_type}")
    
    # Get account objects
    debit_acct = ChartOfAccounts.query.filter_by(account_number=template['debit_account']).first()
    credit_acct = ChartOfAccounts.query.filter_by(account_number=template['credit_account']).first()
    
    if not debit_acct or not credit_acct:
        raise ValueError("Account not found in Chart of Accounts")
    
    # Create debit line
    debit_line = JournalEntryLine(
        journal_entry_id=journal_entry.id,
        account_id=debit_acct.id,
        debit_amount=amount,
        credit_amount=0,
        memo=description
    )
    db.session.add(debit_line)
    
    # Create credit line
    credit_line = JournalEntryLine(
        journal_entry_id=journal_entry.id,
        account_id=credit_acct.id,
        debit_amount=0,
        credit_amount=amount,
        memo=description
    )
    db.session.add(credit_line)
    
    db.session.commit()
    flash('Transaction posted successfully!', 'success')
    return redirect(url_for('transactions'))


def handle_accountant_transaction():
    """Handle full journal entry for accountants"""
    project_id = int(request.form.get('project_id'))
    description = request.form.get('description')
    entry_date = datetime.strptime(request.form.get('entry_date'), '%Y-%m-%d').date()
    reference = request.form.get('reference_number')
    
    # Create journal entry
    journal_entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        reference_number=reference,
        created_by=current_user.id,
        status='Posted'
    )
    db.session.add(journal_entry)
    db.session.flush()
    
    # Get all line items from form
    account_ids = request.form.getlist('account_id[]')
    debit_amounts = request.form.getlist('debit_amount[]')
    credit_amounts = request.form.getlist('credit_amount[]')
    memos = request.form.getlist('memo[]')
    
    total_debits = Decimal('0')
    total_credits = Decimal('0')
    
    for i in range(len(account_ids)):
        if not account_ids[i]:
            continue
            
        debit = Decimal(debit_amounts[i] or 0)
        credit = Decimal(credit_amounts[i] or 0)
        
        if debit == 0 and credit == 0:
            continue
        
        line = JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=int(account_ids[i]),
            debit_amount=debit,
            credit_amount=credit,
            memo=memos[i] if i < len(memos) else ''
        )
        db.session.add(line)
        
        total_debits += debit
        total_credits += credit
    
    # Verify balanced
    if abs(total_debits - total_credits) > Decimal('0.01'):
        db.session.rollback()
        flash(f'Transaction not balanced! Debits: ${total_debits}, Credits: ${total_credits}', 'error')
        return redirect(url_for('transaction_new'))
    
    db.session.commit()
    flash('Journal entry posted successfully!', 'success')
    return redirect(url_for('transactions'))


@app.route('/transactions/<int:id>/void', methods=['POST'])
@login_required
def transaction_void(id):
    if current_user.role not in ['Admin', 'Treasurer']:
        flash('Permission denied', 'error')
        return redirect(url_for('transactions'))
    
    transaction = JournalEntry.query.get_or_404(id)
    transaction.status = 'Voided'
    db.session.commit()
    flash('Transaction voided successfully!', 'success')
    return redirect(url_for('transactions'))


# ==================== REPORTS ====================

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')


@app.route('/reports/balance-sheet')
@login_required
def balance_sheet():
    as_of_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.balance_sheet(as_of_date)
    return render_template('balance_sheet.html', data=data, as_of_date=as_of_date)


@app.route('/reports/income-statement')
@login_required
def income_statement():
    year = request.args.get('year', date.today().year, type=int)
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.income_statement(start_date, end_date)
    return render_template('income_statement.html', data=data, year=year)


@app.route('/reports/cash-flow')
@login_required
def cash_flow():
    year = request.args.get('year', date.today().year, type=int)
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.cash_flow_statement(start_date, end_date)
    return render_template('cash_flow.html', data=data, year=year)


# ==================== SETTINGS ====================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.role not in ['Admin']:
        flash('Permission denied', 'error')
        return redirect(url_for('index'))
    
    org = Organization.query.get(current_user.organization_id)
    
    if request.method == 'POST':
        try:
            org.name = request.form['name']
            org.ein = request.form.get('ein')
            org.address = request.form.get('address')
            org.city = request.form.get('city')
            org.state = request.form.get('state')
            org.zip_code = request.form.get('zip_code')
            org.phone = request.form.get('phone')
            org.email = request.form.get('email')
            org.website = request.form.get('website')
            org.fiscal_year_start = int(request.form.get('fiscal_year_start', 1))
            
            db.session.commit()
            flash('Settings updated successfully!', 'success')
            return redirect(url_for('settings'))
        except Exception as e:
            flash(f'Error updating settings: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('settings.html', org=org)


if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)

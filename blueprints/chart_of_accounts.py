"""
Chart of Accounts Management Blueprint
Handles all chart of accounts operations including CRUD and filtering
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, ChartOfAccounts
from functools import wraps

# Create the blueprint
chart_of_accounts_bp = Blueprint('chart_of_accounts', __name__, url_prefix='/chart-of-accounts')


# Decorator to require Admin role
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== CHART OF ACCOUNTS CRUD ====================

@chart_of_accounts_bp.route('/')
@login_required
def list():
    """List all chart of accounts with filtering"""
    # Get filter parameters
    search_query = request.args.get('search', '').strip()
    account_type_filter = request.args.get('type', '').strip()
    show_inactive = request.args.get('show_inactive', '').lower() == 'true'
    
    # Build query
    query = ChartOfAccounts.query
    
    # Apply filters
    if search_query:
        query = query.filter(
            (ChartOfAccounts.account_number.ilike(f'%{search_query}%')) |
            (ChartOfAccounts.account_name.ilike(f'%{search_query}%'))
        )
    
    if account_type_filter:
        query = query.filter(ChartOfAccounts.account_type == account_type_filter)
    
    if not show_inactive:
        query = query.filter(ChartOfAccounts.active == True)
    
    # Order by account number
    accounts = query.order_by(ChartOfAccounts.account_number).all()
    
    # Get all account types for the filter dropdown
    account_types = db.session.query(ChartOfAccounts.account_type).distinct().all()
    account_types = [t[0] for t in account_types if t[0]]
    account_types.sort()
    
    return render_template('chart_of_accounts.html',
                         accounts=accounts,
                         account_types=account_types,
                         account_type_filter=account_type_filter,
                         search_query=search_query,
                         show_inactive=show_inactive)


@chart_of_accounts_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new():
    """Create new chart of accounts entry"""
    if request.method == 'POST':
        try:
            # Validate account number is unique
            existing = ChartOfAccounts.query.filter_by(
                account_number=request.form['account_number']
            ).first()
            if existing:
                flash('Account number already exists', 'error')
                return redirect(url_for('chart_of_accounts.new'))
            
            account = ChartOfAccounts(
                account_number=request.form['account_number'],
                account_name=request.form['account_name'],
                account_type=request.form['account_type'],
                account_subtype=request.form.get('account_subtype'),
                normal_balance=request.form['normal_balance'],
                description=request.form.get('description'),
                parent_account_id=request.form.get('parent_account_id') or None,
                active=True
            )
            
            db.session.add(account)
            db.session.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('chart_of_accounts.list'))
        except Exception as e:
            flash(f'Error creating account: {str(e)}', 'error')
            db.session.rollback()
    
    # Get parent accounts for dropdown (only active accounts)
    parent_accounts = ChartOfAccounts.query.filter_by(active=True).order_by(
        ChartOfAccounts.account_number
    ).all()
    
    return render_template('chart_of_accounts_form.html',
                         account=None,
                         parent_accounts=parent_accounts)


@chart_of_accounts_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Edit existing chart of accounts entry"""
    account = ChartOfAccounts.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Check if account number is being changed and if new number already exists
            if request.form['account_number'] != account.account_number:
                existing = ChartOfAccounts.query.filter_by(
                    account_number=request.form['account_number']
                ).first()
                if existing:
                    flash('Account number already exists', 'error')
                    return redirect(url_for('chart_of_accounts.edit', id=id))
            
            account.account_number = request.form['account_number']
            account.account_name = request.form['account_name']
            account.account_type = request.form['account_type']
            account.account_subtype = request.form.get('account_subtype')
            account.normal_balance = request.form['normal_balance']
            account.description = request.form.get('description')
            account.parent_account_id = request.form.get('parent_account_id') or None
            
            db.session.commit()
            flash('Account updated successfully!', 'success')
            return redirect(url_for('chart_of_accounts.list'))
        except Exception as e:
            flash(f'Error updating account: {str(e)}', 'error')
            db.session.rollback()
    
    # Get parent accounts for dropdown (exclude current account to prevent circular references)
    parent_accounts = ChartOfAccounts.query.filter(
        ChartOfAccounts.id != id,
        ChartOfAccounts.active == True
    ).order_by(ChartOfAccounts.account_number).all()
    
    return render_template('chart_of_accounts_form.html',
                         account=account,
                         parent_accounts=parent_accounts)


@chart_of_accounts_bp.route('/<int:id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_active(id):
    """Toggle active status of an account"""
    try:
        account = ChartOfAccounts.query.get_or_404(id)
        account.active = not account.active
        db.session.commit()
        
        status = 'activated' if account.active else 'deactivated'
        flash(f'Account {status} successfully!', 'success')
    except Exception as e:
        flash(f'Error toggling account status: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('chart_of_accounts.list'))

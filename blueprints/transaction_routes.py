"""
Transaction Management Blueprint
Handles all transaction (journal entry) related routes including CRUD, export
"""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Project, ChartOfAccounts, JournalEntry, JournalEntryLine
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

# Create the blueprint
transactions_bp = Blueprint('transactions', __name__, url_prefix='/transactions')


# Decorator to require Admin or Treasurer role
def admin_or_treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('Permission denied - only Admin and Treasurer can post transactions', 'error')
            return redirect(url_for('transactions.list'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== TRANSACTIONS CRUD ====================

@transactions_bp.route('/')
@login_required
def list():
    """List all transactions with pagination and filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    project_filter = request.args.get('project', '', type=str)
    
    # Base query
    transactions_query = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)
    
    # Apply project filter if specified
    if project_filter:
        transactions_query = transactions_query.filter(Project.id == int(project_filter))
    
    # Order and paginate
    transactions_query = transactions_query.order_by(JournalEntry.entry_date.desc())
    transactions = transactions_query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get all projects for filter dropdown
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Project.name).all()
    
    return render_template('transactions.html', 
                          transactions=transactions, 
                          projects=projects,
                          selected_project=project_filter)


@transactions_bp.route('/<int:id>')
@login_required
def view(id):
    """View a specific transaction"""
    transaction = JournalEntry.query.get_or_404(id)
    lines = JournalEntryLine.query.filter_by(journal_entry_id=id).all()
    return render_template('transaction_view.html', transaction=transaction, lines=lines)


@transactions_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def new():
    """Create new transaction"""
    if request.method == 'POST':
        try:
            entry_mode = request.form.get('entry_mode', 'simple')
            
            if entry_mode == 'simple':
                # Simple mode - create pre-defined transaction types
                return _handle_simple_transaction()
            else:
                # Accountant mode - full journal entry
                return _handle_accountant_transaction()
                
        except Exception as e:
            flash(f'Error creating transaction: {str(e)}', 'error')
            db.session.expunge_all()  # Clear session to avoid stale data
    
    # GET request - show form
    projects = Project.query.filter_by(organization_id=current_user.organization_id).all()
    accounts = ChartOfAccounts.query.filter_by(active=True).order_by(ChartOfAccounts.account_number).all()
    today = date.today().strftime('%Y-%m-%d')
    return render_template('transaction_form.html', projects=projects, accounts=accounts, today=today)

@transactions_bp.route('/simple', methods=['POST'])
@login_required
@admin_or_treasurer_required
def simple():
    """Create a simple two-line transaction with explicit debit/credit accounts"""
    try:
        entry_date = datetime.strptime(request.form.get('entry_date'), '%Y-%m-%d').date()
        description = request.form.get('description')
        project_id = int(request.form.get('project_id'))
        amount = Decimal(request.form.get('amount', 0))
        debit_account_id = int(request.form.get('debit_account_id'))
        credit_account_id = int(request.form.get('credit_account_id'))

        journal_entry = JournalEntry(
            entry_date=entry_date,
            description=description,
            project_id=project_id,
            reference_number=request.form.get('reference_number'),
            created_by=current_user.id,
            status='Posted'
        )
        db.session.add(journal_entry)
        db.session.flush()

        db.session.add(JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=debit_account_id,
            debit_amount=amount,
            credit_amount=Decimal('0'),
            memo=description
        ))
        db.session.add(JournalEntryLine(
            journal_entry_id=journal_entry.id,
            account_id=credit_account_id,
            debit_amount=Decimal('0'),
            credit_amount=amount,
            memo=description
        ))

        db.session.commit()
        flash('Transaction posted successfully!', 'success')
        return redirect(url_for('transactions.list'))
    except Exception as e:
        flash(f'Error creating transaction: {str(e)}', 'error')
        db.session.expunge_all()
        return redirect(url_for('transactions.list'))

def _handle_simple_transaction():
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
    return redirect(url_for('transactions.list'))


def _handle_accountant_transaction():
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
        return redirect(url_for('transactions.new'))
    
    db.session.commit()
    flash('Journal entry posted successfully!', 'success')
    return redirect(url_for('transactions.list'))


@transactions_bp.route('/<int:id>/void', methods=['POST'])
@login_required
@admin_or_treasurer_required
def void(id):
    """Void a transaction"""
    try:
        transaction = JournalEntry.query.get_or_404(id)
        transaction.status = 'Voided'
        db.session.commit()
        flash('Transaction voided successfully!', 'success')
    except Exception as e:
        flash(f'Error voiding transaction: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('transactions.list'))

@transactions_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def edit(id):
    """Edit a transaction"""
    transaction = JournalEntry.query.get_or_404(id)
    if request.method == 'POST':
        try:
            transaction.description = request.form.get('description', transaction.description)
            transaction.entry_date = datetime.strptime(request.form['entry_date'], '%Y-%m-%d').date() if request.form.get('entry_date') else transaction.entry_date
            transaction.project_id = int(request.form['project_id']) if request.form.get('project_id') else transaction.project_id
            transaction.reference_number = request.form.get('reference_number', transaction.reference_number)
            db.session.commit()
            flash('Transaction updated successfully!', 'success')
            return redirect(url_for('transactions.list'))
        except Exception as e:
            flash(f'Error updating transaction: {str(e)}', 'error')
            db.session.expunge_all()

    projects = Project.query.filter_by(organization_id=current_user.organization_id).all()
    lines = JournalEntryLine.query.filter_by(journal_entry_id=id).all()
    return render_template('transaction_form.html', transaction=transaction, projects=projects, lines=lines)

@transactions_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_or_treasurer_required
def delete(id):
    """Delete a transaction"""
    try:
        transaction = JournalEntry.query.get_or_404(id)
        JournalEntryLine.query.filter_by(journal_entry_id=id).delete()
        db.session.delete(transaction)
        db.session.commit()
        flash('Transaction deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting transaction: {str(e)}', 'error')
        db.session.expunge_all()
    return redirect(url_for('transactions.list'))

@transactions_bp.route('/export')
@login_required
def export():
    """Export all transactions to CSV with journal entry line details"""
    
    # Get all transactions for current organization
    transactions = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)\
        .order_by(JournalEntry.entry_date.desc())\
        .all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header - detailed format with journal entry lines
    writer.writerow([
        'Transaction ID',
        'Date',
        'Description',
        'Project',
        'Reference',
        'Status',
        'Account Number',
        'Account Name',
        'Debit Amount',
        'Credit Amount',
        'Line Memo'
    ])
    
    # Write transaction data with all journal entry lines
    for transaction in transactions:
        lines = JournalEntryLine.query.filter_by(journal_entry_id=transaction.id).all()
        
        for line in lines:
            writer.writerow([
                transaction.id,
                transaction.entry_date.strftime('%Y-%m-%d'),
                transaction.description,
                transaction.project.name,
                transaction.reference_number or '',
                transaction.status,
                line.account.account_number,
                line.account.account_name,
                f'{line.debit_amount:.2f}' if line.debit_amount > 0 else '',
                f'{line.credit_amount:.2f}' if line.credit_amount > 0 else '',
                line.memo or ''
            ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=transactions_export_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response

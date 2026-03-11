"""
Transaction Management Blueprint
Handles all transaction (journal entry) routes.
Business logic is delegated to services.journal_service.
"""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Project, ChartOfAccounts, JournalEntry, JournalEntryLine
from services.journal_service import (
    post_simple_mode_entry, post_entry_from_account_ids,
    void_entry, JournalServiceError
)
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

transactions_bp = Blueprint('transactions', __name__, url_prefix='/transactions')


def admin_or_treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('Permission denied — only Admin and Treasurer can post transactions.', 'error')
            return redirect(url_for('transactions.list'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== LIST / VIEW ====================

@transactions_bp.route('/')
@login_required
def list():
    page = request.args.get('page', 1, type=int)
    project_filter = request.args.get('project', '', type=str)

    query = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)

    if project_filter:
        query = query.filter(Project.id == int(project_filter))

    transactions = query.order_by(JournalEntry.entry_date.desc())\
        .paginate(page=page, per_page=50, error_out=False)

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
    transaction = JournalEntry.query.get_or_404(id)
    lines = JournalEntryLine.query.filter_by(journal_entry_id=id).all()
    return render_template('transaction_view.html', transaction=transaction, lines=lines)


# ==================== CREATE ====================

@transactions_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def new():
    if request.method == 'POST':
        try:
            entry_mode = request.form.get('entry_mode', 'simple')
            if entry_mode == 'simple':
                _post_simple()
            else:
                _post_accountant()
            return redirect(url_for('transactions.list'))
        except JournalServiceError as e:
            flash(str(e), 'error')
            db.session.rollback()
        except Exception as e:
            flash(f'Unexpected error: {e}', 'error')
            db.session.rollback()

    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).all()
    accounts = ChartOfAccounts.query.filter_by(active=True)\
        .order_by(ChartOfAccounts.account_number).all()
    today = date.today().strftime('%Y-%m-%d')
    return render_template('transaction_form.html',
                           projects=projects, accounts=accounts, today=today)


def _post_simple():
    post_simple_mode_entry(
        transaction_type=request.form.get('transaction_type'),
        entry_date=datetime.strptime(request.form['entry_date'], '%Y-%m-%d').date(),
        description=request.form['description'],
        project_id=int(request.form['project_id']),
        created_by=current_user.id,
        amount=Decimal(request.form.get('amount', 0)),
        reference_number=request.form.get('reference_number', ''),
    )
    flash('Transaction posted successfully!', 'success')


def _post_accountant():
    account_ids    = request.form.getlist('account_id[]')
    debit_amounts  = request.form.getlist('debit_amount[]')
    credit_amounts = request.form.getlist('credit_amount[]')
    memos          = request.form.getlist('memo[]')

    lines = []
    for i, acct_id in enumerate(account_ids):
        if not acct_id:
            continue
        debit  = Decimal(debit_amounts[i]  or 0)
        credit = Decimal(credit_amounts[i] or 0)
        if debit == 0 and credit == 0:
            continue
        lines.append({
            'account_id': int(acct_id),
            'debit':  debit,
            'credit': credit,
            'memo':   memos[i] if i < len(memos) else '',
        })

    post_entry_from_account_ids(
        entry_date=datetime.strptime(request.form['entry_date'], '%Y-%m-%d').date(),
        description=request.form['description'],
        project_id=int(request.form['project_id']),
        created_by=current_user.id,
        lines=lines,
        reference_number=request.form.get('reference_number', ''),
    )
    flash('Journal entry posted successfully!', 'success')


# ==================== VOID ====================

@transactions_bp.route('/<int:id>/void', methods=['POST'])
@login_required
@admin_or_treasurer_required
def void(id):
    try:
        void_entry(id, voided_by=current_user.id)
        flash('Transaction voided successfully!', 'success')
    except JournalServiceError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Unexpected error: {e}', 'error')
        db.session.rollback()
    return redirect(url_for('transactions.list'))


# ==================== EXPORT ====================

@transactions_bp.route('/export')
@login_required
def export():
    transactions = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)\
        .order_by(JournalEntry.entry_date.desc())\
        .all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Transaction ID', 'Date', 'Description', 'Project',
        'Reference', 'Status', 'Account Number', 'Account Name',
        'Debit Amount', 'Credit Amount', 'Line Memo'
    ])

    for transaction in transactions:
        for line in transaction.lines:
            writer.writerow([
                transaction.id,
                transaction.entry_date.strftime('%Y-%m-%d'),
                transaction.description,
                transaction.project.name,
                transaction.reference_number or '',
                transaction.status,
                line.account.account_number,
                line.account.account_name,
                f'{line.debit_amount:.2f}'  if line.debit_amount  > 0 else '',
                f'{line.credit_amount:.2f}' if line.credit_amount > 0 else '',
                line.memo or '',
            ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = (
        f'attachment; filename=transactions_export_'
        f'{datetime.now().strftime("%Y%m%d")}.csv'
    )
    response.headers['Content-Type'] = 'text/csv'
    return response

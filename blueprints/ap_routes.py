"""
Accounts Payable / Receivable Blueprint
Thin routing layer — all business logic is in services.ap_service.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Vendor, Invoice, InvoicePayment, ChartOfAccounts, Project
from services.ap_service import create_invoice, record_payment, void_invoice, APServiceError
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from sqlalchemy import func

ap_bp = Blueprint('ap', __name__, url_prefix='/ap')


def treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('Permission denied.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== VENDORS ====================

@ap_bp.route('/vendors')
@login_required
@treasurer_required
def vendors():
    search = request.args.get('search', '').strip()
    show_inactive = request.args.get('show_inactive', '').lower() == 'true'

    query = Vendor.query.filter_by(organization_id=current_user.organization_id)
    if search:
        query = query.filter(Vendor.name.ilike(f'%{search}%'))
    if not show_inactive:
        query = query.filter_by(active=True)

    return render_template('ap/vendors.html',
                           vendors=query.order_by(Vendor.name).all(),
                           search=search,
                           show_inactive=show_inactive)


@ap_bp.route('/vendors/new', methods=['GET', 'POST'])
@login_required
@treasurer_required
def vendor_new():
    if request.method == 'POST':
        try:
            vendor = Vendor(
                organization_id=current_user.organization_id,
                name=request.form['name'],
                contact_name=request.form.get('contact_name'),
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                address=request.form.get('address'),
                city=request.form.get('city'),
                state=request.form.get('state'),
                zip_code=request.form.get('zip_code'),
                payment_terms=request.form.get('payment_terms', 'Net30'),
                is_1099=request.form.get('is_1099') == 'on',
                notes=request.form.get('notes'),
            )
            db.session.add(vendor)
            db.session.commit()
            flash('Vendor created successfully.', 'success')
            return redirect(url_for('ap.vendors'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating vendor: {e}', 'error')

    return render_template('ap/vendor_form.html', vendor=None)


@ap_bp.route('/vendors/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@treasurer_required
def vendor_edit(id):
    vendor = Vendor.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()

    if request.method == 'POST':
        try:
            vendor.name          = request.form['name']
            vendor.contact_name  = request.form.get('contact_name')
            vendor.email         = request.form.get('email')
            vendor.phone         = request.form.get('phone')
            vendor.address       = request.form.get('address')
            vendor.city          = request.form.get('city')
            vendor.state         = request.form.get('state')
            vendor.zip_code      = request.form.get('zip_code')
            vendor.payment_terms = request.form.get('payment_terms', 'Net30')
            vendor.is_1099       = request.form.get('is_1099') == 'on'
            vendor.active        = request.form.get('active') == 'on'
            vendor.notes         = request.form.get('notes')
            db.session.commit()
            flash('Vendor updated successfully.', 'success')
            return redirect(url_for('ap.vendors'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating vendor: {e}', 'error')

    return render_template('ap/vendor_form.html', vendor=vendor)


# ==================== INVOICES ====================

@ap_bp.route('/')
@login_required
@treasurer_required
def invoices():
    status_filter = request.args.get('status', 'Open')
    vendor_filter = request.args.get('vendor_id', 0, type=int)

    query = Invoice.query.filter_by(organization_id=current_user.organization_id)
    if status_filter and status_filter != 'All':
        query = query.filter_by(status=status_filter)
    if vendor_filter:
        query = query.filter_by(vendor_id=vendor_filter)

    vendors = Vendor.query.filter_by(
        organization_id=current_user.organization_id, active=True
    ).order_by(Vendor.name).all()

    return render_template('ap/invoices.html',
                           invoices=query.order_by(Invoice.due_date.asc()).all(),
                           vendors=vendors,
                           status_filter=status_filter,
                           vendor_filter=vendor_filter)


@ap_bp.route('/invoices/new', methods=['GET', 'POST'])
@login_required
@treasurer_required
def invoice_new():
    if request.method == 'POST':
        try:
            gl_account_id = int(request.form['gl_account_id'])
            gl_account = ChartOfAccounts.query.get_or_404(gl_account_id)

            invoice = create_invoice(
                organization_id=current_user.organization_id,
                vendor_id=int(request.form['vendor_id']),
                project_id=int(request.form['project_id']),
                gl_account_number=gl_account.account_number,
                gl_account_id=gl_account_id,
                invoice_number=request.form.get('invoice_number', ''),
                invoice_date=datetime.strptime(request.form['invoice_date'], '%Y-%m-%d').date(),
                due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date(),
                amount=Decimal(request.form['amount']),
                notes=request.form.get('notes', ''),
                created_by=current_user.id,
            )
            flash(f'Invoice entered and journal entry posted.', 'success')
            return redirect(url_for('ap.invoices'))
        except APServiceError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Unexpected error: {e}', 'error')

    vendors = Vendor.query.filter_by(
        organization_id=current_user.organization_id, active=True
    ).order_by(Vendor.name).all()
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id, status='Active'
    ).order_by(Project.name).all()
    expense_accounts = ChartOfAccounts.query.filter_by(
        account_type='Expense', active=True
    ).order_by(ChartOfAccounts.account_number).all()

    return render_template('ap/invoice_form.html',
                           vendors=vendors,
                           projects=projects,
                           expense_accounts=expense_accounts,
                           today=date.today().strftime('%Y-%m-%d'))


@ap_bp.route('/invoices/<int:id>/pay', methods=['GET', 'POST'])
@login_required
@treasurer_required
def invoice_pay(id):
    invoice = Invoice.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()

    if request.method == 'POST':
        try:
            record_payment(
                invoice=invoice,
                payment_amount=Decimal(request.form['amount']),
                payment_date=datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date(),
                reference_number=request.form.get('reference_number', ''),
                created_by=current_user.id,
            )
            flash('Payment recorded and journal entry posted.', 'success')
            return redirect(url_for('ap.invoices'))
        except APServiceError as e:
            db.session.rollback()
            flash(str(e), 'error')
        except Exception as e:
            db.session.rollback()
            flash(f'Unexpected error: {e}', 'error')

    return render_template('ap/invoice_pay.html',
                           invoice=invoice,
                           today=date.today().strftime('%Y-%m-%d'))


@ap_bp.route('/invoices/<int:id>/void', methods=['POST'])
@login_required
@treasurer_required
def invoice_void(id):
    invoice = Invoice.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()
    try:
        void_invoice(invoice)
        flash('Invoice voided.', 'success')
    except APServiceError as e:
        flash(str(e), 'error')
    return redirect(url_for('ap.invoices'))


# ==================== AGING REPORT ====================

@ap_bp.route('/aging')
@login_required
@treasurer_required
def aging():
    open_invoices = Invoice.query.filter(
        Invoice.organization_id == current_user.organization_id,
        Invoice.status.in_(['Open', 'Partial'])
    ).order_by(Invoice.due_date.asc()).all()

    buckets = {'Current': [], '1-30': [], '31-60': [], '61-90': [], '90+': []}
    totals  = {k: Decimal('0.00') for k in buckets}

    for inv in open_invoices:
        b = inv.aging_bucket
        buckets[b].append(inv)
        totals[b] += inv.amount_due

    return render_template('ap/aging.html',
                           buckets=buckets,
                           totals=totals,
                           grand_total=sum(totals.values()),
                           as_of=date.today())


# ==================== 1099 REPORT ====================

@ap_bp.route('/1099')
@login_required
@treasurer_required
def report_1099():
    year = request.args.get('year', date.today().year, type=int)

    vendors_1099 = Vendor.query.filter_by(
        organization_id=current_user.organization_id, is_1099=True
    ).order_by(Vendor.name).all()

    results = []
    for vendor in vendors_1099:
        paid = db.session.query(func.sum(InvoicePayment.amount))\
            .join(Invoice, InvoicePayment.invoice_id == Invoice.id)\
            .filter(
                Invoice.vendor_id == vendor.id,
                func.extract('year', InvoicePayment.payment_date) == year
            ).scalar() or Decimal('0.00')
        results.append({'vendor': vendor, 'total_paid': paid})

    return render_template('ap/1099.html', results=results, year=year)

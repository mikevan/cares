"""
Member Management Blueprint
Handles all member-related routes including CRUD, import, export, and annual dues
"""

import csv
import io
from datetime import datetime, date
from decimal import Decimal
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, jsonify
from flask_login import login_required, current_user

from models import (
    db, Member, MemberDuesPayment, Organization, Project, ProjectAssignment,
    ChartOfAccounts,
    JournalEntry, JournalEntryLine, MembershipEvent, MEMBERSHIP_EVENT_TYPES,
    MEMBERSHIP_EVENT_ADDITION_TYPES, MEMBERSHIP_EVENT_DEDUCTION_TYPES,
)

# Create the blueprint
members_bp = Blueprint('members', __name__, url_prefix='/members')


# Decorator to require Admin or Treasurer role
def admin_or_treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# Decorator for dues management (Admin, Treasurer, Membership Coordinator)
def dues_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer', 'Membership Coordinator']:
            flash('You do not have permission to manage dues.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== MEMBER CRUD ====================

@members_bp.route('/')
@login_required
def list():
    """List all members"""
    search = request.args.get('search', '').strip()
    query = Member.query.filter_by(organization_id=current_user.organization_id)
    if search:
        query = query.filter(Member.name.ilike(f'%{search}%'))
    members = query.order_by(Member.name).all()

    # Every member's current assignments in ONE query, not one per member.
    # This page renders the whole roster, so a per-row lookup would be a
    # query per member -- the same O(n) round-trip pattern already noted
    # against services/reports.py. Scoped through Project.organization_id,
    # because that is where an assignment's tenancy actually lives.
    assignment_rows = (
        db.session.query(
            ProjectAssignment.member_id, ProjectAssignment.role, Project.name
        )
        .join(Project, Project.id == ProjectAssignment.project_id)
        .filter(
            Project.organization_id == current_user.organization_id,
            ProjectAssignment.end_date.is_(None),
        )
        .order_by(ProjectAssignment.role, Project.name)
        .all()
    )
    assignments_by_member = {}
    for member_id, role, project_name in assignment_rows:
        assignments_by_member.setdefault(member_id, []).append(
            {'role': role, 'project': project_name}
        )

    return render_template(
        'members.html',
        members=members,
        search=search,
        assignments_by_member=assignments_by_member,
    )


@members_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new member"""
    if request.method == 'POST':
        try:
            member = Member(
                name=request.form['name'],
                email=request.form.get('email'),
                phone=request.form.get('phone'),
                address=request.form.get('address'),
                city=request.form.get('city'),
                state=request.form.get('state'),
                zip_code=request.form.get('zip'),
                join_date=datetime.strptime(request.form.get('join_date'), '%Y-%m-%d').date() if request.form.get('join_date') else None,
                active=True,
                organization_id=current_user.organization_id
            )
            db.session.add(member)
            db.session.flush()
            db.session.add(MembershipEvent(
                member_id=member.id,
                organization_id=current_user.organization_id,
                event_type='Initiation',
                event_date=member.join_date or date.today(),
                notes='Logged automatically when the member record was created.',
            ))
            db.session.commit()
            flash('Member added successfully!', 'success')
            return redirect(url_for('members.list'))
        except Exception as e:
            flash(f'Error adding member: {str(e)}', 'error')
            db.session.rollback()

    return render_template('member_form.html', member=None)


@members_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit existing member"""
    member = Member.query.get_or_404(id)

    if member.organization_id != current_user.organization_id:
        flash('Permission denied', 'error')
        return redirect(url_for('members.list'))

    if request.method == 'POST':
        try:
            member.name = request.form['name']
            member.email = request.form.get('email')
            member.phone = request.form.get('phone')
            member.address = request.form.get('address')
            member.city = request.form.get('city')
            member.state = request.form.get('state')
            member.zip_code = request.form.get('zip')
            if request.form.get('join_date'):
                member.join_date = datetime.strptime(request.form.get('join_date'), '%Y-%m-%d').date()
            was_active = member.active
            member.active = request.form.get('active') == 'on'

            if member.active != was_active:
                event_type = request.form.get('membership_event_type')
                if event_type in MEMBERSHIP_EVENT_TYPES:
                    event_date_raw = request.form.get('membership_event_date')
                    event_date = (
                        datetime.strptime(event_date_raw, '%Y-%m-%d').date()
                        if event_date_raw else date.today()
                    )
                    db.session.add(MembershipEvent(
                        member_id=member.id,
                        organization_id=current_user.organization_id,
                        event_type=event_type,
                        event_date=event_date,
                        notes=request.form.get('membership_event_notes'),
                    ))

            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('members.list'))
        except Exception as e:
            flash(f'Error updating member: {str(e)}', 'error')
            db.session.rollback()

    # Full assignment history, current first. ProjectAssignment is a history
    # table by design -- it records why a term ended, not merely that it did --
    # and until now nothing in the application ever showed that history back.
    assignments = (
        ProjectAssignment.query
        .join(Project, Project.id == ProjectAssignment.project_id)
        .filter(
            ProjectAssignment.member_id == member.id,
            Project.organization_id == current_user.organization_id,
        )
        .order_by(
            ProjectAssignment.end_date.is_(None).desc(),
            ProjectAssignment.start_date.desc(),
        )
        .all()
    )

    return render_template(
        'member_form.html',
        member=member,
        assignments=assignments,
        membership_event_addition_types=MEMBERSHIP_EVENT_ADDITION_TYPES,
        membership_event_deduction_types=MEMBERSHIP_EVENT_DEDUCTION_TYPES,
    )


@members_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete member"""
    if current_user.role not in ['Admin', 'Treasurer']:
        flash('Permission denied', 'error')
        return redirect(url_for('members.list'))

    member = Member.query.get_or_404(id)

    if member.organization_id != current_user.organization_id:
        flash('Permission denied', 'error')
        return redirect(url_for('members.list'))

    try:
        db.session.delete(member)
        db.session.commit()
        flash('Member deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting member: {str(e)}', 'error')
        db.session.rollback()

    return redirect(url_for('members.list'))


# ==================== MEMBER IMPORT/EXPORT ====================

@members_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def import_members():
    """Member CSV import page"""
    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash('No file uploaded.', 'danger')
            return redirect(request.url)

        file = request.files['csv_file']

        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)

        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'danger')
            return redirect(request.url)

        try:
            stream = io.StringIO(file.stream.read().decode('utf-8'))
            reader = csv.DictReader(stream)

            imported_count = 0
            error_count = 0
            errors = []

            for row_num, row in enumerate(reader, start=2):
                try:
                    name = row.get('name', '').strip()
                    if not name:
                        errors.append(f'Row {row_num}: Missing name')
                        error_count += 1
                        continue

                    email = row.get('email', '').strip() or None

                    if email:
                        existing = Member.query.filter_by(
                            email=email,
                            organization_id=current_user.organization_id
                        ).first()
                        if existing:
                            errors.append(f'Row {row_num}: Email {email} already exists')
                            error_count += 1
                            continue

                    join_date = None
                    if row.get('join_date', '').strip():
                        try:
                            join_date = datetime.strptime(row['join_date'].strip(), '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f'Row {row_num}: Invalid date format (use YYYY-MM-DD)')
                            error_count += 1
                            continue

                    active_str = row.get('active', 'true').strip().lower()
                    active = active_str not in ('false', '0', 'no', 'inactive')

                    member = Member(
                        name=name,
                        email=email,
                        phone=row.get('phone', '').strip() or None,
                        address=row.get('address', '').strip() or None,
                        city=row.get('city', '').strip() or None,
                        state=row.get('state', '').strip() or None,
                        zip_code=row.get('zip', '').strip() or None,
                        join_date=join_date,
                        active=active,
                        organization_id=current_user.organization_id
                    )
                    db.session.add(member)
                    imported_count += 1

                except Exception as e:
                    errors.append(f'Row {row_num}: {str(e)}')
                    error_count += 1

            db.session.commit()
            flash(f'Successfully imported {imported_count} member(s).', 'success')

            if error_count > 0:
                flash(f'Failed to import {error_count} member(s). See errors below.', 'warning')
                return render_template('member_import.html', errors=errors)

            return redirect(url_for('members.list'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error processing CSV file: {str(e)}', 'danger')
            return redirect(request.url)

    return render_template('member_import.html', errors=None)


@members_bp.route('/import/template')
@login_required
@admin_or_treasurer_required
def download_template():
    """Download CSV template for member import"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active'])
    writer.writerow(['John Smith', 'john.smith@example.com', '555-0123', '123 Main St', 'Springfield', 'IL', '62701', '2024-01-15', 'true'])
    writer.writerow(['Jane Doe', 'jane.doe@example.com', '555-0124', '456 Oak Ave', 'Springfield', 'IL', '62702', '2024-03-20', 'true'])
    writer.writerow(['Bob Johnson', 'bob.johnson@example.com', '555-0125', '789 Pine Rd', 'Springfield', 'IL', '62703', '2023-11-10', 'false'])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=member_import_template.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


@members_bp.route('/export')
@login_required
def export_members():
    """Export all members to CSV"""
    members = Member.query.filter_by(organization_id=current_user.organization_id).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active'])

    for member in members:
        writer.writerow([
            member.name,
            member.email or '',
            member.phone or '',
            member.address or '',
            member.city or '',
            member.state or '',
            member.zip_code or '',
            member.join_date.strftime('%Y-%m-%d') if member.join_date else '',
            'true' if member.active else 'false'
        ])

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=members_export_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response


# ==================== ANNUAL DUES ====================

@members_bp.route('/dues/')
@login_required
@dues_access_required
def dues_roster():
    """Annual dues roster page"""
    year = request.args.get('year', date.today().year, type=int)
    org = Organization.query.get(current_user.organization_id)
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()

    # Load existing dues records for this year, keyed by member_id
    dues_map = {}
    existing = MemberDuesPayment.query.filter_by(
        organization_id=current_user.organization_id,
        year=year
    ).all()
    for d in existing:
        dues_map[d.member_id] = d

    # Auto-select the Dues project, creating it if it doesn't exist
    dues_project = Project.query.filter_by(
        organization_id=current_user.organization_id,
        name='Dues'
    ).first()
    if not dues_project:
        dues_project = Project(
            name='Dues',
            description='Member dues and subscription payments',
            status='Active',
            organization_id=current_user.organization_id
        )
        db.session.add(dues_project)
        db.session.commit()

    # Year range for selector (5 years back, current year)
    current_year = date.today().year
    year_range = [*range(current_year - 4, current_year + 1)]

    paid_count = sum(1 for d in dues_map.values() if d.is_paid)
    total_active = len(members)

    return render_template(
        'dues_roster.html',
        members=members,
        dues_map=dues_map,
        year=year,
        year_range=year_range,
        org=org,
        dues_project=dues_project,
        paid_count=paid_count,
        total_active=total_active
    )


@members_bp.route('/dues/toggle', methods=['POST'])
@login_required
@dues_access_required
def dues_toggle():
    """AJAX: toggle dues paid/unpaid for one member/year"""
    data = request.get_json()
    member_id = data.get('member_id')
    year = data.get('year')
    paid = data.get('paid')  # True = mark paid, False = mark unpaid

    member = Member.query.get_or_404(member_id)
    if member.organization_id != current_user.organization_id:
        return jsonify({'error': 'Permission denied'}), 403

    record = MemberDuesPayment.query.filter_by(
        member_id=member_id,
        year=year,
        organization_id=current_user.organization_id
    ).first()

    if paid:
        if not record:
            record = MemberDuesPayment(
                member_id=member_id,
                organization_id=current_user.organization_id,
                year=year,
                include_in_transaction=True
            )
            db.session.add(record)
        record.paid_date = date.today()
    else:
        if record:
            # Only allow unpay if no journal entry posted yet
            if record.journal_entry_id:
                return jsonify({'error': 'Cannot unpay: transaction already posted'}), 400
            record.paid_date = None

    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'paid': record.is_paid if record else False,
            'paid_date': record.paid_date.strftime('%Y-%m-%d') if (record and record.paid_date) else None
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@members_bp.route('/dues/toggle-transaction', methods=['POST'])
@login_required
@dues_access_required
def dues_toggle_transaction():
    """AJAX: toggle include_in_transaction flag"""
    data = request.get_json()
    member_id = data.get('member_id')
    year = data.get('year')
    include = data.get('include')

    member = Member.query.get_or_404(member_id)
    if member.organization_id != current_user.organization_id:
        return jsonify({'error': 'Permission denied'}), 403

    record = MemberDuesPayment.query.filter_by(
        member_id=member_id,
        year=year,
        organization_id=current_user.organization_id
    ).first()

    if not record:
        return jsonify({'error': 'No dues record found — mark dues paid first'}), 400

    if record.journal_entry_id:
        return jsonify({'error': 'Transaction already posted'}), 400

    record.include_in_transaction = include
    try:
        db.session.commit()
        return jsonify({'success': True, 'include': record.include_in_transaction})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@members_bp.route('/dues/create-transactions', methods=['POST'])
@login_required
@dues_access_required
def dues_create_transactions():
    """Create a single combined journal entry for all checked + transaction-enabled members"""
    year = request.form.get('year', type=int)

    if not year:
        flash('Year is required.', 'danger')
        return redirect(url_for('members.dues_roster'))

    # Auto-select Dues project, creating it if needed
    project = Project.query.filter_by(
        organization_id=current_user.organization_id,
        name='Dues'
    ).first()
    if not project:
        project = Project(
            name='Dues',
            description='Member dues and subscription payments',
            status='Active',
            organization_id=current_user.organization_id
        )
        db.session.add(project)
        db.session.commit()

    org = Organization.query.get(current_user.organization_id)
    dues_amount = org.dues_amount or Decimal('0.00')

    if dues_amount <= 0:
        flash('Dues amount is not set for this organization. Please update organization settings.', 'danger')
        return redirect(url_for('members.dues_roster', year=year))

    # Find all paid, include-flagged, not-yet-posted records for this year
    pending = MemberDuesPayment.query.filter(
        MemberDuesPayment.organization_id == current_user.organization_id,
        MemberDuesPayment.year == year,
        MemberDuesPayment.include_in_transaction == True,
        MemberDuesPayment.paid_date.isnot(None),
        MemberDuesPayment.journal_entry_id.is_(None)
    ).all()

    if not pending:
        flash('No eligible dues records to post. Mark members as paid and ensure Include in Transaction is enabled.', 'warning')
        return redirect(url_for('members.dues_roster', year=year))

    # Look up required GL accounts
    cash_acct = ChartOfAccounts.query.filter_by(account_number='1010').first()
    dues_acct = ChartOfAccounts.query.filter_by(account_number='4110').first()

    if not cash_acct or not dues_acct:
        flash('Required GL accounts not found (1010 Cash, 4110 Membership Dues). Check Chart of Accounts.', 'danger')
        return redirect(url_for('members.dues_roster', year=year))

    try:
        posted = 0
        total = Decimal('0.00')
        for record in pending:
            member_name = record.member.name
            description = f'{member_name} {year} Dues Payment'
            entry = JournalEntry(
                entry_date=date.today(),
                description=description,
                project_id=project.id,
                reference_number=f'DUES-{year}-{record.member_id}-{datetime.now().strftime("%m%d")}',
                created_by=current_user.id,
                status='Posted'
            )
            db.session.add(entry)
            db.session.flush()

            # Debit Cash
            db.session.add(JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=cash_acct.id,
                debit_amount=dues_amount,
                credit_amount=Decimal('0.00'),
                memo=description
            ))

            # Credit Membership Dues Revenue
            db.session.add(JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=dues_acct.id,
                debit_amount=Decimal('0.00'),
                credit_amount=dues_amount,
                memo=description
            ))

            record.journal_entry_id = entry.id
            posted += 1
            total += dues_amount

        db.session.commit()
        flash(f'Posted {posted} dues transaction(s) -- ${total:,.2f} total.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error creating transaction: {str(e)}', 'danger')

    return redirect(url_for('members.dues_roster', year=year))

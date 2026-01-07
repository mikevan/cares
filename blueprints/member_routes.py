"""
Member Management Blueprint
Handles all member-related routes including CRUD, import, and export
"""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Member
from datetime import datetime
from functools import wraps

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


# ==================== MEMBER CRUD ====================

@members_bp.route('/')
@login_required
def list():
    """List all members"""
    members = Member.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Member.name).all()
    return render_template('members.html', members=members)


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
            member.active = request.form.get('active') == 'on'
            
            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('members.list'))
        except Exception as e:
            flash(f'Error updating member: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('member_form.html', member=member)


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
                missing = [h for h in required_headers if h not in csv_reader.fieldnames]
                flash(f'CSV is missing these required columns: {", ".join(missing)}', 'danger')
                return redirect(request.url)
            
            # Process rows
            success_count = 0
            error_count = 0
            errors = []
            row_num = 1  # Start at 1 (header is row 0)
            
            for row in csv_reader:
                row_num += 1
                try:
                    # Helper function to safely get and strip field value
                    def get_field(field_name):
                        value = row.get(field_name, '')
                        if value is None:
                            return ''
                        return str(value).strip()
                    
                    # Get all fields safely
                    name = get_field('name')
                    email = get_field('email')
                    phone = get_field('phone')
                    address = get_field('address')
                    city = get_field('city')
                    state = get_field('state')
                    zip_code = get_field('zip')
                    join_date_str = get_field('join_date')
                    active_str = get_field('active')
                    
                    # Validate required fields
                    if not name:
                        errors.append(f"Row {row_num}: Name is required")
                        error_count += 1
                        continue
                    
                    # Parse join_date
                    join_date = None
                    if join_date_str:
                        try:
                            join_date = datetime.strptime(join_date_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Row {row_num}: Invalid date format for '{join_date_str}'. Use YYYY-MM-DD")
                            error_count += 1
                            continue
                    
                    # Parse active status
                    active = True  # Default to active
                    if active_str.lower() in ['false', '0', 'no', 'inactive', 'n']:
                        active = False
                    
                    # Check for duplicate email (only if email is provided)
                    if email:
                        existing = Member.query.filter_by(
                            email=email,
                            organization_id=current_user.organization_id
                        ).first()
                        if existing:
                            errors.append(f"Row {row_num}: Member with email '{email}' already exists")
                            error_count += 1
                            continue
                    
                    # Create member with safe field values
                    member = Member(
                        name=name,
                        email=email if email else None,
                        phone=phone if phone else None,
                        address=address if address else None,
                        city=city if city else None,
                        state=state if state else None,
                        zip_code=zip_code if zip_code else None,
                        join_date=join_date,
                        active=active,
                        organization_id=current_user.organization_id
                    )
                    
                    db.session.add(member)
                    success_count += 1
                    
                except KeyError as e:
                    errors.append(f"Row {row_num}: Missing required field: {str(e)}")
                    error_count += 1
                    continue
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
    
    # Create CSV template
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header with ALL required columns
    writer.writerow(['name', 'email', 'phone', 'address', 'city', 'state', 'zip', 'join_date', 'active'])
    
    # Write example rows with complete data
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


@members_bp.route('/export')
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
            member.zip_code or '',
            member.join_date.strftime('%Y-%m-%d') if member.join_date else '',
            'true' if member.active else 'false'
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=members_export_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response
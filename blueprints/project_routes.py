"""
Project Management Blueprint
Handles all project-related routes including CRUD, export, and the
leadership/volunteer assignment lifecycle (see services/project_service.py).
"""

import csv
import io
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Project, Member, JournalEntry, JournalEntryLine, ChartOfAccounts, ProjectAssignment, PROJECT_ASSIGNMENT_END_REASONS
from services.project_service import (
    assign_member, end_assignment, close_project_for_year, restart_project, ProjectServiceError
)
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func

# Create the blueprint
projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


def admin_or_treasurer_required(f):
    """Gates project lifecycle actions (ending an assignment, closing a
    project for the year, restarting it) to Admin/Treasurer, matching the
    convention used in ap_routes.py, member_routes.py, and transaction_routes.py.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'Treasurer']:
            flash('Permission denied.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== PROJECTS CRUD ====================

@projects_bp.route('/')
@login_required
def list():
    """List all projects with budget tracking"""
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Project.name).all()
    
    # Calculate budget data for each project
    projects_data = []
    for project in projects:
        spend = calculate_project_spend(project.id)
        budget = project.budget or Decimal('0')
        remaining = budget - spend
        percent_used = (float(spend) / float(budget) * 100) if budget > 0 else 0
        
        projects_data.append({
            'project': project,
            'spend': spend,
            'remaining': remaining,
            'percent_used': percent_used
        })
    
    return render_template('projects.html', projects_data=projects_data)


def calculate_project_spend(project_id):
    """Calculate total spend for a project (sum of expense account debits)"""
    # Get all expense transactions for this project (accounts starting with 5)
    spend = db.session.query(func.sum(JournalEntryLine.debit_amount))\
        .join(JournalEntry)\
        .join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id)\
        .filter(
            JournalEntry.project_id == project_id,
            JournalEntry.status == 'Posted',
            ChartOfAccounts.account_number.like('5%')
        ).scalar() or Decimal('0')
    
    # Subtract any credits (reversals) on expense accounts
    credits = db.session.query(func.sum(JournalEntryLine.credit_amount))\
        .join(JournalEntry)\
        .join(ChartOfAccounts, JournalEntryLine.account_id == ChartOfAccounts.id)\
        .filter(
            JournalEntry.project_id == project_id,
            JournalEntry.status == 'Posted',
            ChartOfAccounts.account_number.like('5%')
        ).scalar() or Decimal('0')
    
    return spend - credits


@projects_bp.route('/<int:id>/view')
@login_required
def view(id):
    """View project details with transactions"""
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()
    
    # Get all transactions for this project
    transactions = JournalEntry.query.filter_by(
        project_id=id,
        status='Posted'
    ).order_by(JournalEntry.entry_date.desc()).all()
    
    # Calculate spend to date
    spend_to_date = calculate_project_spend(id)
    budget = project.budget or Decimal('0')
    remaining = budget - spend_to_date
    percent_used = (float(spend_to_date) / float(budget) * 100) if budget > 0 else 0
    
    return render_template('project_form.html', 
                          project=project, 
                          members=None,
                          transactions=transactions,
                          spend_to_date=spend_to_date,
                          remaining=remaining,
                          percent_used=percent_used,
                          end_reasons=PROJECT_ASSIGNMENT_END_REASONS,
                          view_mode=True)


@projects_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new project"""
    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else None
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None
        if start_date and end_date and end_date < start_date:
            flash('End date cannot be before start date.', 'error')
            members = Member.query.filter_by(organization_id=current_user.organization_id, active=True).order_by(Member.name).all()
            return render_template('project_form.html', project=None, members=members)
        try:
            project = Project(
                name=request.form['name'],
                description=request.form.get('description'),
                start_date=start_date,
                end_date=end_date,
                status=request.form.get('status', 'Active'),
                budget=Decimal(request.form.get('budget', 0)),
                is_fundraiser=request.form.get('is_fundraiser') == 'on',
                organization_id=current_user.organization_id
            )
            db.session.add(project)
            db.session.commit()  # project needs an id before assignments can reference it

            # Add volunteers
            volunteer_ids = request.form.getlist('volunteers')
            for vid in volunteer_ids:
                if vid:
                    volunteer = Member.query.filter_by(
                        id=int(vid), organization_id=current_user.organization_id
                    ).first()
                    if volunteer:
                        assign_member(project, volunteer, role='Volunteer', assigned_by=current_user.id)

            # Add leaders
            leader_ids = request.form.getlist('leaders')
            for lid in leader_ids:
                if lid:
                    leader = Member.query.filter_by(
                        id=int(lid), organization_id=current_user.organization_id
                    ).first()
                    if leader:
                        assign_member(project, leader, role='Leader', assigned_by=current_user.id)

            flash('Project added successfully!', 'success')
            return redirect(url_for('projects.list'))
        except Exception as e:
            flash(f'Error adding project: {str(e)}', 'error')
            # expunge_all(), not rollback(): a rollback() here expires every
            # object in the session -- including flask-login's current_user
            # -- and the re-render below immediately re-reads
            # current_user.organization_id, which then raises
            # ObjectDeletedError under the test harness's savepoint-based
            # per-test transaction. expunge_all() clears the identity map
            # without touching the transaction, avoiding that. (Restored to
            # match the original behavior here -- this endpoint's own
            # partial work, if any, was never committed at the point most
            # exceptions are raised anyway.)
            db.session.expunge_all()
    
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()
    return render_template('project_form.html', project=None, members=members)


@projects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit existing project's basic details.

    Leadership/volunteer changes are NOT handled here -- they go through the
    dedicated assign/end/close/restart routes below, each a single, auditable
    call into services/project_service.py, rather than a bulk replace of
    "whoever's currently selected" that would silently lose end_reason history.
    """
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()
    
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
            project.is_fundraiser = request.form.get('is_fundraiser') == 'on'

            db.session.commit()
            flash('Project updated successfully!', 'success')
            return redirect(url_for('projects.list'))
        except Exception as e:
            flash(f'Error updating project: {str(e)}', 'error')
            db.session.rollback()
    
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()
    
    # Get all transactions for this project
    transactions = JournalEntry.query.filter_by(
        project_id=id,
        status='Posted'
    ).order_by(JournalEntry.entry_date.desc()).all()
    
    # Calculate spend to date
    spend_to_date = calculate_project_spend(id)
    budget = project.budget or Decimal('0')
    remaining = budget - spend_to_date
    percent_used = (float(spend_to_date) / float(budget) * 100) if budget > 0 else 0
    
    return render_template('project_form.html', 
                          project=project, 
                          members=members,
                          transactions=transactions,
                          spend_to_date=spend_to_date,
                          remaining=remaining,
                          percent_used=percent_used,
                          end_reasons=PROJECT_ASSIGNMENT_END_REASONS,
                          view_mode=False)

@projects_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    """Delete a project if it has no journal entries"""
    project = Project.query.get_or_404(id)
    
    if project.organization_id != current_user.organization_id:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))
    
    entry_count = JournalEntry.query.filter_by(project_id=id).count()
    if entry_count > 0:
        flash(f'Cannot delete project "{project.name}" — it has {entry_count} journal entries.', 'error')
        return redirect(url_for('projects.list'))
    
    db.session.delete(project)
    db.session.commit()
    flash(f'Project "{project.name}" deleted successfully.', 'success')
    return redirect(url_for('projects.list'))

@projects_bp.route('/export')
@login_required
def export():
    """Export all projects to CSV"""
    
    # Get all projects for current organization
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Project.name).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Name',
        'Description',
        'Status',
        'Budget',
        'Start Date',
        'End Date',
        'Leaders',
        'Volunteers',
        'Leader Count',
        'Volunteer Count'
    ])
    
    # Write project data
    for project in projects:
        # Get leader names
        leader_names = ', '.join([leader.name for leader in project.leaders])
        
        # Get volunteer names
        volunteer_names = ', '.join([volunteer.name for volunteer in project.volunteers])
        
        writer.writerow([
            project.name,
            project.description or '',
            project.status,
            f'{project.budget:.2f}' if project.budget else '0.00',
            project.start_date.strftime('%Y-%m-%d') if project.start_date else '',
            project.end_date.strftime('%Y-%m-%d') if project.end_date else '',
            leader_names,
            volunteer_names,
            len(project.leaders),
            len(project.volunteers)
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=projects_export_{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response


# ==================== LEADERSHIP / VOLUNTEER ASSIGNMENTS ====================

@projects_bp.route('/<int:id>/volunteers/add', methods=['POST'])
@login_required
def add_volunteer(id):
    """Add a volunteer to a project"""
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first()
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))

    member_id = request.form.get('member_id', type=int)
    if member_id:
        volunteer = Member.query.filter_by(
            id=member_id, organization_id=current_user.organization_id
        ).first()
        if not volunteer:
            flash('Member not found.', 'error')
        else:
            try:
                assign_member(project, volunteer, role='Volunteer', assigned_by=current_user.id)
                flash(f'{volunteer.name} added as volunteer.', 'success')
            except ProjectServiceError as e:
                flash(str(e), 'error')

    return redirect(url_for('projects.edit', id=id))


@projects_bp.route('/<int:id>/leaders/add', methods=['POST'])
@login_required
def add_leader(id):
    """Add a leader to a project"""
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first()
    if not project:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))

    member_id = request.form.get('member_id', type=int)
    if member_id:
        leader = Member.query.filter_by(
            id=member_id, organization_id=current_user.organization_id
        ).first()
        if not leader:
            flash('Member not found.', 'error')
        else:
            try:
                assign_member(project, leader, role='Leader', assigned_by=current_user.id)
                flash(f'{leader.name} added as leader.', 'success')
            except ProjectServiceError as e:
                flash(str(e), 'error')

    return redirect(url_for('projects.edit', id=id))


@projects_bp.route('/<int:id>/assignments/<int:assignment_id>/end', methods=['POST'])
@login_required
@admin_or_treasurer_required
def end_assignment_route(id, assignment_id):
    """End one member's assignment on a project: resignation, dismissal,
    being replaced, etc. This is how a leadership/volunteer term is closed
    out without waiting for the whole project to be closed for the year.
    """
    assignment = ProjectAssignment.query.join(Project).filter(
        ProjectAssignment.id == assignment_id,
        ProjectAssignment.project_id == id,
        Project.organization_id == current_user.organization_id
    ).first_or_404()

    end_reason = request.form.get('end_reason')
    end_notes = request.form.get('end_notes')

    try:
        end_assignment(assignment, end_reason=end_reason, ended_by=current_user.id, end_notes=end_notes)
        flash(f'{assignment.member.name} — {assignment.role.lower()} assignment ended ({end_reason}).', 'success')
    except ProjectServiceError as e:
        flash(str(e), 'error')

    return redirect(url_for('projects.edit', id=id))


@projects_bp.route('/<int:id>/close', methods=['POST'])
@login_required
@admin_or_treasurer_required
def close(id):
    """Close a project out for the year: ends every currently-open
    assignment as 'Term Completed' and marks the project Completed.
    """
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()

    try:
        close_project_for_year(project, ended_by=current_user.id)
        flash(f'"{project.name}" closed out for the year.', 'success')
    except ProjectServiceError as e:
        flash(str(e), 'error')

    return redirect(url_for('projects.view', id=id))


@projects_bp.route('/<int:id>/restart', methods=['GET', 'POST'])
@login_required
@admin_or_treasurer_required
def restart(id):
    """Start next year's iteration of a recurring project.

    Creates a new, linked Project row (see Project.previous_project_id)
    rather than reopening this one, so this year's history stays intact.
    """
    project = Project.query.filter_by(
        id=id, organization_id=current_user.organization_id
    ).first_or_404()

    if request.method == 'POST':
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else None
        carry_forward = request.form.get('carry_forward_people') == 'on'
        try:
            new_project = restart_project(
                project,
                start_date=start_date,
                carry_forward_people=carry_forward,
                created_by=current_user.id
            )
            flash(f'"{new_project.name}" started for the new cycle.', 'success')
            return redirect(url_for('projects.edit', id=new_project.id))
        except ProjectServiceError as e:
            flash(str(e), 'error')
            return redirect(url_for('projects.view', id=id))

    return render_template('project_restart.html', project=project)

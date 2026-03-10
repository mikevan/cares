"""
Project Management Blueprint
Handles all project-related routes including CRUD and export
"""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Project, Member, JournalEntry, JournalEntryLine, ChartOfAccounts
from datetime import datetime
from decimal import Decimal
from sqlalchemy import func

# Create the blueprint
projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


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
    project = Project.query.get_or_404(id)
    
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
                          view_mode=True)


@projects_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new():
    """Create new project"""
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
            return redirect(url_for('projects.list'))
        except Exception as e:
            flash(f'Error adding project: {str(e)}', 'error')
            db.session.expunge_all()  # Clear session to avoid stale data
    
    members = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).order_by(Member.name).all()
    return render_template('project_form.html', project=None, members=members)


@projects_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit existing project"""
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

@projects_bp.route('/<int:id>/volunteers/add', methods=['POST'])
@login_required
def add_volunteer(id):
    """Add a volunteer to a project"""
    project = Project.query.get_or_404(id)
    if project.organization_id != current_user.organization_id:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))

    member_id = request.form.get('member_id', type=int)
    if member_id:
        volunteer = Member.query.get_or_404(member_id)
        if volunteer not in project.volunteers:
            project.volunteers.append(volunteer)
            db.session.commit()
            flash(f'{volunteer.name} added as volunteer.', 'success')

    return redirect(url_for('projects.edit', id=id))


@projects_bp.route('/<int:id>/volunteers/<int:member_id>/remove', methods=['POST'])
@login_required
def remove_volunteer(id, member_id):
    """Remove a volunteer from a project"""
    project = Project.query.get_or_404(id)
    if project.organization_id != current_user.organization_id:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))

    member = Member.query.get_or_404(member_id)
    if member in project.volunteers:
        project.volunteers.remove(member)
        db.session.commit()
        flash(f'{member.name} removed from volunteers.', 'success')

    return redirect(url_for('projects.edit', id=id))


@projects_bp.route('/<int:id>/leaders/add', methods=['POST'])
@login_required
def add_leader(id):
    """Add a leader to a project"""
    project = Project.query.get_or_404(id)
    if project.organization_id != current_user.organization_id:
        flash('Project not found.', 'error')
        return redirect(url_for('projects.list'))

    member_id = request.form.get('member_id', type=int)
    if member_id:
        leader = Member.query.get_or_404(member_id)
        if leader not in project.leaders:
            project.leaders.append(leader)
            db.session.commit()
            flash(f'{leader.name} added as leader.', 'success')

    return redirect(url_for('projects.edit', id=id))
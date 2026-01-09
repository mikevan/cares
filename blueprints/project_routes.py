"""
Project Management Blueprint
Handles all project-related routes including CRUD and export
"""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from models import db, Project, Member
from datetime import datetime
from decimal import Decimal

# Create the blueprint
projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


# ==================== PROJECTS CRUD ====================

@projects_bp.route('/')
@login_required
def list():
    """List all projects"""
    projects = Project.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Project.name).all()
    return render_template('projects.html', projects=projects)


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
            db.session.rollback()
    
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
    return render_template('project_form.html', project=project, members=members)


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

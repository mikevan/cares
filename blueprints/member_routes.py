"""
Member Management Blueprint
Handles all member-related routes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Member
from datetime import datetime

# Create the blueprint
members_bp = Blueprint('members', __name__, url_prefix='/members')


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
                zip=request.form.get('zip'),
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
            member.zip = request.form.get('zip')
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
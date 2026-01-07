"""
User Management Blueprint
Handles all user-related routes including CRUD and password management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, Organization
from functools import wraps

# Create the blueprint
users_bp = Blueprint('users', __name__, url_prefix='/users')


# Decorator to require Admin role
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'Admin':
            flash('You must be an administrator to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== USER CRUD ====================

@users_bp.route('/')
@login_required
@admin_required
def list():
    """List all users in the current organization"""
    users = User.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(User.username).all()
    return render_template('users.html', users=users)


@users_bp.route('/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new():
    """Create new user"""
    if request.method == 'POST':
        try:
            # Validate username uniqueness
            existing_user = User.query.filter_by(username=request.form['username']).first()
            if existing_user:
                flash('Username already exists. Please choose a different username.', 'danger')
                return redirect(request.url)
            
            # Validate email uniqueness
            if request.form.get('email'):
                existing_email = User.query.filter_by(email=request.form['email']).first()
                if existing_email:
                    flash('Email already exists. Please use a different email.', 'danger')
                    return redirect(request.url)
            
            # Validate password
            password = request.form.get('password')
            password_confirm = request.form.get('password_confirm')
            
            if not password or len(password) < 8:
                flash('Password must be at least 8 characters long.', 'danger')
                return redirect(request.url)
            
            if password != password_confirm:
                flash('Passwords do not match.', 'danger')
                return redirect(request.url)
            
            # Create user
            user = User(
                username=request.form['username'],
                email=request.form['email'],
                role=request.form['role'],
                organization_id=current_user.organization_id,
                active=True
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash(f'User "{user.username}" created successfully!', 'success')
            return redirect(url_for('users.list'))
            
        except Exception as e:
            flash(f'Error creating user: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('user_form.html', user=None)


@users_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    """Edit existing user"""
    user = User.query.get_or_404(id)
    
    # Verify user belongs to same organization
    if user.organization_id != current_user.organization_id:
        flash('Permission denied.', 'danger')
        return redirect(url_for('users.list'))
    
    if request.method == 'POST':
        try:
            # Check if username changed and is unique
            if user.username != request.form['username']:
                existing_user = User.query.filter_by(username=request.form['username']).first()
                if existing_user:
                    flash('Username already exists. Please choose a different username.', 'danger')
                    return redirect(request.url)
            
            # Check if email changed and is unique
            if request.form.get('email') and user.email != request.form['email']:
                existing_email = User.query.filter_by(email=request.form['email']).first()
                if existing_email:
                    flash('Email already exists. Please use a different email.', 'danger')
                    return redirect(request.url)
            
            # Update user
            user.username = request.form['username']
            user.email = request.form['email']
            user.role = request.form['role']
            user.active = request.form.get('active') == 'on'
            
            db.session.commit()
            
            flash(f'User "{user.username}" updated successfully!', 'success')
            return redirect(url_for('users.list'))
            
        except Exception as e:
            flash(f'Error updating user: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('user_form.html', user=user)


@users_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(id):
    """Delete user"""
    user = User.query.get_or_404(id)
    
    # Verify user belongs to same organization
    if user.organization_id != current_user.organization_id:
        flash('Permission denied.', 'danger')
        return redirect(url_for('users.list'))
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('users.list'))
    
    # Prevent deleting the last admin
    if user.role == 'Admin':
        admin_count = User.query.filter_by(
            organization_id=current_user.organization_id,
            role='Admin',
            active=True
        ).count()
        if admin_count <= 1:
            flash('Cannot delete the last administrator account.', 'danger')
            return redirect(url_for('users.list'))
    
    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        flash(f'User "{username}" deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting user: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('users.list'))


@users_bp.route('/<int:id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_active(id):
    """Activate or deactivate a user"""
    user = User.query.get_or_404(id)
    
    # Verify user belongs to same organization
    if user.organization_id != current_user.organization_id:
        flash('Permission denied.', 'danger')
        return redirect(url_for('users.list'))
    
    # Prevent deactivating yourself
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('users.list'))
    
    # Prevent deactivating the last admin
    if user.role == 'Admin' and user.active:
        admin_count = User.query.filter_by(
            organization_id=current_user.organization_id,
            role='Admin',
            active=True
        ).count()
        if admin_count <= 1:
            flash('Cannot deactivate the last administrator account.', 'danger')
            return redirect(url_for('users.list'))
    
    try:
        user.active = not user.active
        db.session.commit()
        status = 'activated' if user.active else 'deactivated'
        flash(f'User "{user.username}" {status} successfully.', 'success')
    except Exception as e:
        flash(f'Error updating user: {str(e)}', 'danger')
        db.session.rollback()
    
    return redirect(url_for('users.list'))


# ==================== PASSWORD MANAGEMENT ====================

@users_bp.route('/<int:id>/change-password', methods=['GET', 'POST'])
@login_required
def change_password(id):
    """Change user password"""
    user = User.query.get_or_404(id)
    
    # Only admins or the user themselves can change password
    if current_user.id != user.id and current_user.role != 'Admin':
        flash('Permission denied.', 'danger')
        return redirect(url_for('index'))
    
    # Verify user belongs to same organization
    if user.organization_id != current_user.organization_id:
        flash('Permission denied.', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            # If user is changing their own password, verify current password
            if current_user.id == user.id:
                current_password = request.form.get('current_password')
                if not user.check_password(current_password):
                    flash('Current password is incorrect.', 'danger')
                    return redirect(request.url)
            
            # Validate new password
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not new_password or len(new_password) < 8:
                flash('New password must be at least 8 characters long.', 'danger')
                return redirect(request.url)
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(request.url)
            
            # Update password
            user.set_password(new_password)
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            
            # Redirect based on who changed the password
            if current_user.role == 'Admin' and current_user.id != user.id:
                return redirect(url_for('users.list'))
            else:
                return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'Error changing password: {str(e)}', 'danger')
            db.session.rollback()
    
    return render_template('change_password.html', user=user)


@users_bp.route('/profile')
@login_required
def profile():
    """View current user's profile"""
    return render_template('user_profile.html', user=current_user)
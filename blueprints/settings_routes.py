"""
Settings Management Blueprint
Handles organization settings
"""

from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Organization

# Create the blueprint
settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


# ==================== SETTINGS ====================

@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """Organization settings page"""
    if current_user.role not in ['Admin']:
        flash('Permission denied', 'error')
        return redirect(url_for('index'))

    org = Organization.query.get(current_user.organization_id)

    if request.method == 'POST':
        try:
            org.name = request.form['name']
            org.ein = request.form.get('ein')
            org.address = request.form.get('address')
            org.city = request.form.get('city')
            org.state = request.form.get('state')
            org.zip_code = request.form.get('zip_code')
            org.phone = request.form.get('phone')
            org.email = request.form.get('email')
            org.website = request.form.get('website')
            org.fiscal_year_start = int(request.form.get('fiscal_year_start', 1))
            css_code = request.form.get('css_file', '').strip()
            org.css_file = (css_code + '.css') if css_code else None

            dues_raw = request.form.get('dues_amount', '').strip()
            if dues_raw:
                try:
                    org.dues_amount = Decimal(dues_raw)
                except InvalidOperation:
                    flash('Dues amount must be a valid number (e.g. 150.00).', 'danger')
                    return render_template('settings.html', org=org)
            else:
                org.dues_amount = None

            db.session.commit()
            flash('Settings updated successfully!', 'success')
            return redirect(url_for('settings.index'))
        except Exception as e:
            flash(f'Error updating settings: {str(e)}', 'error')
            db.session.rollback()

    return render_template('settings.html', org=org)

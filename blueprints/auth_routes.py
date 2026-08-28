"""
Authentication Blueprint
Handles authentication routes and initialization
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Organization, Project, ChartOfAccounts
from datetime import datetime
from sqlalchemy import text, inspect
from extensions import limiter
from default_chart_of_accounts import DEFAULT_CHART_OF_ACCOUNTS
from services.usage_service import log_event
from audit_schema import install_audit_triggers
from services.audit_context import set_current_actor

# Create the blueprint
auth_bp = Blueprint('auth', __name__)


# ==================== AUTHENTICATION ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    """Login page and handler"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            # apply_audit_actor()'s before_request hook ran before this
            # request knew who was logging in (current_user wasn't
            # authenticated yet), so it set the actor contextvar to None.
            # The User.query.filter_by(...) lookup above already opened
            # this request's transaction under that None actor -- and
            # audit_context's SET LOCAL is applied once, in
            # SQLAlchemy's after_begin, when a transaction *begins*, not
            # retroactively when the contextvar changes mid-transaction.
            # So updating the contextvar here isn't enough on its own:
            # the still-open transaction from the lookup query would
            # carry the last_login UPDATE below and stay attributed to
            # no one. Commit now (nothing pending yet, so this is just a
            # clean transaction boundary) so the actor is set *before*
            # the next transaction begins, then do the actual write.
            set_current_actor(user.id)
            db.session.commit()
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_event('auth.login', organization_id=user.organization_id, user_id=user.id)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    #return render_template('login.html')
    org = Organization.query.first()
    return render_template('login.html',
                       org_code=org.css_file[:-4] if org and org.css_file else None,
                       org_name=org.name if org else 'CARES')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout handler"""
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('auth.login'))


def init_database(app):
    """Initialize database with default data"""
    with app.app_context():
        db.create_all()

        # Install (or refresh) the audit trail's trigger function and
        # per-table triggers now that audit_log and every audited table
        # exist. Idempotent -- see audit_schema.py. Uses db.engine
        # directly (not db.session) because this needs its own
        # transaction wrapping DDL, run by whatever role this app
        # context is connected as (the owner/migration role in a
        # properly separated production deployment -- see
        # docs/AUDIT_TRAIL.md).
        with db.engine.begin() as connection:
            install_audit_triggers(connection)

        # Ensure the users table has the `default_report_year` column; add it if missing
        try:
            inspector = inspect(db.engine)
            cols = [c['name'] for c in inspector.get_columns('users')]
            if 'default_report_year' not in cols:
                app.logger.info('users.default_report_year not found; attempting to add column')
                try:
                    dialect = db.engine.dialect.name
                    if dialect == 'postgresql' or dialect == 'mysql':
                        # Use IF NOT EXISTS where supported to avoid race errors
                        alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_report_year INTEGER"
                    else:
                        # SQLite and other dialects: standard ADD COLUMN
                        alter_sql = "ALTER TABLE users ADD COLUMN default_report_year INTEGER"

                    db.session.execute(text(alter_sql))
                    db.session.commit()

                    # Re-create inspector to refresh metadata and verify the column was added
                    inspector = inspect(db.engine)
                    cols2 = [c['name'] for c in inspector.get_columns('users')]
                    if 'default_report_year' in cols2:
                        app.logger.info('Added users.default_report_year column successfully')
                    else:
                        app.logger.error('Failed to add users.default_report_year column (still missing)')
                        raise RuntimeError('Failed to add users.default_report_year column')
                except Exception as e:
                    app.logger.exception(f'Attempt to add users.default_report_year failed: {e}')
                    # Re-create inspector and re-check in case another process added the column concurrently
                    try:
                        inspector = inspect(db.engine)
                        cols2 = [c['name'] for c in inspector.get_columns('users')]
                        if 'default_report_year' in cols2:
                            app.logger.info('users.default_report_year appears to have been added by another process')
                            # success
                        else:
                            # Not present after retry -> raise so ops can run a migration manually
                            raise
                    except Exception:
                        raise
        except Exception as e:
            app.logger.exception(f'Could not inspect users table for default_report_year column: {e}')
            raise

        # Ensure the users table has the `must_change_password` column; add it if missing
        try:
            inspector = inspect(db.engine)
            cols = [c['name'] for c in inspector.get_columns('users')]
            if 'must_change_password' not in cols:
                app.logger.info('users.must_change_password not found; attempting to add column')
                dialect = db.engine.dialect.name
                if dialect == 'postgresql' or dialect == 'mysql':
                    alter_sql = "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
                else:
                    alter_sql = "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"
                db.session.execute(text(alter_sql))
                db.session.commit()
                app.logger.info('Added users.must_change_password column')
        except Exception as e:
            app.logger.exception(f'Could not add users.must_change_password column: {e}')
            raise

        # Create default organization if none exists
        if not Organization.query.first():
            org = Organization(
                name=app.config.get('DEFAULT_ORGANIZATION', 'CARES - Example Chapter'),
                org_type='Chapter',
                fiscal_year_start=1,
                css_file='kofc.css'  # REGALIA (Knights of Columbus edition) branding by default
            )
            db.session.add(org)
            db.session.commit()
        
        # Create default admin user if none exists
        if not User.query.first():
            admin = User(
                username='admin',
                email='admin@example.com',
                role='Admin',
                organization_id=1,
                must_change_password=True,  # admin123 is a known default -- force a real one on first login
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
        
        # Create default Dues project if it doesn't exist
        if not Project.query.filter_by(name='Dues').first():
            dues_project = Project(
                name='Dues',
                description='Member dues and subscription payments',
                status='Active',
                organization_id=1
            )
            db.session.add(dues_project)
            db.session.commit()
        
        # Create default Chart of Accounts if empty. DEFAULT_CHART_OF_ACCOUNTS
        # is the same list init_db.py's create_complete_chart_of_accounts() uses
        # -- this used to be a second, hand-copied, incomplete list that had
        # drifted out of sync (missing accounts like 1410 Computer Equipment),
        # which only surfaced once the test harness correctly loaded demo data
        # against the same database whose Chart of Accounts this seeds.
        if ChartOfAccounts.query.count() == 0:
            for acc in DEFAULT_CHART_OF_ACCOUNTS:
                account = ChartOfAccounts(
                    account_number=acc[0],
                    account_name=acc[1],
                    account_type=acc[2],
                    account_subtype=acc[3],
                    normal_balance=acc[4],
                    active=acc[5]
                )
                db.session.add(account)
            
            db.session.commit()

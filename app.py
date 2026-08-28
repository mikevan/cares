"""
CARES - Community Accounting & Resource Engagement System
Main Flask Application
"""

import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_required, current_user
from flask_wtf import CSRFProtect
from models import db, User, Member, Project, JournalEntry
from services.reports import FinancialReports
from datetime import date 
from config import is_production, resolve_secret, parse_bool_env
from extensions import limiter
from blueprints.auth_routes import auth_bp, init_database
from blueprints.member_routes import members_bp
from blueprints.user_routes import users_bp
from blueprints.chart_of_accounts import chart_of_accounts_bp
from blueprints.transaction_routes import transactions_bp
from blueprints.project_routes import projects_bp
from blueprints.report_routes import reports_bp
from blueprints.settings_routes import settings_bp
from blueprints.ap_routes import ap_bp
from blueprints.translation_routes import translation_bp
from blueprints.audit_routes import audit_bp
from services.translation_service import translate_response, detect_language, SKIP_ROUTES
from services.audit_context import set_current_actor, clear_current_actor

IS_PRODUCTION = is_production()
# Explicit opt-in, off by default: turning this on sends full rendered page
# HTML -- including account balances, transaction memos, and member/donor
# PII -- to a third-party LLM API for translation. See maybe_translate()
# below and the code review's §5 for the full rationale.
ENABLE_TRANSLATION = parse_bool_env('ENABLE_TRANSLATION', default=False)

app = Flask(__name__)
app.url_map.strict_slashes = False  # Treat /route and /route/ as equivalent, fixes 308/302 redirect issue
# Load default application configuration (override with instance/config.py if present)
app.config.from_object('config.Config')
app.config.from_pyfile('config.py', silent=True)
app.config['SECRET_KEY'] = resolve_secret(
    'SECRET_KEY', 'dev-secret-key-change-in-production', production=IS_PRODUCTION
)
app.config['SQLALCHEMY_DATABASE_URI'] = resolve_secret(
    'DATABASE_URL', 'postgresql://postgres:dev123@localhost/kofc_accounting', production=IS_PRODUCTION
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
csrf = CSRFProtect(app)
limiter.init_app(app)

@app.context_processor
def inject_branding():
    from models import Organization
    org_css_file = 'branding.css'
    org_code = None
    # Authenticated users get their own organization's branding. Anonymous
    # visitors (e.g. the login screen) fall back to the first organization in
    # the deployment, matching the heuristic auth_routes.login() already uses
    # to pick a logo/name to show before anyone has signed in.
    if current_user.is_authenticated:
        org = Organization.query.get(current_user.organization_id)
    else:
        org = Organization.query.first()
    if org and org.css_file:
        org_css_file = org.css_file
        org_code = org.css_file[:-4]
    return dict(
        APP_NAME=app.config.get('APP_NAME'),
        APP_VERSION=app.config.get('APP_VERSION'),
        DEFAULT_ORGANIZATION=app.config.get('DEFAULT_ORGANIZATION'),
        org_css_file=org_css_file,
        org_code=org_code
    )

login_manager.login_view = 'auth.login' 

app.register_blueprint(auth_bp)
app.register_blueprint(members_bp)
app.register_blueprint(users_bp)
app.register_blueprint(chart_of_accounts_bp)
app.register_blueprint(transactions_bp)
app.register_blueprint(projects_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(ap_bp)
app.register_blueprint(translation_bp)
app.register_blueprint(audit_bp)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.before_request
def require_password_change():
    """Force a redirect to the change-password page for any account still
    flagged must_change_password -- the seeded default admin account above
    all, since admin123 is a known, publicly-documented default.
    """
    if not current_user.is_authenticated:
        return None
    if not getattr(current_user, 'must_change_password', False):
        return None
    allowed_endpoints = {'users.change_password', 'auth.logout', 'static'}
    if request.endpoint in allowed_endpoints:
        return None
    flash('Please choose a new password before continuing.', 'warning')
    return redirect(url_for('users.change_password', id=current_user.id))


@app.before_request
def apply_audit_actor():
    """
    Tell the audit trail's trigger function who's making requests on this
    thread, before any of this request's database writes happen. See
    services/audit_context.py for how this reaches Postgres.
    """
    set_current_actor(current_user.id if current_user.is_authenticated else None)


@app.teardown_request
def clear_audit_actor(exc=None):
    """Threads are reused across requests -- without this, one user's
    actions could be attributed to whoever the same worker thread serves
    next."""
    clear_current_actor()


# ==================== DASHBOARD ====================

@app.route('/')
@login_required
def index():
    member_count = Member.query.filter_by(
        organization_id=current_user.organization_id,
        active=True
    ).count()
    
    project_count = Project.query.filter_by(
        organization_id=current_user.organization_id,
        status='Active'
    ).count()
    
    # Get cash balance from Chart of Accounts
    reports = FinancialReports(db.session, current_user.organization_id)
    balance_sheet = reports.balance_sheet()
    cash_balance = sum(
        acc['balance'] for acc in balance_sheet['assets']['accounts']
        if acc['number'].startswith('10')
    )
    
    # Recent transactions
    recent_transactions = JournalEntry.query\
        .join(Project)\
        .filter(Project.organization_id == current_user.organization_id)\
        .order_by(JournalEntry.entry_date.desc())\
        .limit(10)\
        .all()
    
    return render_template('index.html',
                         member_count=member_count,
                         project_count=project_count,
                         cash_balance=cash_balance,
                         recent_transactions=recent_transactions)

@app.after_request
def maybe_translate(response):
    """Automatically translate HTML responses for non-English browsers.

    Off by default (see ENABLE_TRANSLATION above) -- this sends the full
    rendered page, including live financial data and member/donor PII, to
    a third-party translation API. A chapter must explicitly set
    ENABLE_TRANSLATION=true (and GROQ_API_KEY) to turn it on.
    """
    if not ENABLE_TRANSLATION:
        return response
    if 'text/html' not in response.content_type:
        return response
    if request.path in SKIP_ROUTES or request.path.startswith('/static'):
        return response

    lang = detect_language(request.headers.get('Accept-Language', ''))
    if lang == 'en':
        return response

    try:
        html = response.get_data(as_text=True)
        translated = translate_response(html, lang, request.path)
        response.set_data(translated)
    except Exception as exc:
        app.logger.warning(f'Translation middleware error: {exc}')

    response.headers['Vary'] = 'Accept-Language'
    return response

if __name__ == '__main__':
    init_database(app)
    app.run(debug=not IS_PRODUCTION, host='0.0.0.0', port=5000)

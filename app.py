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
from blueprints.audit_routes import audit_bp
from services.translation_service import translate_response, detect_language, SKIP_ROUTES
from services.audit_context import set_current_actor, clear_current_actor
from services.tenancy import (
    set_current_organization, set_current_organization_scope,
    clear_current_organization, apply_to_open_transaction,
)
from services.hierarchy import descendant_ids

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
# Two connections, two roles. See setup_runtime_role.py.
#
#   DATABASE_URL          owner. Runs migrations and DDL.
#   RUNTIME_DATABASE_URL  restricted role. Serves requests.
#
# The split exists because a table's OWNER is not subject to that table's
# row-level security policies, and because audit_log's tamper-resistance is
# a REVOKE that does not apply to the owner either. An app connecting as the
# owner keeps every screen working and silently has neither control.
#
# CARES_ADMIN_CONNECTION is set by migrate_production.py before it imports
# this module, because migrations genuinely need the owner. It is not
# something to set on a serving process.
_ADMIN_CONNECTION = os.environ.get('CARES_ADMIN_CONNECTION', '').strip().lower() == 'true'
_OWNER_DATABASE_URL = resolve_secret(
    'DATABASE_URL', 'postgresql://postgres:dev123@localhost/kofc_accounting', production=IS_PRODUCTION
)
_RUNTIME_DATABASE_URL = os.environ.get('RUNTIME_DATABASE_URL', '').strip()
app.config['SQLALCHEMY_DATABASE_URI'] = (
    _OWNER_DATABASE_URL if (_ADMIN_CONNECTION or not _RUNTIME_DATABASE_URL)
    else _RUNTIME_DATABASE_URL
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


# Verified once, on the first request this process serves. Deliberately not
# at import: the database may not be reachable yet on some deploy paths, and
# a check that prevents the process from starting cannot report what it
# found.
_SECURITY_VERIFIED = {'done': False, 'report': None}


def _run_security_check():
    """Ask the database what protections actually apply to this connection.

    In production a failure is fatal -- every request is refused -- because
    the alternative is a council operating for months believing it has
    isolation and an immutable audit trail while having neither. That is the
    failure mode a treasurer discovers in a deposition, not in a log.

    Outside production it warns once and continues, so development and the
    demo keep working against a single owner connection exactly as before.
    """
    from services.security_check import verify_runtime_security, format_report

    try:
        with db.engine.connect() as connection:
            report = verify_runtime_security(connection)
    except Exception as exc:
        app.logger.warning('Runtime security check could not run: %s', exc)
        return None

    _SECURITY_VERIFIED['report'] = report
    if report['secure']:
        app.logger.info('Runtime security verified: role %s, isolation enforced, '
                        'audit_log immutable', report['role_name'])
        return report

    banner = ('\n' + '=' * 72 + '\n'
              'RUNTIME SECURITY CHECK FAILED\n' + '=' * 72 + '\n'
              + format_report(report) + '\n' + '=' * 72)
    if IS_PRODUCTION:
        app.logger.critical(banner)
    else:
        app.logger.warning(banner)
    return report


@app.before_request
def enforce_runtime_security():
    """Refuse to serve a production deployment without its controls."""
    if not _SECURITY_VERIFIED['done']:
        _SECURITY_VERIFIED['done'] = True
        _run_security_check()

    report = _SECURITY_VERIFIED['report']
    if not IS_PRODUCTION or report is None or report.get('secure'):
        return None
    # 503, not 500: the application is fine, its configuration is not, and
    # the distinction matters to whoever is paged.
    return (render_template('security_misconfigured.html',
                            findings=report.get('findings', [])), 503)


@app.before_request
def apply_tenant_context():
    """Establish which organization this request writes to and which ones it
    may read, before any query runs.

    Ordering matters and is not obvious: this must land before the first
    database read of the request, because services/tenancy.py pushes the
    settings on `after_begin` -- when a transaction starts. Set the
    organization after a query has already opened the transaction and the
    settings arrive one transaction late, which is precisely the bug that
    once left login's last_login update with no audit actor.

    descendant_ids() runs one recursive query against `organizations` per
    request. At the scale this is built for -- a national body, three states,
    a hundred councils -- that is a hundred-odd rows and costs nothing. If a
    much larger tree ever makes it show up in a profile, cache it on the
    organization row and invalidate on parent_id change; do not move the
    recursion into the RLS policy, where it would run per row.
    """
    if not current_user.is_authenticated:
        set_current_organization(None)
        set_current_organization_scope(None)
        return None
    org_id = current_user.organization_id
    set_current_organization(org_id)

    # Push onto the transaction that is ALREADY open, rather than waiting
    # for after_begin to fire on the next one.
    #
    # require_password_change() is registered before this handler and its
    # first statement reads current_user, which fires Flask-Login's user
    # loader -- the request's first query, and therefore the start of this
    # request's transaction. tenancy.py pushes its settings on after_begin,
    # so that transaction began carrying an EMPTY organization, and
    # after_begin does not fire again when the context changes mid-way.
    # Every later query in the request then ran with no tenant context, and
    # RLS returned zero rows: correct behaviour, wrong cause. The entire
    # application rendered as an empty database.
    #
    # Invisible in development and in the test suite, both of which connect
    # as the table OWNER, which is exempt from its own tables' policies.
    # It appears only under the restricted runtime role -- the configuration
    # that actually matters.
    apply_to_open_transaction(db.session)

    try:
        set_current_organization_scope(descendant_ids(org_id))
    except Exception:
        # A hierarchy lookup that fails must not widen visibility. Falling
        # back to None means "this organization only" (see tenancy.py).
        set_current_organization_scope(None)

    # Again, because the scope was only known after descendant_ids() ran.
    apply_to_open_transaction(db.session)
    return None


@app.teardown_request
def clear_tenant_context(exc=None):
    """Same reason as clear_audit_actor: worker threads outlive requests."""
    clear_current_organization()


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

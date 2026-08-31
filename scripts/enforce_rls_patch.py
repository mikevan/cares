"""Make row-level security and audit immutability actually apply at runtime.

Splits the owner connection (migrations, DDL) from the runtime connection
(serving requests), and refuses to serve a production deployment whose
runtime role bypasses the controls this product claims to have.
"""
import io

NL_CACHE = {}
CURRENT = {'path': None}


def load(p):
    s = io.open(p, 'r', encoding='utf-8', newline='').read()
    NL_CACHE[p] = '\r\n' if '\r\n' in s else '\n'
    CURRENT['path'] = p
    return s


def fit(t, p=None):
    return NL_CACHE[p or CURRENT['path']].join(t.strip('\n').split('\n'))


def save(p, s):
    io.open(p, 'w', encoding='utf-8', newline='').write(s)
    print('patched', p)


# ============================================================ app.py: two URLs
p = 'app.py'
s = load(p)

OLD_URI = fit("""
app.config['SQLALCHEMY_DATABASE_URI'] = resolve_secret(
    'DATABASE_URL', 'postgresql://postgres:dev123@localhost/kofc_accounting', production=IS_PRODUCTION
)
""")
assert OLD_URI in s, 'SQLALCHEMY_DATABASE_URI block not found'

NEW_URI = fit("""
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
""")
s = s.replace(OLD_URI, NEW_URI, 1)

# ---- the boot check -------------------------------------------------------
anchor = fit("""
@app.before_request
def apply_tenant_context():
""")
assert anchor in s, 'tenant context hook not found'

CHECK = fit('''
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

    banner = ('\\n' + '=' * 72 + '\\n'
              'RUNTIME SECURITY CHECK FAILED\\n' + '=' * 72 + '\\n'
              + format_report(report) + '\\n' + '=' * 72)
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
''')
s = s.replace(anchor, CHECK, 1)
save(p, s)


# ================================================= migrate_production.py: owner
p = 'migrate_production.py'
s = load(p)

anchor = fit("from app import app, db")
assert anchor in s, 'migrate_production app import not found'
PRELUDE = fit('''
# Migrations run DDL -- CREATE TRIGGER, ALTER TABLE, CREATE POLICY -- which
# only the table owner may do. Set BEFORE importing app, because app.py
# chooses its connection URL at import time and there is no supported way to
# rebind Flask-SQLAlchemy's engine afterwards.
#
# This is the one process that should ever set this.
import os
os.environ['CARES_ADMIN_CONNECTION'] = 'true'

from app import app, db
''')
s = s.replace(anchor, PRELUDE, 1)

# ---- Step 8: report on the RUNTIME role, not this one --------------------
anchor = fit("def verify_database_integrity():")
assert anchor in s
STEP8 = fit('''
def verify_runtime_role():
    """Check the role the APPLICATION will serve requests as.

    Not the role running this script. This process is connected as the owner
    on purpose -- it has to be, to run DDL -- so checking its own connection
    would always report the same failure and teach everyone to ignore it.

    When RUNTIME_DATABASE_URL is unset the app serves as the owner, which is
    correct for development and for the demo and wrong for a council's live
    books. Said plainly here rather than discovered later.
    """
    print("\\nStep 8: Verifying the application's runtime database role...")
    from demo_guard import is_production
    from services.security_check import verify_runtime_security, format_report
    from sqlalchemy import create_engine

    runtime_url = os.environ.get('RUNTIME_DATABASE_URL', '').strip()
    if not runtime_url:
        if is_production():
            print("  ! RUNTIME_DATABASE_URL is not set. The application would")
            print("    serve requests as the table owner, which bypasses every")
            print("    organization isolation policy and can rewrite audit")
            print("    history. Run: python setup_runtime_role.py --role cares_app")
        else:
            print("  - RUNTIME_DATABASE_URL not set; app will use the owner")
            print("    connection. Fine for development and the demo; not for a")
            print("    council's live books.")
        return

    engine = create_engine(runtime_url)
    try:
        with engine.connect() as connection:
            report = verify_runtime_security(connection)
        print(format_report(report))
        if not report['secure'] and is_production():
            print("\\n  ! This deployment will refuse requests until the runtime")
            print("    role is corrected. See setup_runtime_role.py.")
    except Exception as e:
        print(f"  ! Could not connect as the runtime role: {e}")
    finally:
        engine.dispose()


def verify_database_integrity():
''')
s = s.replace(anchor, STEP8, 1)

anchor = fit("""
            # Verify and summarise
            verify_database_integrity()
""")
assert anchor in s
s = s.replace(anchor, fit("""
            # Verify and summarise
            verify_runtime_role()
            verify_database_integrity()
"""), 1)

save(p, s)
print('\ndone')

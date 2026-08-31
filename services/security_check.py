"""
Runtime security verification.

Everything in rls_schema.py and audit_schema.py is conditional on one fact
that nothing in this codebase has ever checked: WHICH DATABASE ROLE THE
APPLICATION CONNECTS AS.

    Row-level security policies do not apply to a table's owner. The
    policies are installed with ENABLE, not FORCE, deliberately -- migrations,
    loaders and the test harness must keep working -- so an app connecting
    as the owner reads and writes every organization's rows exactly as it
    did before multi-tenancy existed.

    The audit trail's tamper-RESISTANCE is a REVOKE on audit_log. An app
    connecting as the owner can UPDATE and DELETE audit rows freely. It
    keeps tamper-evidence (the hash chain still breaks) but loses the
    property the product's strongest claim rests on.

Both mechanisms fail SILENTLY when this is wrong. Nothing errors, nothing
logs, every screen looks correct, and every test passes. A deployment can
run for years believing it has controls it does not have -- which is
precisely the kind of defect that is discovered by an auditor rather than
by an engineer.

So this module asks the database directly, and app.py refuses to serve a
production deployment that fails.

WHAT DEFEATS RLS, ALL OF WHICH ARE CHECKED
------------------------------------------
    table owner     policies do not apply (unless FORCE'd, which they
                    are not, and should not be -- see rls_schema.py)
    SUPERUSER       bypasses all policies, always
    BYPASSRLS       exactly what it says; grantable independently

The first is the one a real deployment gets wrong, because
`postgresql://postgres:...` is what every quickstart hands you.
"""
from sqlalchemy import text


# Queries deliberately hit the catalog only -- no locks on business tables,
# nothing that can block behind a migration holding ACCESS EXCLUSIVE.
_ROLE_SQL = text("""
    SELECT current_user                                   AS role_name,
           r.rolsuper                                     AS is_superuser,
           r.rolbypassrls                                 AS bypasses_rls
      FROM pg_roles r
     WHERE r.rolname = current_user
""")

_OWNERSHIP_SQL = text("""
    SELECT count(*) FILTER (WHERE pg_get_userbyid(c.relowner) = current_user) AS owned,
           count(*)                                                          AS total
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r'
""")

_AUDIT_PRIV_SQL = text("""
    SELECT has_table_privilege(current_user, 'audit_log', 'INSERT') AS can_insert,
           has_table_privilege(current_user, 'audit_log', 'SELECT') AS can_select,
           has_table_privilege(current_user, 'audit_log', 'UPDATE') AS can_update,
           has_table_privilege(current_user, 'audit_log', 'DELETE') AS can_delete,
           has_table_privilege(current_user, 'audit_log', 'TRUNCATE') AS can_truncate
""")


def verify_runtime_security(connection):
    """Report what protections are actually in force on THIS connection.

    Takes a connection rather than opening one, so the caller decides which
    role is being audited -- the point of the exercise is that the answer
    differs between the migration's connection and the app's.

    Returns a dict. Never raises for a failed check: a check that crashes
    the thing it is checking teaches operators to remove it.
    """
    report = {
        'role_name': None,
        'is_superuser': False,
        'bypasses_rls': False,
        'owns_tables': False,
        'tables_owned': 0,
        'tables_total': 0,
        'audit_log': {},
        'errors': [],
    }
    try:
        row = connection.execute(_ROLE_SQL).first()
        if row is not None:
            report['role_name'] = row.role_name
            report['is_superuser'] = bool(row.is_superuser)
            report['bypasses_rls'] = bool(row.bypasses_rls)
    except Exception as e:
        report['errors'].append(f'role lookup failed: {e}')

    try:
        row = connection.execute(_OWNERSHIP_SQL).first()
        report['tables_owned'] = row.owned or 0
        report['tables_total'] = row.total or 0
        # Owning ANY business table is enough to matter -- a role that owns
        # half of them bypasses policies on that half, which is not a
        # partial failure but a complete one.
        report['owns_tables'] = report['tables_owned'] > 0
    except Exception as e:
        report['errors'].append(f'ownership lookup failed: {e}')

    try:
        row = connection.execute(_AUDIT_PRIV_SQL).first()
        report['audit_log'] = {
            'can_insert': bool(row.can_insert),
            'can_select': bool(row.can_select),
            'can_update': bool(row.can_update),
            'can_delete': bool(row.can_delete),
            'can_truncate': bool(row.can_truncate),
        }
    except Exception as e:
        report['errors'].append(f'audit_log privilege lookup failed: {e}')

    report['findings'] = _findings(report)
    report['rls_enforced'] = not (
        report['owns_tables'] or report['is_superuser'] or report['bypasses_rls']
    )
    report['audit_log_immutable'] = (
        report['audit_log'].get('can_insert') is True
        and not report['audit_log'].get('can_update', True)
        and not report['audit_log'].get('can_delete', True)
        and not report['audit_log'].get('can_truncate', True)
        and not report['is_superuser']
    )
    report['secure'] = (
        report['rls_enforced']
        and report['audit_log_immutable']
        and not report['errors']
    )
    return report


def _findings(report):
    """Each finding names the mechanism that is off and why it matters.

    Phrased for whoever is reading a deploy log at 2am, not for whoever
    wrote this file.
    """
    out = []
    role = report['role_name'] or 'unknown'

    if report['is_superuser']:
        out.append(
            f"Role '{role}' is a SUPERUSER. It bypasses every row-level "
            f"security policy and can modify or delete audit history. No "
            f"database-level control in this application applies to it."
        )
    if report['bypasses_rls'] and not report['is_superuser']:
        out.append(
            f"Role '{role}' has BYPASSRLS. Organization isolation policies "
            f"do not apply to it."
        )
    if report['owns_tables']:
        out.append(
            f"Role '{role}' owns {report['tables_owned']} of "
            f"{report['tables_total']} tables. A table's owner is not subject "
            f"to that table's policies, so organization isolation is inactive "
            f"for this connection. Run setup_runtime_role.py and point "
            f"RUNTIME_DATABASE_URL at the restricted role."
        )
    priv = report['audit_log']
    writable = [name for name, key in
                (('UPDATE', 'can_update'), ('DELETE', 'can_delete'), ('TRUNCATE', 'can_truncate'))
                if priv.get(key)]
    if writable:
        out.append(
            f"Role '{role}' can {', '.join(writable)} audit_log. Audit history "
            f"is tamper-EVIDENT (the hash chain still breaks) but not "
            f"tamper-RESISTANT. Anyone holding the application's own database "
            f"credentials can rewrite it."
        )
    if priv and not priv.get('can_insert'):
        out.append(
            f"Role '{role}' cannot INSERT into audit_log. The audit trigger "
            f"fires on every write, so this deployment cannot record ANY "
            f"change -- business writes will fail."
        )
    for e in report['errors']:
        out.append(f"Check did not complete: {e}")
    return out


def format_report(report):
    """Multi-line, human-readable. Returned rather than printed so the
    caller decides between stdout, a logger, and an exception message."""
    lines = []
    role = report['role_name'] or 'unknown'
    verdict = 'SECURE' if report['secure'] else 'NOT ENFORCED'
    lines.append(f"  Database role:        {role}")
    lines.append(f"  Owns tables:          {report['tables_owned']}/{report['tables_total']}")
    lines.append(f"  Superuser:            {report['is_superuser']}")
    lines.append(f"  Bypasses RLS:         {report['bypasses_rls']}")
    lines.append(f"  Org isolation:        {'enforced' if report['rls_enforced'] else 'INACTIVE'}")
    lines.append(f"  audit_log immutable:  {'yes' if report['audit_log_immutable'] else 'NO'}")
    lines.append(f"  Verdict:              {verdict}")
    for f in report['findings']:
        lines.append("")
        lines.append("  ! " + _wrap(f, indent='    '))
    return '\n'.join(lines)


def _wrap(text_value, width=72, indent='    '):
    words = text_value.split()
    lines, current = [], ''
    for w in words:
        if current and len(current) + 1 + len(w) > width:
            lines.append(current)
            current = w
        else:
            current = f'{current} {w}'.strip()
    if current:
        lines.append(current)
    return ('\n' + indent).join(lines)

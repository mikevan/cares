"""
CARES Audit Trail -- Database-Level Capture
=============================================

This is the single source of truth for the audit trail's database-side
schema: which tables are audited, the trigger function that captures every
change to them, and the restricted production role that makes the whole
thing tamper-resistant. See models.py::AuditLog for the ORM-side mapping
of the table this writes to, and AUDIT_TRAIL.md for the full design
rationale and required production setup.

Why a database trigger instead of an application-level hook
-------------------------------------------------------------
The threat this defends against is someone with legitimate access to the
system -- a treasurer, a compromised admin account -- trying to alter or
delete financial records to cover their tracks. An application-level hook
(a SQLAlchemy event listener, a decorator on a Flask route) only fires
when a change goes through that specific code path. Anyone with direct
database access -- which a treasurer or a compromised app credential may
well have -- can bypass it entirely with a raw UPDATE or DELETE statement.
A trigger defined on the table itself fires no matter how the row was
changed, including from a bare psql prompt.

Why every row is hash-chained
-------------------------------
Postgres grants (see grant_restricted_runtime_role below) stop the
application's own database role from ever running UPDATE/DELETE/TRUNCATE
against audit_log. But grants are a property of the current schema; they
don't prove after the fact that nothing has changed. Every row's row_hash
is a SHA-256 of its own contents (table, operation, before/after JSON,
actor, exact timestamp) chained to the previous row's row_hash. Editing or
deleting even one row breaks the chain from that point forward, and
anyone with SELECT on audit_log can verify that independently -- they
don't have to take the database's word for its own integrity.

Why a single global advisory lock, not per-table chains
-----------------------------------------------------------
Concurrent transactions each computing "the current chain tail" and
appending to it would otherwise be a race: two transactions could both
read the same prev_hash and both insert next, forking the chain in a way
that looks like tampering but is really just an unprotected read-then-write.
pg_advisory_xact_lock() (held for the duration of the writing transaction,
released automatically at commit/rollback) serializes every audited write
across every table behind one lock, guaranteeing a genuinely linear,
verifiable chain. For a single council's transaction volume this is not a
meaningful throughput concern; it would need revisiting long before this
software's realistic scale.
"""

from sqlalchemy import text

# Every mutable table that holds financial data, membership data, or
# access control (users/roles) gets a trigger. Deliberately excluded:
#   - translation_cache: a cache, not user data, zero fraud relevance
#   - usage_events: itself a log (see services/usage_service.py); auditing
#     a log adds noise without adding evidence
#   - audit_log: itself -- see below for why the ORM can't write to it,
#     and why the DB grants below stop even the app's own trigger-writing
#     role from ever rewriting a row after the fact
AUDITED_TABLES = [
    'organizations',
    'users',
    'members',
    'member_dues_payments',
    'project_assignments',
    'projects',
    'chart_of_accounts',
    'journal_entries',
    'journal_entry_lines',
    'donors',
    'donations',
    'currencies',
    'vendors',
    'invoices',
    'invoice_payments',
    'receivables',
    'receivable_payments',
    # Knights of Columbus Form 1295 support (see services/kofc_form_1295.py):
    # both feed a compliance document a trustee signs and files, so
    # changes to either belong in the tamper-evident trail like
    # everything else here.
    'membership_events',
    'form_1295_submissions',
]

_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION audit_trigger_fn() RETURNS TRIGGER AS $$
DECLARE
    v_old JSONB;
    v_new JSONB;
    v_row_id INTEGER;
    v_user_id INTEGER;
    v_prev_hash TEXT;
    v_payload TEXT;
    v_row_hash TEXT;
    v_changed_at TIMESTAMPTZ;
BEGIN
    -- Serialize every audited write, across every table, behind one
    -- transaction-scoped advisory lock so the hash chain can never fork
    -- under concurrent writers. Released automatically at commit/rollback.
    PERFORM pg_advisory_xact_lock(hashtext('cares_audit_log_chain'));

    -- Captured once and reused for both the hash payload and the stored
    -- column below. clock_timestamp() is volatile -- calling it twice
    -- would give two slightly different values, which would make later
    -- hash verification fail on every single row.
    v_changed_at := clock_timestamp();

    IF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD);
        v_new := NULL;
        v_row_id := (v_old->>'id')::INTEGER;
    ELSIF TG_OP = 'UPDATE' THEN
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
        v_row_id := (v_new->>'id')::INTEGER;
    ELSE
        v_old := NULL;
        v_new := to_jsonb(NEW);
        v_row_id := (v_new->>'id')::INTEGER;
    END IF;

    -- Set by services/audit_context.py once per transaction. NULL here
    -- means either a background/maintenance script (init_db.py,
    -- load_comprehensive_data.py) or -- more importantly -- a change that
    -- did not go through the application at all. That is itself useful
    -- evidence: a real trustee audit should treat a NULL actor on a
    -- production system as a change to ask about, not to ignore.
    BEGIN
        v_user_id := NULLIF(current_setting('app.current_user_id', true), '')::INTEGER;
    EXCEPTION WHEN others THEN
        v_user_id := NULL;
    END;

    SELECT row_hash INTO v_prev_hash FROM audit_log ORDER BY id DESC LIMIT 1;

    v_payload := coalesce(v_prev_hash, '<genesis>') || '|' || TG_TABLE_NAME || '|' || TG_OP || '|'
                 || coalesce(v_old::text, '') || '|' || coalesce(v_new::text, '')
                 || '|' || coalesce(v_user_id::text, '<unknown>') || '|' || v_changed_at::text;
    v_row_hash := encode(digest(v_payload, 'sha256'), 'hex');

    INSERT INTO audit_log(table_name, row_id, operation, old_data, new_data,
                           changed_by_user_id, db_role, changed_at, prev_hash, row_hash)
    VALUES (TG_TABLE_NAME, v_row_id, TG_OP, v_old, v_new, v_user_id, current_user,
            v_changed_at, v_prev_hash, v_row_hash);

    RETURN NULL; -- AFTER trigger; return value is ignored either way
END;
$$ LANGUAGE plpgsql;
"""


def install_audit_triggers(connection):
    """
    Idempotent: safe to call every time the schema is (re)built (app
    startup, test-session setup, a fresh deployment). Creates pgcrypto if
    it isn't already installed, (re)creates the trigger function, and
    (re)attaches it to every table in AUDITED_TABLES.

    Must run AFTER db.create_all() -- the audited tables, and audit_log
    itself (via models.AuditLog), need to already exist.

    `connection` must be a SQLAlchemy Connection bound to a role that owns
    these tables (able to CREATE EXTENSION / CREATE FUNCTION / CREATE
    TRIGGER). In production that's a migration/owner role -- deliberately
    NOT the restricted runtime role the app connects as day to day (see
    grant_restricted_runtime_role below and AUDIT_TRAIL.md).
    """
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    connection.execute(text(_TRIGGER_FUNCTION_SQL))
    for table in AUDITED_TABLES:
        connection.execute(text(f"DROP TRIGGER IF EXISTS trg_audit_{table} ON {table}"))
        connection.execute(text(
            f"CREATE TRIGGER trg_audit_{table} "
            f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn()"
        ))


def grant_restricted_runtime_role(connection, role_name, password):
    """
    Creates (or updates the password of) the role the application should
    connect as in production, and applies the exact grants that make the
    audit trail's tamper-resistance real rather than aspirational:

    - Full SELECT/INSERT/UPDATE/DELETE on every business table (the app
      needs to do its normal job).
    - INSERT and SELECT ONLY on audit_log -- explicitly no UPDATE, DELETE,
      or TRUNCATE. This is what stops a SQL-injection bug or someone who
      has the app's own database credentials from editing or deleting
      audit history, even though that same role is what the trigger uses
      to write new rows.

    This is NOT run automatically against a real deployment's database --
    it's meant to be run once, deliberately, by whoever controls that
    database, using a role with the privileges to create another role and
    grant/revoke on existing tables (typically the same owner role used to
    run install_audit_triggers). Wiring it into an automatic startup path
    would mean the app's own credentials could re-grant themselves
    whatever they wanted, which defeats the point. See AUDIT_TRAIL.md
    for the deployment procedure.
    """
    connection.execute(text(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :role_name) THEN "
        "CREATE ROLE " + _quote_ident(role_name) + " LOGIN PASSWORD :password; "
        "ELSE "
        "ALTER ROLE " + _quote_ident(role_name) + " PASSWORD :password; "
        "END IF; END $$;"
    ), {'role_name': role_name, 'password': password})

    role_ident = _quote_ident(role_name)
    connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role_ident}"))
    connection.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role_ident}"))

    business_tables = ', '.join(AUDITED_TABLES + ['translation_cache', 'usage_events'])
    connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {business_tables} TO {role_ident}"))

    connection.execute(text(f"GRANT SELECT, INSERT ON audit_log TO {role_ident}"))
    connection.execute(text(f"REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {role_ident}"))


def _quote_ident(identifier):
    """
    Minimal defense-in-depth for role_name, which in every real call site
    is an operator-supplied deployment constant, not user input -- but a
    role name can't be parameterized like a value can (SET/CREATE ROLE
    don't accept bind params for identifiers), so it gets validated and
    quoted rather than trusted as-is.
    """
    if not identifier.replace('_', '').isalnum():
        raise ValueError(f"Refusing to use {identifier!r} as a SQL identifier")
    return '"' + identifier + '"'

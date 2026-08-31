"""Wire multi-tenancy into the running application.

rls_schema.py and services/tenancy.py were delivered but never connected to
anything: nothing set the organization context on a request, and nothing
installed the policies during migration. This patch connects them, adds
hierarchy scope so a state or national body can read down its own branch of
the tree without being able to post to it, and stops the Trustee Audit
Report from showing every organization's rows to whoever opens it.
"""
import io
import os

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


# =========================================================== hierarchy service
HIERARCHY = '''"""
Organizational hierarchy.

CARES V2 is one deployment holding a whole order: a national body, its state
or regional councils, and the local councils under those -- four levels in
the Knights of Columbus case (Supreme -> State -> District -> Council).
`organizations.parent_id` already carried that shape; nothing read it.

Two questions get asked of this file, and they have deliberately different
answers:

    which organizations may I READ?     my own branch, root to leaves
    which organization may I WRITE?     exactly one -- my own

That asymmetry is the whole design. A state deputy must be able to roll up
a hundred councils' Form 1295 figures. A state deputy must NOT be able to
post a journal entry into a council's books, because the council's trustees
sign that ledger under Section 145 and the audit trail has to name a real
person inside that council. rls_schema.py enforces exactly this split:
USING (readable scope) and WITH CHECK (own organization only).

WHERE THE TRUST BOUNDARY ACTUALLY SITS
--------------------------------------
The scope is computed here, from `organizations.parent_id`, and pushed into
a Postgres session setting that the policies read back. It is NOT recomputed
per row inside the policy: a recursive CTE evaluated once per row of
journal_entry_lines would make every report unusable at a hundred councils.

So the honest statement of what RLS buys here: it is a backstop against
application bugs -- a query that forgets its WHERE clause returns nothing
instead of everything -- not a defence against a hostile database role with
a psql prompt, which could set the session variables itself. That was
already true of `app.current_organization_id`; adding scope alongside it
does not weaken anything. Defence against a hostile role is the restricted
runtime grants in audit_schema.py, and it is a separate mechanism.
"""
from sqlalchemy import text

from models import db

_SCOPE_SQL = text("""
    WITH RECURSIVE branch AS (
        SELECT id FROM organizations WHERE id = :root
        UNION
        SELECT o.id FROM organizations o JOIN branch b ON o.parent_id = b.id
    )
    SELECT id FROM branch
""")


def descendant_ids(organization_id):
    """Every organization at or below `organization_id`, including itself.

    Cycle-safe by construction: UNION (not UNION ALL) drops an id already in
    the working set, so a parent_id loop entered by hand in the database
    terminates instead of recursing forever.
    """
    if organization_id is None:
        return []
    rows = db.session.execute(_SCOPE_SQL, {'root': organization_id}).fetchall()
    return [r[0] for r in rows]


def ancestor_ids(organization_id):
    """Every organization above this one, nearest parent first.

    Used for "who do we report up to" -- assessments and per-capita billing
    flow the other direction from roll-up reporting.
    """
    if organization_id is None:
        return []
    rows = db.session.execute(text("""
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 0 AS depth
              FROM organizations WHERE id = :start
            UNION
            SELECT o.id, o.parent_id, c.depth + 1
              FROM organizations o JOIN chain c ON o.id = c.parent_id
             WHERE c.depth < 20
        )
        SELECT id FROM chain WHERE id <> :start ORDER BY depth
    """), {'start': organization_id}).fetchall()
    return [r[0] for r in rows]


def is_leaf(organization_id):
    """True when nothing reports to this organization.

    Only leaves keep books in this design. A state body's "totals" are the
    sum of its councils' ledgers, not a ledger of its own -- which is why
    roll-up reporting reads descendants rather than posting consolidating
    entries that would have to be eliminated later.
    """
    return db.session.execute(
        text("SELECT NOT EXISTS (SELECT 1 FROM organizations WHERE parent_id = :id)"),
        {'id': organization_id},
    ).scalar()
'''

with io.open('services/hierarchy.py', 'w', encoding='utf-8', newline='\r\n') as fh:
    fh.write(HIERARCHY)
print('created services/hierarchy.py')


# =========================================================== tenancy: add scope
p = 'services/tenancy.py'
s = load(p)

assert '_current_org_id = contextvars.ContextVar' in s
s = s.replace(
    fit("""
_current_org_id = contextvars.ContextVar('cares_current_organization_id', default=None)
""", p),
    fit("""
_current_org_id = contextvars.ContextVar('cares_current_organization_id', default=None)

# The organizations this request may READ -- its own plus everything below it
# in the hierarchy. Separate from _current_org_id, which stays the single
# organization this request may WRITE. See services/hierarchy.py.
_current_org_scope = contextvars.ContextVar('cares_current_organization_scope', default=None)
"""), 1)

anchor = fit("""
def clear_current_organization():
""", p)
assert anchor in s
s = s.replace(anchor, fit("""
def set_current_organization_scope(organization_ids):
    \"\"\"Declare which organizations this unit of work may read.

    Passing None (or never calling this) falls back to the acting
    organization alone, so forgetting to set scope narrows visibility rather
    than widening it. Every default in this module errs the same direction.
    \"\"\"
    _current_org_scope.set(list(organization_ids) if organization_ids else None)


def clear_current_organization():
"""), 1)

anchor = fit("""
    _current_org_id.set(None)
""", p)
assert anchor in s
s = s.replace(anchor, fit("""
    _current_org_id.set(None)
    _current_org_scope.set(None)
"""), 1)

old_set = fit("""
    org_id = _current_org_id.get()
    connection.execute(
        text("SET LOCAL app.current_organization_id = :org_id"),
        {'org_id': str(org_id) if org_id is not None else ''},
    )
""", p)
assert old_set in s, 'after_begin body not found'
s = s.replace(old_set, fit("""
    org_id = _current_org_id.get()
    connection.execute(
        text("SET LOCAL app.current_organization_id = :org_id"),
        {'org_id': str(org_id) if org_id is not None else ''},
    )

    # Postgres session settings are text, so the readable scope travels as a
    # comma-separated list that rls_schema.current_org_scope() parses back
    # into INTEGER[]. Empty means "no scope declared", which the policies
    # treat as the acting organization alone -- never as "everything".
    scope = _current_org_scope.get()
    if not scope and org_id is not None:
        scope = [org_id]
    connection.execute(
        text("SET LOCAL app.current_organization_scope = :scope"),
        {'scope': ','.join(str(i) for i in scope) if scope else ''},
    )
"""), 1)
save(p, s)


# =========================================================== rls: scope function
p = 'rls_schema.py'
s = load(p)

anchor = fit("""
def _derive_function_sql(table, parent_table, foreign_key):
""", p)
assert anchor in s
s = s.replace(anchor, fit('''
_CURRENT_ORG_SCOPE_FUNCTION = """
CREATE OR REPLACE FUNCTION current_org_scope() RETURNS INTEGER[] AS $$
DECLARE
    v_raw TEXT;
BEGIN
    v_raw := NULLIF(current_setting('app.current_organization_scope', true), '');
    IF v_raw IS NULL THEN
        -- No scope declared. Fall back to the single acting organization
        -- rather than to everything: a caller that forgets to set scope
        -- must lose reach, never gain it.
        IF current_org() IS NULL THEN
            RETURN ARRAY[]::INTEGER[];
        END IF;
        RETURN ARRAY[current_org()];
    END IF;
    RETURN string_to_array(v_raw, ',')::INTEGER[];
EXCEPTION WHEN others THEN
    RETURN ARRAY[]::INTEGER[];
END;
$$ LANGUAGE plpgsql STABLE;
"""


def _derive_function_sql(table, parent_table, foreign_key):
'''), 1)

anchor = fit("""
    connection.execute(text(_CURRENT_ORG_FUNCTION))
    say("  current_org() installed")
""", p)
assert anchor in s, 'current_org install anchor not found'
s = s.replace(anchor, fit("""
    connection.execute(text(_CURRENT_ORG_FUNCTION))
    connection.execute(text(_CURRENT_ORG_SCOPE_FUNCTION))
    say("  current_org() / current_org_scope() installed")
"""), 1)

old_policy = fit("""
        connection.execute(text(
            f"CREATE POLICY {_POLICY_NAME} ON {table} "
            f"USING (organization_id = current_org()) "
            f"WITH CHECK (organization_id = current_org())"
        ))
""", p)
assert old_policy in s, 'policy creation anchor not found'
s = s.replace(old_policy, fit("""
        # READ down the hierarchy, WRITE only your own organization.
        #
        # A state deputy rolling up a hundred councils' Form 1295 figures
        # needs to read all of them. That same deputy must not be able to
        # post into a council's ledger: the council's trustees sign those
        # books under Section 145, and the audit trail has to name someone
        # inside that council. USING and WITH CHECK are what make those two
        # sentences true at the database rather than in a route decorator
        # somebody will forget to apply.
        connection.execute(text(
            f"CREATE POLICY {_POLICY_NAME} ON {table} "
            f"USING (organization_id = ANY(current_org_scope())) "
            f"WITH CHECK (organization_id = current_org())"
        ))
"""), 1)
save(p, s)


# =========================================================== models: audit org
p = 'models.py'
s = load(p)
anchor = fit("""
    changed_by_user_id = db.Column(db.Integer, nullable=True)
    db_role = db.Column(db.String(64), nullable=False)
""", p)
assert anchor in s, 'AuditLog column anchor not found'
s = s.replace(anchor, fit("""
    changed_by_user_id = db.Column(db.Integer, nullable=True)
    # Which organization's hash chain this row belongs to. Written by
    # audit_trigger_fn() from the audited row's OWN organization_id -- never
    # from session state, because a row's owner is a property of the data.
    # Deliberately no ForeignKey, for the same reason changed_by_user_id has
    # none: the audit trail must survive the deletion of anything it
    # references. NULL means the audited table has no organization of its
    # own (organizations itself), which shares a single chain.
    organization_id = db.Column(db.Integer, nullable=True, index=True)
    db_role = db.Column(db.String(64), nullable=False)
"""), 1)
save(p, s)


# =========================================================== app.py wiring
p = 'app.py'
s = load(p)

anchor = fit("from services.audit_context import set_current_actor, clear_current_actor", p)
assert anchor in s
s = s.replace(anchor, fit("""
from services.audit_context import set_current_actor, clear_current_actor
from services.tenancy import (
    set_current_organization, set_current_organization_scope,
    clear_current_organization,
)
from services.hierarchy import descendant_ids
"""), 1)

anchor = fit("""
@app.teardown_request
def clear_audit_actor(exc=None):
""", p)
assert anchor in s, 'teardown anchor not found'
s = s.replace(anchor, fit('''
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
    try:
        set_current_organization_scope(descendant_ids(org_id))
    except Exception:
        # A hierarchy lookup that fails must not widen visibility. Falling
        # back to None means "this organization only" (see tenancy.py).
        set_current_organization_scope(None)
    return None


@app.teardown_request
def clear_tenant_context(exc=None):
    """Same reason as clear_audit_actor: worker threads outlive requests."""
    clear_current_organization()


@app.teardown_request
def clear_audit_actor(exc=None):
'''), 1)
save(p, s)


# =========================================================== migration wiring
p = 'migrate_production.py'
s = load(p)

anchor = fit("def verify_database_integrity():", p)
assert anchor in s
s = s.replace(anchor, fit('''
def install_row_level_security():
    """Install organization isolation at the database layer.

    Runs AFTER ensure_default_organization() because the backfill needs an
    organization to attribute pre-multi-tenancy rows to, and after every
    column migration because the policies reference columns those add.

    Idempotent by construction (see rls_schema.install_rls), so this runs on
    every startup like the rest of this file. Failure is reported but not
    fatal: a deployment that cannot install policies is a deployment that
    behaves exactly as it did before multi-tenancy, and refusing to boot a
    council's books over it would be the wrong trade.
    """
    print("\\nStep 7: Installing row-level security...")
    try:
        from rls_schema import install_rls, backfill_organization_ids, verify_isolation
    except ImportError as e:
        print(f"  ! rls_schema unavailable: {e}")
        return
    default_org = Organization.query.order_by(Organization.id).first()
    if default_org is None:
        print("  ! No organization exists yet; skipping")
        return
    try:
        with db.engine.begin() as connection:
            install_rls(connection)
            backfill_organization_ids(connection, default_org.id)
        with db.engine.connect() as connection:
            report = verify_isolation(connection)
        unprotected = report.get('unprotected_tables') or []
        if unprotected:
            print(f"  ! Tables without an active policy: {', '.join(unprotected)}")
        else:
            print(f"OK Policies active on {len(report['tables'])} table(s)")
        if report.get('connected_as_owner'):
            # Not a warning to fix here -- migrations MUST run as the owner.
            # It is a warning about how the app itself connects: an app
            # running as the owner bypasses every policy above, which makes
            # this whole mechanism decorative. See grant_restricted_runtime_role.
            print("  ! App connects as the table owner; policies are bypassed "
                  "at runtime until a restricted role is used")
    except Exception as e:
        db.session.rollback()
        print(f"  ! Could not install row-level security: {e}")


def verify_database_integrity():
'''), 1)

anchor = fit("""
            # Verify and summarise
            verify_database_integrity()
""", p)
assert anchor in s, 'migration call-site anchor not found'
s = s.replace(anchor, fit("""
            # Multi-tenancy
            install_row_level_security()

            # Verify and summarise
            verify_database_integrity()
"""), 1)

imp = fit("from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project, ProjectAssignment, Member, MembershipEvent", p)
assert imp in s
if 'Organization' not in imp.split('import')[1]:
    s = s.replace(imp, imp + ', Organization', 1)
save(p, s)


# =========================================================== audit report scope
p = 'blueprints/audit_routes.py'
s = load(p)

old_doc = fit("""
Deliberately NOT organization-scoped: V1 is single-chapter scope (see
kofc-v2-backlog.md), so there is only ever one real chapter's data in a
given deployment's database. Per-organization filtering of audit_log
belongs with the rest of the multi-tenancy work in V2, once a second real
organization actually needs to share a deployment.
""", p)
assert old_doc in s, 'audit docstring anchor not found'
s = s.replace(old_doc, fit("""
Organization-scoped as of V2. audit_log carries an organization_id written
by the trigger from each audited row's own data, and every row on this
report is filtered to the branch of the hierarchy the viewer sits in. The
hash chain is partitioned the same way, so a council can verify its own
history without reading -- or depending on -- any other council's rows.

audit_log deliberately carries no RLS policy of its own (see rls_schema.py):
an auditor investigating a cross-tenant incident must not be blocked by the
mechanism they are investigating. That makes the filtering below the actual
control, which is why it lives in collect_log_rows() -- the single function
both the screen and the signed PDF read from -- rather than in either
caller.
"""), 1)

old_collect = fit("""
def collect_log_rows(start_date, end_date, table_filter, limit):
""", p)
assert old_collect in s
s = s.replace(old_collect, fit("""
def collect_log_rows(start_date, end_date, table_filter, limit, organization_ids=None):
"""), 1)

old_query = fit("""
    query = AuditLog.query.filter(
        AuditLog.changed_at >= start_date,
        # Inclusive of the whole end day, not just midnight.
        AuditLog.changed_at < end_date + timedelta(days=1),
    )
""", p)
assert old_query in s, 'collect_log_rows query anchor not found'
s = s.replace(old_query, fit("""
    query = AuditLog.query.filter(
        AuditLog.changed_at >= start_date,
        # Inclusive of the whole end day, not just midnight.
        AuditLog.changed_at < end_date + timedelta(days=1),
    )
    if organization_ids:
        # Rows on the `organizations` table itself have no organization_id
        # (they ARE the organization), so match those by row_id or a council
        # would never see changes to its own registration details.
        query = query.filter(or_(
            AuditLog.organization_id.in_(organization_ids),
            and_(AuditLog.table_name == 'organizations',
                 AuditLog.row_id.in_(organization_ids)),
        ))
"""), 1)

old_verify_def = fit("""
def verify_chain():
""", p)
assert old_verify_def in s
s = s.replace(old_verify_def, fit("""
def verify_chain(organization_ids=None):
"""), 1)

old_self = fit("""
    self_consistency_failures = db.session.execute(text(\"\"\"
        SELECT id, table_name, operation, changed_at
        FROM audit_log
        WHERE row_hash <> encode(digest(
""", p)
assert old_self in s, 'verify self-consistency anchor not found'
s = s.replace(old_self, fit("""
    # Scope every check to the caller's branch of the hierarchy. Restricting
    # the ROWS is safe for the chain check below because the window function
    # partitions by organization_id: filtering out other organizations
    # removes whole partitions, never a link from the middle of this one.
    scope_clause = ''
    params = {}
    if organization_ids:
        scope_clause = 'AND organization_id = ANY(:org_ids)'
        params['org_ids'] = list(organization_ids)

    self_consistency_failures = db.session.execute(text(f\"\"\"
        SELECT id, table_name, operation, changed_at
        FROM audit_log
        WHERE row_hash <> encode(digest(
"""), 1)

old_tail = fit("""
            'sha256'), 'hex')
        ORDER BY id
    \"\"\")).fetchall()
""", p)
assert old_tail in s, 'verify self-consistency tail anchor not found'
s = s.replace(old_tail, fit("""
            'sha256'), 'hex')
        {scope_clause}
        ORDER BY id
    \"\"\"), params).fetchall()
"""), 1)

old_chain = fit("""
    chain_breaks = db.session.execute(text(\"\"\"
        WITH ordered AS (
            SELECT id, table_name, operation, changed_at, prev_hash,
                   lag(row_hash) OVER (PARTITION BY organization_id ORDER BY id)
                       AS expected_prev_hash
            FROM audit_log
        )
        SELECT id, table_name, operation, changed_at
        FROM ordered
        WHERE prev_hash IS DISTINCT FROM expected_prev_hash
        ORDER BY id
    \"\"\")).fetchall()

    total_rows = db.session.execute(text("SELECT count(*) FROM audit_log")).scalar() or 0
""", p)
assert old_chain in s, 'chain-break query anchor not found'
s = s.replace(old_chain, fit("""
    chain_breaks = db.session.execute(text(f\"\"\"
        WITH ordered AS (
            SELECT id, table_name, operation, changed_at, prev_hash,
                   lag(row_hash) OVER (PARTITION BY organization_id ORDER BY id)
                       AS expected_prev_hash
            FROM audit_log
            WHERE TRUE {scope_clause}
        )
        SELECT id, table_name, operation, changed_at
        FROM ordered
        WHERE prev_hash IS DISTINCT FROM expected_prev_hash
        ORDER BY id
    \"\"\"), params).fetchall()

    total_rows = db.session.execute(
        text(f"SELECT count(*) FROM audit_log WHERE TRUE {scope_clause}"), params
    ).scalar() or 0
"""), 1)

old_imports = fit("from sqlalchemy import text", p)
assert old_imports in s
s = s.replace(old_imports, fit("from sqlalchemy import and_, or_, text"), 1)

# ---- call sites: three of them, all must pass the same scope -------------
old_call = fit("    rows = collect_log_rows(start_date, end_date, table_filter, _ROW_LIMIT)", p)
assert s.count(old_call) == 2, f'expected 2 collect_log_rows call sites, found {s.count(old_call)}'
s = s.replace(old_call, fit("""
    org_scope = _visible_organization_ids()
    rows = collect_log_rows(start_date, end_date, table_filter, _ROW_LIMIT,
                            organization_ids=org_scope)
"""))

old_call = fit("    result = verify_chain()", p)
assert old_call in s
s = s.replace(old_call, fit("    result = verify_chain(_visible_organization_ids())"), 1)

old_call = fit("        verification=verify_chain(),", p)
assert old_call in s
s = s.replace(old_call, fit("        verification=verify_chain(org_scope),"), 1)

anchor = fit("""
def _require_admin():
""", p)
assert anchor in s
s = s.replace(anchor, fit('''
def _visible_organization_ids():
    """The branch of the hierarchy this viewer's audit report covers.

    Returns the acting organization plus everything below it, so a state
    body reviewing its councils sees them and a council sees only itself.
    Never returns an empty list for an authenticated user -- an empty scope
    would read as "no filter" at the call sites and show everything.
    """
    org_id = getattr(current_user, 'organization_id', None)
    if org_id is None:
        return []
    try:
        ids = descendant_ids(org_id)
    except Exception:
        ids = []
    return ids or [org_id]


def _require_admin():
'''), 1)

anchor = fit("from models import db, AuditLog, User", p)
assert anchor in s
s = s.replace(anchor, fit("""
from models import db, AuditLog, User
from services.hierarchy import descendant_ids
"""), 1)

save(p, s)

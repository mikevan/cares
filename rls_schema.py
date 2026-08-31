"""
Row-Level Security: organization isolation enforced by PostgreSQL
=================================================================

`services/journal_service.py` has listed "RLS context verification" as a
future hook point since it was written. This is that hook, built.

WHY THIS EXISTS RATHER THAN MORE .filter_by(organization_id=...)
---------------------------------------------------------------
The application had 163 references to ChartOfAccounts across 29 files and a
scoping rule that every developer had to remember at every query. §1 of the
code review is what that produces: `project_routes.edit` and
`journal_service.void_entry` reachable across organizations because someone
forgot, on a write path, in code that looked fine. Scaling that approach to
ten councils and fifty thousand users scales the number of chances to forget.

The failure modes are opposite, and that is the whole argument:

    filter-everywhere    a forgotten filter returns EVERY organization's rows
    row-level security   a forgotten filter returns NO rows

One is a silent data breach. The other is an obvious bug that shows up the
first time anyone runs the query.

Application-level filters stay where they are. They are now defence in depth
rather than the only defence, and they keep queries efficient by not making
the database discard rows it was going to reject anyway.

WHO IS SUBJECT TO THESE POLICIES
--------------------------------
`ENABLE ROW LEVEL SECURITY` without `FORCE`, deliberately. A table's owner
bypasses its policies; everyone else is subject. That draws the line exactly
where the existing design already draws it:

    the app's runtime role   non-owner, restricted to INSERT/SELECT on
                             audit_log (see audit_schema.py) -- SUBJECT to
                             these policies. This is the role that must never
                             read another council's books.

    the owner/migration role migrations, init_db.py, the demo loaders and the
                             test harness -- NOT subject, so they keep working
                             unchanged and can backfill across organizations.

Adding FORCE would mean the owner is subject too, which sounds stricter and
is mostly self-harm: a role that can DROP the table is not meaningfully
constrained by being unable to SELECT from it, and every maintenance path
would need a bypass that becomes the new hole.

The consequence worth stating plainly: **these policies only protect a
deployment that actually runs `grant_restricted_runtime_role`.** An
installation still connecting as the owner is unprotected. That is the same
manual step the audit trail's tamper-resistance already depends on, and the
same reason a startup check for it is on the backlog.

DENORMALIZED organization_id, AND WHY IT CANNOT DRIFT
-----------------------------------------------------
A policy that has to join through `projects` to discover a journal entry's
organization is slow and awkward, so the tables below carry `organization_id`
directly even where it is derivable. A denormalized column that drifts from
its parent is a silent cross-tenant leak, so it is not maintained by
application code: a BEFORE INSERT OR UPDATE trigger derives it from the
parent row on every write. The application cannot set it wrong because the
application does not set it at all.
"""
from sqlalchemy import text

# Tables that already carry organization_id as real, first-class data.
DIRECT_ORG_TABLES = [
    'members',
    'member_dues_payments',
    'projects',
    'vendors',
    'invoices',
    'receivables',
    'payers',
    'membership_events',
    'form_1295_submissions',
    'chart_of_accounts',
    'donors',
]

# (table, parent_table, foreign_key) -- organization_id is derived from the
# parent by trigger, never written by the application.
DERIVED_ORG_TABLES = [
    ('journal_entries', 'projects', 'project_id'),
    ('journal_entry_lines', 'journal_entries', 'journal_entry_id'),
    ('donations', 'journal_entries', 'journal_entry_id'),
    ('invoice_payments', 'invoices', 'invoice_id'),
    ('receivable_payments', 'receivables', 'receivable_id'),
    ('pledge_installments', 'receivables', 'receivable_id'),
    ('project_assignments', 'projects', 'project_id'),
]

# Deliberately NOT protected:
#
#   organizations     the tenant list itself. A user must be able to read
#                     their own organization row to know who they are, and a
#                     parent council must see its children exist to roll them
#                     up. Isolation here is a route-level concern.
#   users             authentication happens before any organization context
#                     exists -- a login that cannot find the user by name
#                     cannot log anyone in. Scoped at the route layer.
#   currencies        reference data, identical for everyone.
#   translation_cache keyed by route and content hash, holds no org data.
#   usage_events      vendor telemetry. The V2 design has a SEPARATE,
#                     closed-source application reading this with its own
#                     read-only role, deliberately ACROSS organizations, to
#                     inform pricing. A policy here would blind exactly the
#                     consumer it exists for. It carries organization_id for
#                     grouping, not for isolation.
#   audit_log         append-only and separately protected by grants. It gets
#                     an organization_id column for filtering the Trustee
#                     report, but no policy -- an auditor investigating a
#                     cross-tenant incident must not be blocked by the
#                     mechanism they are investigating.
UNPROTECTED_TABLES = ['organizations', 'users', 'currencies', 'translation_cache',
                      'audit_log', 'usage_events']

ALL_PROTECTED_TABLES = DIRECT_ORG_TABLES + [t[0] for t in DERIVED_ORG_TABLES]

_POLICY_NAME = 'cares_org_isolation'


_CURRENT_ORG_FUNCTION = """
CREATE OR REPLACE FUNCTION current_org() RETURNS INTEGER AS $$
BEGIN
    -- The 'true' makes a missing setting return NULL instead of raising.
    -- Every policy below compares organization_id against this, so a NULL
    -- here yields NULL, which is not true, which returns no rows. Failing
    -- closed is intentional: the design this replaces failed open.
    RETURN NULLIF(current_setting('app.current_organization_id', true), '')::INTEGER;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;
"""


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
    return f"""
CREATE OR REPLACE FUNCTION derive_org_{table}() RETURNS TRIGGER AS $$
BEGIN
    SELECT p.organization_id INTO NEW.organization_id
      FROM {parent_table} p
     WHERE p.id = NEW.{foreign_key};
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def install_rls(connection, verbose=True):
    """Create the organization columns, derivation triggers and policies.

    Idempotent: safe to run on every migration. Adds columns only when
    missing, replaces functions in place, and drops each policy before
    recreating it so a changed definition actually takes effect.

    `connection` must be bound to the table owner.
    """
    def say(msg):
        if verbose:
            print(msg)

    connection.execute(text(_CURRENT_ORG_FUNCTION))
    connection.execute(text(_CURRENT_ORG_SCOPE_FUNCTION))
    say("  current_org() / current_org_scope() installed")

    # ---- columns ---------------------------------------------------------
    for table, _, _ in DERIVED_ORG_TABLES:
        connection.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS organization_id INTEGER"
        ))
    for table in ('chart_of_accounts', 'donors'):
        connection.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS organization_id INTEGER"
        ))
    connection.execute(text(
        "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS organization_id INTEGER"
    ))
    say(f"  organization_id present on {len(ALL_PROTECTED_TABLES)} protected table(s)")

    # ---- derivation triggers --------------------------------------------
    for table, parent_table, foreign_key in DERIVED_ORG_TABLES:
        connection.execute(text(_derive_function_sql(table, parent_table, foreign_key)))
        connection.execute(text(f"DROP TRIGGER IF EXISTS trg_derive_org_{table} ON {table}"))
        connection.execute(text(
            f"CREATE TRIGGER trg_derive_org_{table} "
            f"BEFORE INSERT OR UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION derive_org_{table}()"
        ))
    say(f"  {len(DERIVED_ORG_TABLES)} derivation trigger(s) attached")

    # ---- policies --------------------------------------------------------
    for table in ALL_PROTECTED_TABLES:
        connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"DROP POLICY IF EXISTS {_POLICY_NAME} ON {table}"))
        # USING governs what can be read/updated/deleted; WITH CHECK governs
        # what may be written. Both are needed: without WITH CHECK, a role
        # could insert rows belonging to an organization it cannot read.
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
    say(f"  isolation policy applied to {len(ALL_PROTECTED_TABLES)} table(s)")


def backfill_organization_ids(connection, default_organization_id, verbose=True):
    """Populate organization_id on rows that predate these columns.

    Run once, as the owner, before the policies can do anything useful --
    a NULL organization_id matches no policy, so unbackfilled rows become
    invisible to the application.

    Derived tables take their value from their parent. `chart_of_accounts`
    and `donors` have no parent to derive from and are assigned to
    `default_organization_id`, which is correct precisely because this only
    runs while the deployment holds one council. Doing this later, with two
    councils' rows intermingled and no way to tell them apart, is the
    migration this is meant to avoid.
    """
    def say(msg):
        if verbose:
            print(msg)

    statements = [
        ("journal_entries", """
            UPDATE journal_entries je SET organization_id = p.organization_id
              FROM projects p WHERE p.id = je.project_id AND je.organization_id IS NULL"""),
        ("journal_entry_lines", """
            UPDATE journal_entry_lines jel SET organization_id = je.organization_id
              FROM journal_entries je
             WHERE je.id = jel.journal_entry_id AND jel.organization_id IS NULL"""),
        ("donations", """
            UPDATE donations d SET organization_id = je.organization_id
              FROM journal_entries je
             WHERE je.id = d.journal_entry_id AND d.organization_id IS NULL"""),
        ("invoice_payments", """
            UPDATE invoice_payments ip SET organization_id = i.organization_id
              FROM invoices i WHERE i.id = ip.invoice_id AND ip.organization_id IS NULL"""),
        ("receivable_payments", """
            UPDATE receivable_payments rp SET organization_id = r.organization_id
              FROM receivables r WHERE r.id = rp.receivable_id AND rp.organization_id IS NULL"""),
        ("pledge_installments", """
            UPDATE pledge_installments pi SET organization_id = r.organization_id
              FROM receivables r WHERE r.id = pi.receivable_id AND pi.organization_id IS NULL"""),
        ("project_assignments", """
            UPDATE project_assignments pa SET organization_id = p.organization_id
              FROM projects p WHERE p.id = pa.project_id AND pa.organization_id IS NULL"""),
        # Donors reach an organization only through their donations; any donor
        # with no donation yet falls back to the default below.
        ("donors (via donations)", """
            UPDATE donors dn SET organization_id = sub.organization_id
              FROM (SELECT DISTINCT ON (donor_id) donor_id, organization_id
                      FROM donations WHERE organization_id IS NOT NULL) sub
             WHERE sub.donor_id = dn.id AND dn.organization_id IS NULL"""),
    ]
    for label, sql in statements:
        result = connection.execute(text(sql))
        say(f"    {label}: {result.rowcount if result.rowcount is not None else '?'} row(s)")

    for table in ('chart_of_accounts', 'donors'):
        result = connection.execute(text(
            f"UPDATE {table} SET organization_id = :org WHERE organization_id IS NULL"
        ), {'org': default_organization_id})
        say(f"    {table} -> organization {default_organization_id}: "
            f"{result.rowcount if result.rowcount is not None else '?'} row(s)")

    # audit_log is filtered, not policed -- see UNPROTECTED_TABLES.
    connection.execute(text("""
        UPDATE audit_log a SET organization_id = (new_data->>'organization_id')::INTEGER
         WHERE a.organization_id IS NULL
           AND a.new_data ? 'organization_id'
           AND (a.new_data->>'organization_id') ~ '^[0-9]+$'"""))
    connection.execute(text("""
        UPDATE audit_log a SET organization_id = (old_data->>'organization_id')::INTEGER
         WHERE a.organization_id IS NULL
           AND a.old_data ? 'organization_id'
           AND (a.old_data->>'organization_id') ~ '^[0-9]+$'"""))
    say("    audit_log: organization derived from captured row data where present")


def verify_isolation(connection):
    """Report whether the policies are actually in force.

    Returns a dict rather than printing, so a startup check or a test can
    assert on it. `enforced` being False means every table is readable across
    organizations -- which is exactly the state a deployment is in if it never
    ran grant_restricted_runtime_role, since the owner bypasses these policies.
    """
    rows = connection.execute(text("""
        SELECT c.relname, c.relrowsecurity,
               (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind = 'r'
           AND c.relname = ANY(:tables)
    """), {'tables': ALL_PROTECTED_TABLES}).fetchall()

    by_table = {r[0]: {'rls_enabled': r[1], 'policies': r[2]} for r in rows}
    missing = [t for t in ALL_PROTECTED_TABLES
               if not by_table.get(t, {}).get('rls_enabled')
               or not by_table.get(t, {}).get('policies')]
    current_role = connection.execute(text("SELECT current_user")).scalar()
    is_owner = connection.execute(text("""
        SELECT bool_or(pg_catalog.pg_get_userbyid(c.relowner) = current_user)
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
    """), {'tables': ALL_PROTECTED_TABLES}).scalar()

    return {
        'tables': by_table,
        'unprotected_tables': missing,
        'current_role': current_role,
        'connected_as_owner': bool(is_owner),
        # Policies exist AND this connection is actually subject to them.
        'enforced': not missing and not is_owner,
    }

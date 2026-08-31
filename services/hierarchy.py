"""
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

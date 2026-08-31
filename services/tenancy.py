"""
Tenant context for row-level security.

Postgres enforces organization isolation directly (see rls_schema.py), but a
policy can only compare a row against something the database knows. This
module is what tells it: once per transaction, the acting user's organization
is pushed into a session setting that every RLS policy reads back.

    app.current_organization_id   ->  rls_schema.current_org()  ->  every policy

Deliberately built the same way as services/audit_context.py, which does the
same job for the audit trail's actor. That is not laziness -- that mechanism
has been exercised hard (it survived a full test-suite run, a nested-app-context
demo loader, and the test harness's independently constructed sessionmaker),
and a second, different way of doing the same thing would be a second thing to
get wrong.

WHAT HAPPENS WHEN NOTHING IS SET
--------------------------------
Nothing is the safe answer. `current_setting('app.current_organization_id',
true)` returns NULL when unset, every policy's comparison evaluates to NULL
rather than true, and the query returns zero rows. A background script that
forgets to establish context sees an empty database, not another council's
books. Failing closed is the entire point: the previous design failed OPEN,
because a query that forgot its filter returned everything.

That does mean maintenance paths must be deliberate about context. See
rls_schema.py on why the table owner is not subject to these policies, which
is how migrations, loaders and the test harness continue to work.
"""
import contextvars

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_current_org_id = contextvars.ContextVar('cares_current_organization_id', default=None)

# The organizations this request may READ -- its own plus everything below it
# in the hierarchy. Separate from _current_org_id, which stays the single
# organization this request may WRITE. See services/hierarchy.py.
_current_org_scope = contextvars.ContextVar('cares_current_organization_scope', default=None)


def set_current_organization(organization_id):
    """Declare which organization the current unit of work belongs to.

    Called from app.py's before_request with current_user.organization_id.
    Anything outside a request (a loader, a migration, a shell) simply never
    calls it and runs without tenant context.
    """
    _current_org_id.set(organization_id)


def set_current_organization_scope(organization_ids):
    """Declare which organizations this unit of work may read.

    Passing None (or never calling this) falls back to the acting
    organization alone, so forgetting to set scope narrows visibility rather
    than widening it. Every default in this module errs the same direction.
    """
    _current_org_scope.set(list(organization_ids) if organization_ids else None)


def clear_current_organization():
    """Drop the organization at the end of a request, so a worker thread
    reused for the next one cannot inherit this one's tenant."""
    _current_org_id.set(None)
    _current_org_scope.set(None)


def get_current_organization():
    return _current_org_id.get()


def _settings_for_current_context():
    """The two session-setting values for whatever context is set right now.

    Postgres session settings are text, so the readable scope travels as a
    comma-separated list that rls_schema.current_org_scope() parses back into
    INTEGER[]. Empty means "no scope declared", which the policies treat as
    the acting organization alone -- never as "everything".
    """
    org_id = _current_org_id.get()
    scope = _current_org_scope.get()
    if not scope and org_id is not None:
        scope = [org_id]
    return (
        str(org_id) if org_id is not None else '',
        ','.join(str(i) for i in scope) if scope else '',
    )


def _push(executor):
    org_value, scope_value = _settings_for_current_context()
    executor.execute(
        text("SET LOCAL app.current_organization_id = :org_id"),
        {'org_id': org_value},
    )
    executor.execute(
        text("SET LOCAL app.current_organization_scope = :scope"),
        {'scope': scope_value},
    )


def apply_to_open_transaction(session):
    """Push the current context onto a transaction that is ALREADY open.

    after_begin fires once, when a transaction starts, and never again --
    so context established after the first query of a request would arrive
    one transaction late and every RLS policy would compare against NULL.
    That is not hypothetical: it is what made a production deployment
    render as a completely empty application on its first request served
    under the restricted runtime role.

    The obvious repair -- commit, so the settings land on a fresh
    transaction -- works but is a blunt instrument: commit expires every
    object in the session, which breaks callers holding ORM instances
    across the boundary. SET LOCAL on the open transaction achieves the
    same thing with no side effects at all.

    Safe to call repeatedly; SET LOCAL simply overwrites, and the values
    are discarded when the transaction ends.
    """
    _push(session)


@event.listens_for(Session, "after_begin")
def _apply_organization_to_transaction(session, transaction, connection):
    """Push the organization into the session setting each RLS policy reads.

    Registered on the Session CLASS, not an instance, so it covers every
    session in the process -- the Flask-SQLAlchemy one and the test harness's
    own sessionmaker -- without either needing to know this module exists.

    `after_begin` fires when a transaction begins, which is once on first use
    and again after every commit. It does NOT fire retroactively when the
    organization changes mid-transaction, which is the same trap that made
    login's last_login update land with no audit actor: set the organization
    before the first write, or commit first so the write lands in a fresh
    transaction that already carries it.
    """
    _push(connection)

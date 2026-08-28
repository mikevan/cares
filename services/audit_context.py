"""
Actor-context plumbing for the audit trail.

Every INSERT/UPDATE/DELETE on an audited table is captured by a Postgres
trigger (see audit_schema.py), which has no idea which application user
is behind the change -- it only ever sees the single database role the
whole app connects as. To attribute a change to a specific person, the
app tells Postgres who's acting, once per transaction, via a
session-scoped setting (`SET LOCAL app.current_user_id`) that the trigger
function reads back. This module is the one place that plumbing lives.

How it's wired
-----------------
- `_current_actor_id` is a contextvar holding "who is making requests on
  this thread right now". app.py calls set_current_actor(current_user.id)
  in a before_request hook and clear_current_actor() in teardown_request,
  so it never leaks from one request into the next on a reused thread.
- `_apply_actor_to_transaction` is registered on the base SQLAlchemy
  Session CLASS (not any one session instance), so it fires for every
  session in the process -- the real app's Flask-SQLAlchemy session, and
  also the test harness's independently-constructed
  `sessionmaker(bind=connection, ...)` session in tests/conftest.py --
  without either of them needing to import this module or change how
  they're built. It fires every time a session begins a new logical
  transaction, which in practice means: once when a session is first
  used, and again after every subsequent commit (each commit ends one
  transaction and the next statement silently starts a new one). This was
  verified empirically against a real Postgres and a reproduction of the
  test harness's exact session-construction pattern before relying on it
  here -- see the commit history / conversation for that validation.

Nothing here assumes a request is in progress. A script run outside Flask
(init_db.py, load_comprehensive_data.py) simply
never calls set_current_actor(), so the contextvar stays at its default
(None) and its changes show up in the audit trail with a NULL actor --
which is correct: it genuinely wasn't a logged-in user making the change.
"""
import contextvars

from sqlalchemy import event, text
from sqlalchemy.orm import Session

_current_actor_id = contextvars.ContextVar('cares_current_actor_id', default=None)


def set_current_actor(user_id):
    """Call once per request (or per unit of work outside a request) with
    the acting user's id, before any database writes happen."""
    _current_actor_id.set(user_id)


def clear_current_actor():
    """Call at the end of every request (teardown_request), so a thread
    reused for the next request doesn't inherit this one's actor."""
    _current_actor_id.set(None)


@event.listens_for(Session, "after_begin")
def _apply_actor_to_transaction(session, transaction, connection):
    actor_id = _current_actor_id.get()
    connection.execute(
        text("SET LOCAL app.current_user_id = :actor_id"),
        {'actor_id': str(actor_id) if actor_id is not None else ''},
    )

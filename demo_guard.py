"""
Demo-reset guard
================

Two standing policies govern this codebase, and they pull in opposite
directions:

  1. A DEMO database is disposable. Every demo load wipes the backend and
     rebuilds from nothing, so the demo is reproducible from the loader
     rather than from whatever happens to be in someone's database.

  2. A PRODUCTION update never reloads data. Deploying a new version of
     the software must leave a council's books exactly where they were.

Both are correct. The danger is that the same scripts serve both, so the
only thing separating "rebuild the demo" from "delete a real council's
financial records" has been which shell script someone happened to run.
That is not a safety margin. `migrate_and_start.sh` -- the Render deploy
path -- called load_comprehensive_data.py unconditionally on every
startup, and that loader wipes before it seeds.

This module is the single place that decides. Every destructive action --
wiping transactional data, truncating the audit log, resetting the admin
password -- asks here first, so the guard cannot be bypassed by running a
loader directly on a production box. The shell scripts gate on DEMO_MODE
too, but that is the second line, not the only one.

THE SWITCH
----------
    DEMO_MODE=true      This deployment is a demo. Destructive resets are
                        allowed. Set this on a demo instance, never on a
                        council's live deployment.

Outside production (FLASK_ENV is anything other than 'production'),
destructive resets are allowed without the flag, so running a loader by
hand on a development machine keeps working exactly as before -- and so
the test suite, which sets no FLASK_ENV, is unaffected.

The matrix:

    FLASK_ENV      DEMO_MODE     Destructive reset
    -----------    ----------    -----------------
    production     true          allowed  (an intentional demo deployment)
    production     unset/false   REFUSED  (a council's live books)
    development    anything      allowed
    unset (tests)  anything      allowed
"""
import os


def is_production():
    """True when the app is configured as a production deployment.

    FLASK_ENV is the marker the rest of the codebase already uses for
    this -- app.py fails loudly on a missing SECRET_KEY or DATABASE_URL
    under the same condition -- so the guard keys on the same signal
    rather than inventing a second notion of "production" that could
    disagree with the first.
    """
    return os.environ.get('FLASK_ENV', '').strip().lower() == 'production'


def is_demo_mode():
    """True when this deployment has explicitly declared itself a demo."""
    return os.environ.get('DEMO_MODE', '').strip().lower() == 'true'


def demo_reset_allowed():
    """May a destructive demo reset run right now?"""
    return is_demo_mode() or not is_production()


def demo_reset_refusal_message(action='reload demo data'):
    """Explain a refusal in terms of what was skipped and how to override.

    Deliberately not an exception. A refusal here is the system working
    correctly during a routine production deploy, not an error -- raising
    would fail the deploy and make the safe path the painful one, which is
    how guards end up disabled.
    """
    return (
        f"\n  SKIPPED: refusing to {action}.\n"
        f"  FLASK_ENV=production and DEMO_MODE is not 'true', so this is treated\n"
        f"  as a live deployment. Production policy: an update never reloads data.\n"
        f"  If this really is a demo instance, set DEMO_MODE=true in its environment.\n"
    )

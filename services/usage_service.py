"""
CARES Usage / Billing Telemetry
=================================

Records a small number of usage events -- login, journal entry posted,
invoice created, report generated -- so a vendor operating this app for
multiple chapters has real usage data to inform how to bill for it: how
many organizations are active, how active each one is, which features
actually get used. See UsageEvent in models.py for the schema and the
reasoning behind it.

log_event() is deliberately best-effort. Telemetry going down must never
mean a treasurer can't post a journal entry, so any failure here is caught,
rolled back, and logged -- never raised to the caller. Call it AFTER the
action it's recording has already committed successfully, so a telemetry
failure can only ever roll back its own pending insert, never the real
business data that was already saved.
"""

import logging

from models import db, UsageEvent

logger = logging.getLogger(__name__)


def log_event(event_type, organization_id=None, user_id=None, meta=None):
    """
    Record one usage event. Swallows all exceptions -- see module docstring.

    event_type: short, namespaced string, e.g. \'auth.login\',
                \'journal_entry.posted\', \'ap.invoice_created\',
                \'report.generated\'.
    organization_id / user_id: who did it. Either may be None (e.g. a
                failed login before we know who the user is).
    meta: optional small dict of extra context (a resource id, an amount,
          which report) -- keep it small, it\'s stored as JSON.
    """
    try:
        event = UsageEvent(
            event_type=event_type,
            organization_id=organization_id,
            user_id=user_id,
            event_meta=meta,
        )
        db.session.add(event)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to record usage event %r", event_type)

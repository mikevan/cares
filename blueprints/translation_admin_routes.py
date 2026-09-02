"""
Translation Cache Administration Blueprint
==========================================

Admin-only screen for translating the application's pages ahead of time.

The problem it solves: translating a page happens inside the response cycle
and costs two Groq calls, so the first person to open a page in a given
language waits tens of seconds for it. In a demo that person is the client.
This screen makes an administrator the first reader, in advance, for whichever
languages the demo will use.

Two design decisions worth knowing before changing anything here:

**The browser drives the loop, one page per request.** A full warm run can take
ten minutes, and Gunicorn kills a worker at 120 seconds, so the run cannot be a
request. Nor can it be a background thread with in-memory progress: the
deployment runs multiple workers, so roughly half of the progress polls would
land on a worker that has never heard of the job. Instead the page asks for the
list of targets, then posts them back one at a time. No single request runs
long, progress is exact because it is measured in completed requests, and
nothing needs to be shared between workers.

**The warm endpoint renders only from its own allowlist.** It takes a route
string from the browser, which would otherwise be a fine way to ask the server
to render arbitrary internal URLs on the caller's behalf. Every request is
checked against warmable_routes() before anything is fetched.
"""

import time
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, current_app
from flask_login import login_required, current_user

from models import db, TranslationCache
from services.translation_service import SUPPORTED_LANGUAGES
from services.translation_warmer import warmable_routes, warm_page

translation_admin_bp = Blueprint(
    'translation_admin', __name__, url_prefix='/admin/translation'
)


def admin_required(f):
    """Matches the gating on every other administration screen in this app."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'Admin':
            return jsonify({'error': 'Administrator access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


def _cached_counts():
    """How many distinct routes are already cached, per language."""
    try:
        rows = (
            db.session.query(
                TranslationCache.language_code,
                db.func.count(db.func.distinct(TranslationCache.route)),
            )
            .group_by(TranslationCache.language_code)
            .all()
        )
        return {code: count for code, count in rows}
    except Exception as exc:
        current_app.logger.warning(f'Translation cache count failed: {exc}')
        return {}


@translation_admin_bp.route('/')
@login_required
@admin_required
def index():
    """The translation screen."""
    routes = warmable_routes(current_app)
    return render_template(
        'translation_admin.html',
        languages=sorted(SUPPORTED_LANGUAGES.items(), key=lambda kv: kv[1]),
        routes=routes,
        route_count=len(routes),
        cached_counts=_cached_counts(),
    )


@translation_admin_bp.route('/targets')
@login_required
@admin_required
def targets():
    """The work list: every warmable route, plus what is already cached."""
    routes = warmable_routes(current_app)
    return jsonify({
        'routes': routes,
        'languages': SUPPORTED_LANGUAGES,
        'cached': _cached_counts(),
    })


@translation_admin_bp.route('/warm', methods=['POST'])
@login_required
@admin_required
def warm():
    """Translate exactly one page into exactly one language.

    Deliberately does one unit of work per request: it keeps every request well
    inside the worker timeout, and it makes the progress bar a count of things
    that actually finished rather than an estimate.
    """
    payload = request.get_json(silent=True) or {}
    route = (payload.get('route') or '').strip()
    language = (payload.get('language') or '').strip()

    if language not in SUPPORTED_LANGUAGES:
        return jsonify({'status': 'skipped', 'route': route, 'language': language,
                        'detail': 'unsupported language'}), 400

    # The allowlist check. Without it this endpoint would render any internal
    # URL the caller names, with the caller's own session.
    if route not in warmable_routes(current_app):
        return jsonify({'status': 'skipped', 'route': route, 'language': language,
                        'detail': 'route is not warmable'}), 400

    review = payload.get('review')
    if review is not None:
        review = bool(review)

    started = time.monotonic()
    result = warm_page(
        current_app._get_current_object(),
        route,
        language,
        cookie_header=request.headers.get('Cookie', ''),
        review=review,
    )
    result['ms'] = int((time.monotonic() - started) * 1000)
    return jsonify(result)


@translation_admin_bp.route('/clear', methods=['POST'])
@login_required
@admin_required
def clear():
    """Drop cached translations for the given languages.

    Needed after the demo data is reloaded: the cache is keyed on a hash of the
    rendered page, so rows for the old data are not wrong, just unreachable —
    they accumulate and nothing ever reads them again.
    """
    payload = request.get_json(silent=True) or {}
    languages = [c for c in (payload.get('languages') or []) if c in SUPPORTED_LANGUAGES]

    if not languages:
        return jsonify({'error': 'No valid languages given'}), 400

    try:
        deleted = (
            TranslationCache.query
            .filter(TranslationCache.language_code.in_(languages))
            .delete(synchronize_session=False)
        )
        db.session.commit()
        return jsonify({'deleted': deleted, 'languages': languages})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning(f'Translation cache clear failed: {exc}')
        return jsonify({'error': str(exc)}), 500

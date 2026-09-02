"""
Cache warming for the translation service.

Translating a page costs two Groq calls and tens of seconds, and it happens
inside the response cycle. A reader who is first to a page in their language
pays that; everyone after them pays a database read. This module exists so
that nobody in a demo is ever the first reader.

It feeds pages through exactly the pipeline a real request uses --
services/translation_service.translate_response, so masking, the accounting
review pass, validation and the cache row are all identical -- with one
difference: the language is chosen by the administrator, not read from an
Accept-Language header. Nothing here inspects the browser's preference.

Why the pages are rendered through the test client rather than by calling
render_template: the cache key is a hash of the finished page, so a warmed
entry is only ever *hit* if a real request produces byte-identical HTML.
Anything short of a real trip through the routing, the before_request hooks,
the view and the template would render something subtly different and warm a
cache that could never hit. The only per-request variation in these pages is
the CSRF token, which the pipeline blanks before hashing.
"""

from flask import current_app

from services.translation_service import (
    SUPPORTED_LANGUAGES, is_translatable_route, page_size_limit, translate_response,
)

# Substrings that disqualify a route from warming. Some of these are
# destructive if fetched (a GET that toggles or ends something), some would end
# the warming session outright (logout), and some are downloads rather than
# pages. The URL map is the source of truth for what exists; this is the source
# of truth for what is safe to touch.
DENY_SUBSTRINGS = (
    'login', 'logout', 'delete', 'void', 'toggle', 'close', 'restart',
    'attest', '/pay', 'export', 'import', 'create-transactions', 'verify',
    'admin/translation',
)


def warmable_routes(app) -> list:
    """Every page worth warming: GET, no URL parameters, renders HTML, safe to fetch.

    Routes that take a parameter -- a member, a project, a journal entry -- are
    deliberately excluded. Warming those would mean translating a page per
    database row, which is a different and much larger job than translating the
    application's screens.
    """
    routes = set()

    for rule in app.url_map.iter_rules():
        if rule.endpoint == 'static' or rule.arguments:
            continue
        if 'GET' not in (rule.methods or set()):
            continue

        path = rule.rule
        # The audit trail and everything under it is never translated, so it is
        # never warmed either -- see translation_service.SKIP_ROUTE_PREFIXES.
        if not is_translatable_route(path):
            continue
        if path.endswith('.pdf'):
            continue
        if any(bad in path.lower() for bad in DENY_SUBSTRINGS):
            continue

        routes.add(path)

    return sorted(routes)


def warm_page(app, route: str, language_code: str, cookie_header: str = '',
              review: bool | None = None) -> dict:
    """Render one route as the calling administrator and translate it into one language.

    Returns a result dict the progress UI can render directly:
      status  'cached'  translated and stored (or already cached)
              'skipped' nothing to do -- not HTML, too large, or not a 200
              'failed'  the pipeline declined to translate; the page will
                        serve in English, which is the designed failure
    """
    if language_code not in SUPPORTED_LANGUAGES:
        return {'route': route, 'language': language_code,
                'status': 'skipped', 'detail': 'unsupported language'}

    client = app.test_client()

    # Accept-Language: en is load-bearing. The inner request runs the real
    # after_request hook, and without this it would try to translate itself --
    # a second, redundant trip through Groq whose result we would then throw
    # away. We want the English page; the translation is ours to drive.
    headers = {'Accept-Language': 'en'}
    if cookie_header:
        headers['Cookie'] = cookie_header

    try:
        response = client.get(route, headers=headers, follow_redirects=False)
    except Exception as exc:
        current_app.logger.warning(f'Warm render failed for {route}: {exc}')
        return {'route': route, 'language': language_code,
                'status': 'skipped', 'detail': f'render error: {exc}'}

    if response.status_code != 200:
        # A redirect here almost always means the session cookie did not carry
        # through, or the route is gated for this user.
        return {'route': route, 'language': language_code,
                'status': 'skipped', 'detail': f'HTTP {response.status_code}'}

    if 'text/html' not in (response.content_type or ''):
        return {'route': route, 'language': language_code,
                'status': 'skipped', 'detail': 'not HTML'}

    html = response.get_data(as_text=True)

    limit = page_size_limit()
    if len(html) > limit:
        # Same number the pipeline uses, so the warmer can never report a page
        # as translatable that translate_response would then refuse.
        return {'route': route, 'language': language_code, 'status': 'skipped',
                'detail': f'page too large ({len(html):,} chars, limit {limit:,})'}

    # The pipeline returns the original page unchanged on every failure path,
    # so it has to be asked why -- otherwise the screen can only say "not
    # translated", which is exactly the answer nobody can act on.
    report = {}
    translated = translate_response(html, language_code, route, review=review, report=report)

    if translated == html:
        return {'route': route, 'language': language_code, 'status': 'failed',
                'detail': report.get('detail', 'not translated — reason not recorded'),
                'bytes': len(html)}

    return {'route': route, 'language': language_code, 'status': 'cached',
            'bytes': len(html)}

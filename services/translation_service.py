"""
CARES Translation Service
Automatic page translation via Groq API with PostgreSQL caching.

Requires:
  - GROQ_API_KEY environment variable
  - GROQ_TRANSLATION_MODEL environment variable (optional; see DEFAULT_MODEL below)
  - 'requests' package (pip install requests)
  - TranslationCache model in models.py
"""

import hashlib
import os

import requests as http_requests
from flask import current_app

from models import db, TranslationCache
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Supported languages: ISO 639-1 code -> display name sent to the model
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {
    'ar': 'Arabic',
    'de': 'German',
    'es': 'Spanish',
    'fr': 'French',
    'it': 'Italian',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'tl': 'Tagalog',
    'vi': 'Vietnamese',
}

# Routes that are never translated (login page, the about page itself, etc.)
SKIP_ROUTES = frozenset({'/login', '/logout'})

# HTML responses larger than this are returned as-is (safeguard against huge pages)
MAX_HTML_CHARS = 100_000

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
# Model providers retire models, and this one fails SILENTLY when they do:
# _call_groq()'s exception handler logs and returns None, translate_response()
# then returns the untranslated page, and the only symptom is that nothing is
# translated. llama-3.3-70b-versatile and llama-3.1-8b-instant -- the previous
# value and the one the docstring named -- were both gone from Groq's model
# list by August 2026.
#
# openai/gpt-oss-20b was chosen over gpt-oss-120b and qwen3.8-27b by testing
# the actual job: translate a page while preserving tags, CSS classes, href
# values, currency amounts and proper nouns. qwen3.8-27b translated an
# organization's name ('Bishop Kelley Council' -> 'Consejo Bishop Kelley'),
# which is disqualifying for financial documents. Both gpt-oss models passed;
# 20b is cheaper and lower-latency, which matters because this runs
# synchronously in an after_request hook and the API bill goes to the chapter.
#
# Verify with: GET https://api.groq.com/openai/v1/models
DEFAULT_MODEL = 'openai/gpt-oss-20b'


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _content_hash(html: str) -> str:
    """16-char SHA-256 prefix — short enough for a DB column, collision-safe enough for pages."""
    return hashlib.sha256(html.encode()).hexdigest()[:16]

def get_cached_translation(html: str, language_code: str, route: str) -> str | None:
    """Return cached translation if available, None if cache miss."""
    if language_code not in SUPPORTED_LANGUAGES:
        return None
    try:
        cached = TranslationCache.query.filter_by(
            route=route,
            language_code=language_code,
            content_hash=_content_hash(html),
        ).first()
        return cached.translated_html if cached else None
    except Exception:
        return None
    
def _call_groq(html: str, language_name: str) -> str | None:
    """Call Groq chat completion API. Returns translated HTML or None on failure."""
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        current_app.logger.warning('GROQ_API_KEY not set — translation skipped')
        return None

    model = os.environ.get('GROQ_TRANSLATION_MODEL', DEFAULT_MODEL)

    prompt = (
        f'You are a professional HTML translator. '
        f'Translate all human-readable text in the HTML below from English to {language_name}.\n\n'
        f'STRICT RULES — violations will break the application:\n'
        f'- Preserve ALL HTML tags, attributes, CSS classes, and data-* attributes exactly\n'
        f'- Preserve ALL href, src, action, and id attribute values\n'
        f'- Preserve ALL numbers, currency amounts (e.g. $1,234.56), and account numbers\n'
        f'- Preserve ALL proper nouns: organization names, person names, place names\n'
        f'- Do NOT translate or alter text inside <script> or <style> tags\n'
        f'- Do NOT wrap the output in markdown fences or add any explanation\n'
        f'- Return ONLY the translated HTML, nothing else\n\n'
        f'HTML:\n{html}'
    )

    import time
    for attempt in range(2):
        try:
            resp = http_requests.post(
                GROQ_API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.1,
                    'max_tokens': 32768,
                },
                timeout=45,
            )
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            if resp.status_code == 429 and attempt == 0:
                current_app.logger.warning('Groq rate limited — waiting 10s and retrying')
                time.sleep(10)
                continue
            current_app.logger.warning(
                f'Groq API returned {resp.status_code}: {resp.text[:200]}'
            )
            break
        except Exception as exc:
            current_app.logger.warning(f'Groq API call failed: {exc}')
            break

    return None


def _strip_markdown_fences(text: str) -> str:
    """Remove accidental ```html ... ``` wrapping some models add."""
    if not text.startswith('```'):
        return text
    lines = text.split('\n')
    start = 1
    end = len(lines) - 1 if lines[-1].strip() == '```' else len(lines)
    return '\n'.join(lines[start:end])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_language(accept_language_header: str) -> str:
    """
    Parse the Accept-Language request header and return the best supported
    language code.  Returns 'en' if nothing supported is found.

    Example header: 'es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7'
    """
    if not accept_language_header:
        return 'en'

    candidates = []
    for part in accept_language_header.split(','):
        part = part.strip()
        if ';q=' in part:
            code, q_str = part.split(';q=', 1)
            try:
                weight = float(q_str)
            except ValueError:
                weight = 0.0
        else:
            code = part
            weight = 1.0
        candidates.append((code.strip().lower(), weight))

    candidates.sort(key=lambda x: x[1], reverse=True)

    for code, _ in candidates:
        primary = code.split('-')[0]
        if primary == 'en':
            return 'en'
        if code in SUPPORTED_LANGUAGES:
            return code
        if primary in SUPPORTED_LANGUAGES:
            return primary

    return 'en'


def translate_response(html: str, language_code: str, route: str) -> str:
    """
    Return the HTML translated to language_code, using the cache when available.
    Always returns valid HTML — falls back to the original on any error.
    """
    if language_code not in SUPPORTED_LANGUAGES:
        return html

    if len(html) > MAX_HTML_CHARS:
        current_app.logger.debug(
            f'Translation skipped for {route}: page too large ({len(html)} chars)'
        )
        return html

    content_hash = _content_hash(html)

    # Cache hit?
    try:
        cached = TranslationCache.query.filter_by(
            route=route,
            language_code=language_code,
            content_hash=content_hash,
        ).first()
        if cached:
            return cached.translated_html
    except Exception as exc:
        current_app.logger.warning(f'Translation cache read error: {exc}')

    # Cache miss — call API
    language_name = SUPPORTED_LANGUAGES[language_code]
    translated = _call_groq(html, language_name)

    if not translated:
        return html

    translated = _strip_markdown_fences(translated)

    # Write to cache
    try:
        db.session.execute(
            text(
                'INSERT INTO translation_cache (route, language_code, content_hash, translated_html, created_at) '
                'VALUES (:route, :lang, :hash, :html, NOW()) '
                'ON CONFLICT ON CONSTRAINT uq_translation_cache DO NOTHING'
            ),
            {'route': route, 'lang': language_code, 'hash': content_hash, 'html': translated}
        )
        db.session.commit()
    except Exception as exc:
        current_app.logger.warning(f'Translation cache write error: {exc}')
        db.session.rollback()

    return translated

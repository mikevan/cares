"""
CARES Translation Service
Automatic page translation via Groq API with PostgreSQL caching.

Financial values never reach the API. See services/translation_masking.py --
currency amounts and GL account numbers are replaced with opaque placeholders
before the call and restored afterwards, and any response with a placeholder
missing is discarded in favour of the untranslated English page.

Requires:
  - GROQ_API_KEY environment variable
  - GROQ_TRANSLATION_MODEL environment variable (optional; see DEFAULT_MODEL below)
  - 'requests' package (pip install requests)
  - TranslationCache model in models.py
"""

import hashlib
import os
import time

import requests as http_requests
from flask import current_app

from config import parse_bool_env
from models import db, TranslationCache
from sqlalchemy import text

from services.translation_masking import (
    mask_values, restore_values,
    extract_csrf, reinject_csrf, csrf_placeholder_intact,
)
from services.translation_segments import (
    delocalise, find_segments, localise, mark, parse_response, reassemble,
)

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

# Whole route trees that are never translated, in any language, by any means --
# not by a browser's Accept-Language, not by ?lang=, not by the cache warmer.
#
# /audit is the Trustee Audit Report, chain verification and the Form 1295
# attestation screens. Those pages exist to show what is in audit_log exactly
# as it was written: a hash-chained, tamper-evident record whose whole value is
# that a trustee can read the stored before/after values and verify the chain
# over them. A translated value is no longer the evidence, it is a rendering of
# the evidence, and nothing downstream can tell the difference. Under Section
# 145 the trustees are auditing the officers; handing them a page that has been
# through a language model, however faithfully, breaks the chain of evidence.
#
# This is not a display preference. It is the reason the audit trail exists.
SKIP_ROUTE_PREFIXES = ('/audit', '/static')

# Deliberate carve-outs from the trees above. Exact paths only -- a prefix here
# would quietly re-admit anything added beneath it.
#
# /audit/form-1295 reads nothing from audit_log. It computes Schedules A, B and
# C directly from the ledger (services/kofc_form_1295.py), which makes it a
# derived financial report of the same kind as the balance sheet; it sits under
# /audit only because of where its route was registered. Its own docstring
# draws the line: it is "the document a council actually files", while the
# change-log report is "the tamper-evident evidence underneath it".
#
# Its currency amounts and account numbers are masked and restored exactly like
# any other page, and the schedule PDFs -- the artifact actually filed with
# Supreme and the state office -- are never translated at all, because the hook
# only touches text/html. So a financial secretary can read the schedules in
# their own language and still file them in English.
TRANSLATABLE_EXCEPTIONS = frozenset({'/audit/form-1295'})


def is_translatable_route(path: str) -> bool:
    """False for anything that must be served exactly as the database holds it.

    The audit tree is default-deny: a route added under /audit is exempt until
    somebody consciously lists it above. That is the right way round for pages
    that may carry evidence.
    """
    if path in TRANSLATABLE_EXCEPTIONS:
        return True
    if path in SKIP_ROUTES:
        return False
    for prefix in SKIP_ROUTE_PREFIXES:
        if path == prefix or path.startswith(prefix + '/'):
            return False
    return True

# Size guards, per mode.
#
# 'page' mode asks the model to return the whole document, so the ceiling is
# how much markup it can retype: the completion cap, not the context window.
#
# 'segments' mode returns only the words, so the completion is a fraction of
# the page and the binding limit moves to the input side of the context
# window -- several times more page for the same model.
MAX_HTML_CHARS = 100_000
MAX_HTML_CHARS_SEGMENTS = 300_000

# Above this, a segment-mode review does not fit: the reviewer is sent the page
# AND the translations, so it needs roughly twice the input of the first pass.
# Past it the page is translated once and served without the review.
REVIEW_MAX_CHARS = 150_000

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Groq sits behind Cloudflare, which bans some client signatures outright and
# answers with HTTP 403 and 'error code: 1010' -- not a JSON API error, and
# nothing to do with the key. A default Python user agent is one of the
# signatures it rejects, so identify the application explicitly.
USER_AGENT = 'CARES-Translation/1.0 (+https://github.com/mikevan/cares)'

# All of this runs inside after_request, so the whole pipeline shares one
# worker for its duration and Gunicorn kills that worker at --timeout 120. Two
# 45-second calls plus a rate-limit retry would clear that on their own, so the
# work is given a budget and the review pass -- the optional half -- is what
# gets dropped when the budget runs short. A page translated once is worth more
# than a 502.
RESPONSE_BUDGET_SECONDS = 600

# Strings are requested in batches. The Chart of Accounts renders 683 of them,
# and asked for all at once the model answered "I'm sorry, but I can't provide"
# in thirty-six characters -- a refusal, not a failure. It never attempted the
# work, twice, in ten seconds each.
#
# Nothing about the page was the problem; the size of the single answer was.
# Each call still carries the WHOLE page, so context is untouched -- the model
# reads everything and is asked to write back one slice of it. That the page
# sits at the front of the prompt means every batch after the first reuses it
# as a cached prefix, so the extra calls cost far less than they look.
SEGMENT_BATCH_SIZE = 75
MIN_SEGMENT_BATCH = 20
REVIEW_MIN_SECONDS = 45

# A dropped numbered line or a mangled placeholder is a coin flip, not a
# property of the page: re-running a failed warm usually succeeds. So the
# pipeline flips the coin twice before giving up, budget permitting. A page
# that fails both times is telling you something real.
MAX_TRANSLATION_ATTEMPTS = 2

# A string that fails validation keeps its English. The page is not discarded
# for it.
#
# Fail-closed was right; page-level was the wrong granularity. One tip line the
# model wrapped in markup was throwing away a correct translation of every
# financial label on the same page, and the reader got English for all of it.
# A failing string now falls back to its own source text -- the page's own
# words, so nothing about it can be wrong, and the money is the money.
#
# Past this it is systemic rather than incidental, and the whole page goes
# back to English as before. The absolute floor matters: a short form with
# three strings would otherwise be condemned by a single bad line, since one
# in three is a third of the page.
MAX_STRINGS_KEPT_IN_ENGLISH = 0.20
MIN_STRINGS_BEFORE_DISCARD = 3
RETRY_MIN_SECONDS = 60

# A flat 45s cut the chart of accounts off mid-response. Big pages generate for
# longer, so the timeout scales with the work and caps at 180s.
#
# NOTE FOR RENDER: the Procfile runs Gunicorn with --timeout 120. A call that
# takes 180s there gets its worker killed, and the reader sees a 502 rather
# than the English fallback. Raise --timeout to 300 before deploying this, or
# lower TRANSLATION_TIMEOUT_CAP to 90 for that environment.
TRANSLATION_TIMEOUT_CAP = 180

# Groq's free tier has a tokens-per-minute ceiling, and a full warm run walks
# straight into it: 26 pages x 2 calls x tens of thousands of tokens inside a
# few minutes. A 429 means the request was fine and will succeed shortly, so it
# is waited out rather than reported as a failure.
RATE_LIMIT_MAX_WAIT = 90

# gpt-oss models reason before they answer, and reasoning is generated text.
# On a large page that thinking can eat the completion and leave an empty
# message -- a 200 OK with nothing in it, after a minute of billing.
#
# Translating marked strings is not a reasoning problem. It is a long,
# mechanical transformation where the work is in the reading, and 'low' spends
# the budget on output instead of deliberation. The review pass is the one
# genuine judgement call in the pipeline, so it keeps a higher setting.
#
# Both are overridable; an unsupported value is a 400, which the error
# reporting now surfaces plainly rather than swallowing.
TRANSLATION_REASONING_EFFORT = os.environ.get('GROQ_REASONING_EFFORT', 'low')
REVIEW_REASONING_EFFORT = os.environ.get('GROQ_REVIEW_REASONING_EFFORT', 'medium')


def _retry_after_seconds(resp) -> int:
    """How long Groq asked us to wait, clamped to something sane."""
    for header in ('retry-after', 'x-ratelimit-reset-tokens',
                   'x-ratelimit-reset-requests'):
        raw = (resp.headers or {}).get(header)
        if not raw:
            continue
        try:
            # retry-after is plain seconds; the reset headers look like '7.66s'
            # or '2m59.56s'.
            text = str(raw).strip().lower()
            if 'm' in text:
                minutes, _, rest = text.partition('m')
                seconds = float(rest.rstrip('s') or 0)
                return max(1, int(float(minutes) * 60 + seconds) + 1)
            return max(1, int(float(text.rstrip('s'))) + 1)
        except (TypeError, ValueError):
            continue
    return 20

# A big page generates for longer, and a flat 45s cut the chart of accounts off
# mid-response. Scale with the work, and cap short of the request budget so a
# timeout never becomes a killed Gunicorn worker.
def _timeout_for(html: str) -> int:
    return int(min(TRANSLATION_TIMEOUT_CAP, max(60, 40 + len(html) / 600)))
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

# The review pass runs on a different model by default, for two reasons.
#
# Groq's rate limits are per organization AND per model, so a warm run that
# sends every page twice to gpt-oss-20b spends one bucket twice as fast.
# Splitting the passes draws on two.
#
# The larger model is also the better reviewer: judging whether 'balance'
# should be 'saldo' here and 'Balance General' there is exactly the kind of
# call worth more parameters, and the review runs once per page rather than on
# every read, so it is the cheap place to spend them.
DEFAULT_REVIEW_MODEL = 'openai/gpt-oss-120b'


def _review_model() -> str:
    return os.environ.get('GROQ_REVIEW_MODEL', DEFAULT_REVIEW_MODEL)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _content_hash(html: str) -> str:
    """16-char SHA-256 prefix — short enough for a DB column, collision-safe enough for pages.

    Always hash a page whose CSRF token has been blanked (see _cache_key_html).
    Hashing the raw page hashes a fresh timed signature every request, which is
    why this cache used to miss one hundred percent of the time.
    """
    return hashlib.sha256(html.encode()).hexdigest()[:16]


def _cache_key_html(html: str) -> str:
    """The form of the page the cache key is computed from: CSRF token blanked."""
    blanked, _ = extract_csrf(html)
    return blanked


def get_cached_translation(html: str, language_code: str, route: str) -> str | None:
    """Return cached translation if available, None if cache miss.

    NOTE: the returned HTML still carries the CSRF placeholder. Callers must
    pass it through reinject_csrf() with the current request's token before
    serving it. translate_response() does this for you.
    """
    if language_code not in SUPPORTED_LANGUAGES:
        return None
    try:
        cached = TranslationCache.query.filter_by(
            route=route,
            language_code=language_code,
            content_hash=_content_hash(_cache_key_html(html)),
        ).first()
        return cached.translated_html if cached else None
    except Exception:
        return None


# The domain the reviewer is asked to hold the translation to. Kept in one
# place because both the translation prompt and the review prompt need to
# describe the same world.
DOMAIN_CONTEXT = (
    'This is a page from a nonprofit fund-accounting system used by a Knights of '
    'Columbus council: journal entries, a chart of accounts, accounts payable and '
    'receivable, member dues, project budgets, Form 1295 schedules, and the four '
    'financial statements. Every term must read as it would in published financial '
    'statements, not as it would in ordinary speech.'
)

# Sentinel the reviewer returns when it finds nothing to correct. Cheap, and it
# keeps a clean translation from being rewritten for the sake of answering.
NO_CHANGES = 'NO_CHANGES'


def _translation_prompt(html: str, language_name: str) -> str:
    """First pass: translate."""
    return (
        f'You are a professional translator working on financial documents. '
        f'{DOMAIN_CONTEXT}\n\n'
        f'Translate all human-readable text in the HTML below from English to {language_name}. '
        f'Where an English term has both an everyday sense and an accounting sense, '
        f'use the accounting sense, in the register a {language_name}-speaking accountant '
        f'would read on a financial statement. Render the same English term the same way '
        f'everywhere on the page.\n\n'
        f'STRICT RULES — violations will break the application:\n'
        f'- Preserve ALL HTML tags, attributes, CSS classes, and data-* attributes exactly\n'
        f'- Preserve ALL href, src, action, and id attribute values\n'
        f'- The HTML contains placeholders of the form __CARES_V0000__ and __CARES_CSRF_TOKEN__.\n'
        f'  Copy every placeholder through character for character, in the same place.\n'
        f'  Do NOT translate them, renumber them, reformat them, remove them, duplicate them,\n'
        f'  or invent new ones. A page with one placeholder wrong is discarded entirely.\n'
        f'- Preserve ALL remaining numbers and dates exactly as written\n'
        f'- Preserve ALL proper nouns: organization names, council names, person names, place names\n'
        f'- Do NOT translate or alter text inside <script> or <style> tags\n'
        f'- Do NOT wrap the output in markdown fences or add any explanation\n'
        f'- Return ONLY the translated HTML, nothing else\n\n'
        f'HTML:\n{html}'
    )


def _review_prompt(source_html: str, translated_html: str, language_name: str) -> str:
    """Second pass: check the first one against a rubric.

    Deliberately NOT 'are you sure?'. Undifferentiated doubt makes a model
    revise work that was already right — it reads the question as a signal that
    something is wrong and finds something to change. A reviewer given a named
    rubric and told to return a sentinel when the work passes has a job it can
    actually decline to do, which is what makes its corrections worth having.
    """
    return (
        f'You are a bilingual accounting reviewer checking a machine translation. '
        f'{DOMAIN_CONTEXT}\n\n'
        f'You are given the ENGLISH SOURCE and a {language_name} TRANSLATION of it. '
        f'Check the translation against this rubric, in order:\n\n'
        f'1. ACCOUNTING REGISTER. Every term with both an everyday and an accounting sense '
        f'must use the accounting sense as it appears in published {language_name} financial '
        f'statements. In English the terms that carry this risk include: balance, entry, post, '
        f'statement, account, book, fund, dues, charge, credit, debit, payable, receivable, '
        f'reconcile, closing, period, trustee, audit, asset, liability, equity, disbursement.\n'
        f'2. CONSISTENCY. The same English term must be rendered the same way everywhere on '
        f'the page. Two defensible renderings of one term is still an error.\n'
        f'3. PROPER NOUNS unchanged: organization names, council names, person names, place names.\n'
        f'4. PLACEHOLDERS (__CARES_V0000__, __CARES_CSRF_TOKEN__) present, unaltered, same count.\n'
        f'5. HTML tags, attributes, classes and href/src/id values identical to the source.\n\n'
        f'Do not restyle, re-punctuate, shorten, or improve fluency. Change only what the '
        f'rubric requires. A translation that satisfies the rubric needs no changes, and '
        f'saying so is the correct answer — do not invent corrections to justify the review.\n\n'
        f'If the translation satisfies the rubric, reply with exactly: {NO_CHANGES}\n'
        f'Otherwise reply with the corrected {language_name} HTML only, nothing else.\n\n'
        f'ENGLISH SOURCE:\n{source_html}\n\n'
        f'{language_name.upper()} TRANSLATION:\n{translated_html}'
    )


def _call_groq(prompt: str, timeout: int = 45, allow_retry: bool = True,
               report: dict | None = None, model: str | None = None,
               reasoning_effort: str | None = None) -> str | None:
    """Call Groq chat completion API. Returns the message content or None on failure.

    allow_retry=False suppresses the 10-second wait-and-retry on a 429. The
    review pass sets it: a second opinion is not worth spending the request
    budget that the page itself might need.
    """
    def _note(detail):
        if report is not None:
            report['detail'] = detail

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        current_app.logger.warning('GROQ_API_KEY not set — translation skipped')
        _note('GROQ_API_KEY is not set')
        return None

    model = model or os.environ.get('GROQ_TRANSLATION_MODEL', DEFAULT_MODEL)

    for attempt in range(3):
        try:
            resp = http_requests.post(
                GROQ_API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'User-Agent': USER_AGENT,
                },
                json={
                    'model': model,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.1,
                    # Groq allows 65,536 output tokens for gpt-oss-20b and we
                    # pay for what is generated, not for the ceiling. The whole
                    # translated page has to come back in one response, and a
                    # response cut off at the cap loses its masking placeholders
                    # and is discarded -- so a low ceiling reads as "the model
                    # cannot translate this page" when it means "we did not let
                    # it finish". Non-Latin scripts need roughly twice the
                    # tokens per character, which is where this bit first.
                    'max_tokens': 65536,
                    'reasoning_effort': reasoning_effort or TRANSLATION_REASONING_EFFORT,
                    'include_reasoning': False,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                payload = resp.json()
                choice = (payload.get('choices') or [{}])[0]
                content = (choice.get('message') or {}).get('content') or ''
                finish = choice.get('finish_reason')
                usage = payload.get('usage') or {}

                if finish and finish != 'stop':
                    current_app.logger.warning(
                        f'{model} stopped with finish_reason={finish} '
                        f'(completion_tokens={usage.get("completion_tokens")})'
                    )

                if not content.strip():
                    # A 200 with nothing in it. gpt-oss models reason before
                    # they answer, and on a large page the whole completion
                    # budget can go to reasoning, leaving an empty message.
                    # This used to fall through every error branch and surface
                    # as a bare 'not translated', which is the one answer
                    # nobody can act on.
                    current_app.logger.warning(
                        f'{model} returned an empty message for a {len(prompt):,}-char '
                        f'prompt (finish_reason={finish}, '
                        f'completion_tokens={usage.get("completion_tokens")})'
                    )
                    _note(
                        f'the model returned an empty response '
                        f'(finish_reason={finish}, '
                        f'completion_tokens={usage.get("completion_tokens")})'
                    )
                    if allow_retry and attempt < 2:
                        continue
                    break

                return content
            if resp.status_code == 429:
                # Groq tells us how long to wait. Honour it rather than
                # guessing: a fixed sleep either gives up too early or throws
                # away budget. A 429 is throughput, not a failed request.
                wait = _retry_after_seconds(resp)
                _note(f'rate limited by Groq — waited but the limit held ({wait}s)')
                if allow_retry and attempt < 2 and wait <= RATE_LIMIT_MAX_WAIT:
                    current_app.logger.warning(
                        f'Groq rate limited — waiting {wait}s, attempt '
                        f'{attempt + 2} of 3'
                    )
                    time.sleep(wait)
                    continue
                current_app.logger.warning(
                    f'Groq rate limited, giving up (asked for {wait}s, '
                    f'allow_retry={allow_retry})'
                )
                _note(f'rate limited by Groq; it asked for {wait}s and that was too long to wait')
                break
            if resp.status_code == 403 and 'error code: 1010' in (resp.text or ''):
                _note('refused at the edge (Cloudflare 1010) — client signature, not the key')
                current_app.logger.warning(
                    'Groq refused the request at the edge (Cloudflare 1010): the client '
                    'signature is banned, not the API key. Check the User-Agent header '
                    'and any TLS-inspecting proxy between this host and api.groq.com.'
                )
                break
            current_app.logger.warning(
                f'Groq API returned {resp.status_code}: {resp.text[:200]}'
            )
            _note(f'Groq returned HTTP {resp.status_code}: {(resp.text or "")[:120]}')
            break
        except Exception as exc:
            current_app.logger.warning(f'Groq API call failed: {exc}')
            _note(f'API call failed: {type(exc).__name__} — {str(exc)[:120]}')
            break

    if report is not None and 'detail' not in report:
        # Belt and braces: a silent None here shows up on screen as a bare
        # 'not translated', which is the one answer nobody can act on.
        report['detail'] = f'no usable response from {model} after {attempt + 1} attempt(s)'
    return None


def _strip_markdown_fences(text: str) -> str:
    """Remove accidental ```html ... ``` wrapping some models add."""
    if not text.startswith('```'):
        return text
    lines = text.split('\n')
    start = 1
    end = len(lines) - 1 if lines[-1].strip() == '```' else len(lines)
    return '\n'.join(lines[start:end])


def _review_enabled() -> bool:
    """Whether to run the accounting-register review pass. On unless switched off.

    Read per call rather than at import so it can be flipped without a redeploy
    in an emergency, and so tests can toggle it.
    """
    return parse_bool_env('ENABLE_TRANSLATION_REVIEW', default=True)


def _restore_or_none(candidate_html: str, tokens: dict, csrf_token,
                     counts: dict | None = None,
                     report: dict | None = None) -> str | None:
    """Validate a model response and put the real values back, or reject it.

    Returns None if the response is not safe to serve: a lost CSRF placeholder,
    or any masked value the model dropped, duplicated or invented.
    """
    if not csrf_placeholder_intact(candidate_html, csrf_token):
        if report is not None:
            report['detail'] = 'discarded: the CSRF placeholder was lost in translation'
        return None
    return restore_values(candidate_html, tokens, counts=counts, report=report)


def _review_translation(source_html: str, translated_html: str, language_name: str,
                        timeout: int = 30) -> str | None:
    """Second pass over a translation. Returns amended HTML, or None to keep the first pass.

    None covers three cases that are all the same decision: the API failed, the
    reviewer found nothing to correct, or the reviewer answered with something
    that is not a page. In every one of them the first-pass translation stands.
    """
    reviewed = _call_groq(
        _review_prompt(source_html, translated_html, language_name),
        timeout=timeout,
        allow_retry=False,
    )
    if not reviewed:
        return None

    if reviewed.strip().upper().startswith(NO_CHANGES):
        return None

    amended = _strip_markdown_fences(reviewed)
    # A reviewer that answered in prose ('The translation is correct.') has not
    # given us a page, whatever it meant by it.
    if '<' not in amended:
        return None
    return amended


def page_size_limit() -> int:
    """The largest page the current mode can translate, in characters.

    Public because the cache warmer needs to answer 'would this page be
    skipped?' with the same number the pipeline would use, rather than a copy
    of it that drifts.
    """
    return MAX_HTML_CHARS_SEGMENTS if _translation_mode() == 'segments' else MAX_HTML_CHARS


def _translation_mode() -> str:
    """'segments' (default) or 'page'.

    'page' is the original behaviour -- send the document, get the document
    back. It is kept as an escape hatch: one environment variable reverts to it
    if segment mode ever misbehaves against a model, with no deploy.
    """
    mode = (os.environ.get('TRANSLATION_MODE') or 'segments').strip().lower()
    return mode if mode in ('segments', 'page') else 'segments'


def _page_preamble(marked_html: str) -> str:
    """The page, byte for byte, at the very front of every prompt about it.

    Groq caches prompt prefixes and — this is the point — cached tokens do not
    count against the organization's tokens-per-minute limit. The translate
    call and the review call carry the same page, so putting it first and
    identical in both means the review call's copy is a cache hit: no second
    charge, and no second bite out of the rate limit. Retries hit it too.

    Instructions come after the page. 'Here is the document, now do this' reads
    at least as well as the reverse, and the ordering is what makes the cache
    work.
    """
    return f'PAGE:\n{marked_html}\n\n'


def _translate_batch(marked, language_name, batch, total, route, language_code,
                     started, report, depth=0):
    """Translate one batch, halving it if the model balks. Returns {index: text}.

    150 markers in one request drew a flat refusal in production -- "I'm sorry,
    but I can't provide that" -- on two pages, twice each, while the 34-marker
    batch beside it succeeded. The line is somewhere below 150 and nobody knows
    where, so the batch finds it: a request the model will not attempt is split
    and asked again, down to MIN_SEGMENT_BATCH.

    Guessing a smaller constant would work until a page grew, or a model
    changed, and then fail the same way with no signal.
    """
    wanted = set(batch)
    chunk = _call_groq(
        _segment_translation_prompt(marked, language_name, batch, total),
        timeout=min(_timeout_for(marked), 120),
        report=report,
    )
    got = parse_response(_strip_markdown_fences(chunk), wanted, require_all=False) or {} if chunk else {}

    if len(got) >= len(wanted) / 2:
        return got

    head = _strip_markdown_fences(chunk or '').strip()[:200].replace('\n', ' | ')
    if chunk:
        report['response_head'] = head

    if len(batch) <= MIN_SEGMENT_BATCH or depth >= 4 or _budget_left(started) < RETRY_MIN_SECONDS:
        current_app.logger.warning(
            f'{route} ({language_code}): batch #{batch[0]}-{batch[-1]} '
            f'({len(batch)} strings) returned {len(got)} and cannot be split '
            f'further. It began: {head!r}'
        )
        return got

    mid = len(batch) // 2
    current_app.logger.info(
        f'{route} ({language_code}): batch #{batch[0]}-{batch[-1]} returned '
        f'{len(got)} of {len(wanted)}; splitting. It began: {head!r}'
    )
    merged = _translate_batch(marked, language_name, batch[:mid], total, route,
                              language_code, started, report, depth + 1)
    merged.update(_translate_batch(marked, language_name, batch[mid:], total, route,
                                   language_code, started, report, depth + 1))
    return merged


def _batches(indices) -> list:
    """Marker numbers, in order, in chunks small enough to be answered."""
    ordered = sorted(indices)
    return [ordered[i:i + SEGMENT_BATCH_SIZE]
            for i in range(0, len(ordered), SEGMENT_BATCH_SIZE)]


def _range_clause(batch, total) -> str:
    if batch is None or len(batch) == total:
        return ''
    return (
        f'\n\nTHIS REQUEST COVERS ONLY MARKERS [[S{batch[0]}]] THROUGH [[S{batch[-1]}]].\n'
        f'Read the whole page above for context, then return lines for those '
        f'{len(batch)} markers and no others. Other parts of the page are being '
        f'handled separately; ignore their markers entirely.'
    )


def _segment_translation_prompt(marked_html: str, language_name: str,
                                batch=None, total=None) -> str:
    """First pass, segment mode: read everything, write only the words."""
    return _page_preamble(marked_html) + _range_clause(batch, total) + (
        f'You are a professional translator working on financial documents. '
        f'{DOMAIN_CONTEXT}\n\n'
        f'Below is a complete HTML page. Every string that needs translating is preceded '
        f'by a marker of the form [[S12]]. The string runs from the marker to the next '
        f'HTML tag, or to the closing quote if the marker sits inside an attribute.\n\n'
        f'Read the WHOLE page before you translate anything. The table a cell sits in, the '
        f'column header above it and the statement it belongs to are what decide which '
        f'sense of a word is correct. Where an English term has both an everyday and an '
        f'accounting sense, use the accounting sense, in the register a '
        f'{language_name}-speaking accountant would read on a financial statement. Render '
        f'the same English term the same way everywhere on the page.\n\n'
        f'Translate each marked string from English to {language_name}.\n\n'
        f'OUTPUT FORMAT — nothing else is accepted:\n'
        f'One line per marker, the marker number, a colon, then the translation:\n'
        f'12: Estado de Actividades\n\n'
        f'RULES:\n'
        f'- Exactly one line for every marker on the page. Do not omit any. Do not invent any.\n'
        f'- Do NOT return HTML. Do not repeat the [[S..]] marker inside the translation.\n'
        f'- Do not translate anything that is not marked.\n'
        f'- Some strings contain placeholders written [[V1]], [[V2]] and so on, standing for '
        f'financial values. Copy them character for character into the same string. Do not '
        f'translate, renumber or reformat them, and never move one into a different '
        f'numbered line — [[V1]] on line 12 has nothing to do with [[V1]] on line 13.\n'
        f'- Leave proper nouns as they are: organization names, council names, person names, '
        f'place names.\n'
        f'- Leave numbers and dates exactly as written.\n'
        f'- Return ONLY the text of each marked string. Never include an HTML tag: if a '
        f'string ends where a tag begins, your line ends there too.\n'
        f'- Translate what is there. Do not add words, numbers, form numbers, or '
        f'explanations that are not in the English string, however helpful they seem.\n'
        f'- Character references such as &#39; and &amp; may be written as the plain '
        f'character they stand for.'
    )


def _segment_review_prompt(marked_html: str, translations: dict, language_name: str,
                           batch=None, total=None) -> str:
    """Second pass, segment mode: correct only what the rubric requires.

    Same page preamble as the translation prompt, deliberately identical, so
    this call reuses that cached prefix instead of paying for it again.
    """
    rendered = '\n'.join('%d: %s' % (i, translations[i]) for i in sorted(translations))
    return _page_preamble(marked_html) + _range_clause(batch, total) + (
        f'You are a bilingual accounting reviewer checking a machine translation. '
        f'{DOMAIN_CONTEXT}\n\n'
        f'Below is an English page whose translatable strings are marked [[S12]], followed '
        f'by the {language_name} translation of each marked string. Use the page for '
        f'context — the surrounding table, headers and totals are what make a term\'s '
        f'sense clear.\n\n'
        f'Check the translations against this rubric, in order:\n\n'
        f'1. ACCOUNTING REGISTER. Every term with both an everyday and an accounting sense '
        f'must use the accounting sense as it appears in published {language_name} financial '
        f'statements. In English the terms that carry this risk include: balance, entry, post, '
        f'statement, account, book, fund, dues, charge, credit, debit, payable, receivable, '
        f'reconcile, closing, period, trustee, audit, asset, liability, equity, disbursement.\n'
        f'2. CONSISTENCY. The same English term must be rendered the same way in every '
        f'string. Two defensible renderings of one term is still an error.\n'
        f'3. PROPER NOUNS unchanged: organization, council, person and place names.\n'
        f'4. PLACEHOLDERS (__CARES_V0000__, __CARES_CSRF_TOKEN__) present and unaltered.\n\n'
        f'Do not restyle, re-punctuate, shorten or improve fluency. Change only what the '
        f'rubric requires. Translations that satisfy the rubric need no changes, and saying '
        f'so is the correct answer — do not invent corrections to justify the review.\n\n'
        f'If nothing needs changing, reply with exactly: {NO_CHANGES}\n'
        f'Otherwise reply with ONLY the numbered lines you would change, in the same '
        f'"number: translation" format. Do not repeat lines you are leaving alone.\n\n'
        f'{language_name.upper()} TRANSLATIONS:\n{rendered}'
    )


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


def _budget_left(started: float) -> float:
    return RESPONSE_BUDGET_SECONDS - (time.monotonic() - started)


def _translate_whole_page(masked_html, tokens, counts, csrf_token, language_name,
                          route, language_code, want_review, started, report=None):
    """Original mode: the model returns the entire document, markup and all.

    Kept as an escape hatch behind TRANSLATION_MODE=page.
    """
    translated = _call_groq(_translation_prompt(masked_html, language_name),
                            timeout=_timeout_for(masked_html), report=report)
    if not translated:
        return None

    translated = _strip_markdown_fences(translated)

    restored = _restore_or_none(translated, tokens, csrf_token)
    if restored is None:
        current_app.logger.warning(
            f'Translation discarded for {route} ({language_code}): '
            f'model altered a masked financial value or lost the CSRF placeholder '
            f'({len(tokens)} placeholders sent). Serving untranslated English.'
        )
        if report is not None:
            report['detail'] = (f'discarded: a masked value or the CSRF placeholder was '
                                f'altered ({len(tokens)} sent)')
        return None

    remaining = _budget_left(started)
    if want_review and remaining < REVIEW_MIN_SECONDS:
        current_app.logger.info(
            f'Translation review skipped for {route} ({language_code}): '
            f'{remaining:.0f}s left of the {RESPONSE_BUDGET_SECONDS}s budget'
        )
    elif want_review:
        amended = _review_translation(
            masked_html, translated, language_name, timeout=int(min(30, remaining)),
        )
        if amended is not None:
            amended_restored = _restore_or_none(amended, tokens, csrf_token, counts=counts)
            if amended_restored is not None:
                current_app.logger.info(f'Translation review amended {route} ({language_code})')
                restored = amended_restored
            else:
                current_app.logger.warning(
                    f'Translation review output rejected for {route} ({language_code}); '
                    f'keeping the first-pass translation'
                )
    return restored


def _segment_attempt(marked, masked_html, segments, expected, tokens, counts, csrf_token,
                     language_name, route, language_code, want_review, started, report):
    """One trip to the model: translate, optionally review, reassemble, validate."""
    batches = _batches(expected)
    if len(batches) > 1:
        current_app.logger.info(
            f'{route} ({language_code}): {len(expected)} strings in {len(batches)} '
            f'batches of up to {SEGMENT_BATCH_SIZE}'
        )

    # Parse permissively so a failure can say how far off the response was.
    # 'returned 210 of 213 strings, missing 47, 48, 49' is a diagnosis;
    # 'not translated' is a shrug.
    partial = {}
    for batch in batches:
        partial.update(_translate_batch(marked, language_name, batch, len(expected),
                                        route, language_code, started, report))

    if not partial:
        return None
    missing = sorted(expected - set(partial))
    if missing:
        current_app.logger.info(
            f'{route} ({language_code}): model returned {len(partial)} of '
            f'{len(expected)} strings; #{missing[:10]} stay in English.'
        )

    # Put each string's global placeholder back before anything is reassembled.
    # A value borrowed from a different numbered line dies here, on the line
    # that borrowed it, instead of silently corrupting the page.
    localised = {}
    kept_english = []
    for segment in segments:
        index = segment['index']
        if index not in partial:
            kept_english.append((index, 'the model did not return it'))
            localised[index] = segment['text']
            continue
        why = {}
        restored_text = delocalise(segment, partial[index], report=why)
        if restored_text is None:
            # Show the string as a person would read it, not as the model saw
            # it: a diagnostic full of __CARES_V0000__ tells you nothing about
            # which line on the page went wrong.
            readable = segment['text']
            for global_token, value in tokens.items():
                readable = readable.replace(global_token, value)
            reason = why.get('detail', 'failed validation')
            # The reason may name an internal token; show the money instead.
            for global_token, value in tokens.items():
                reason = reason.replace(global_token, repr(value))
            current_app.logger.warning(
                f'{route} ({language_code}): string #{index} ({readable[:60]!r}) kept in '
                f'English — {reason}. Returned: {partial[index][:80]!r}'
            )
            kept_english.append((index, reason))
            localised[index] = segment['text']
            continue
        localised[index] = restored_text
    translations = localised

    too_many = max(MIN_STRINGS_BEFORE_DISCARD,
                   len(segments) * MAX_STRINGS_KEPT_IN_ENGLISH)
    if len(kept_english) > too_many:
        first_index, first_reason = kept_english[0]
        current_app.logger.warning(
            f'Translation discarded for {route} ({language_code}): '
            f'{len(kept_english)} of {len(segments)} strings failed validation — '
            f'systemic, not incidental.'
        )
        detail = (f'discarded: {len(kept_english)} of {len(segments)} strings failed '
                  f'(first #{first_index} — {first_reason})')
        if report.get('response_head'):
            detail += f' — model said: {report["response_head"][:120]}'
        report['detail'] = detail
        return None

    if kept_english:
        report['kept_english'] = len(kept_english)
        report['kept_english_detail'] = (
            '%d of %d strings kept in English (first #%d — %s)'
            % (len(kept_english), len(segments), kept_english[0][0], kept_english[0][1])
        )

    remaining = _budget_left(started)
    if want_review and len(masked_html) > REVIEW_MAX_CHARS:
        current_app.logger.info(
            f'Translation review skipped for {route} ({language_code}): page is '
            f'{len(masked_html):,} chars, over the {REVIEW_MAX_CHARS:,} the reviewer fits'
        )
    elif want_review and remaining < REVIEW_MIN_SECONDS:
        current_app.logger.info(
            f'Translation review skipped for {route} ({language_code}): '
            f'{remaining:.0f}s left of the {RESPONSE_BUDGET_SECONDS}s budget'
        )
    elif want_review:
        by_index = {s['index']: s for s in segments}
        accepted = {}
        for batch in batches:
            if _budget_left(started) < REVIEW_MIN_SECONDS:
                current_app.logger.info(
                    f'Translation review stopped early for {route} ({language_code}): '
                    f'budget spent'
                )
                break
            subset = {i: translations[i] for i in batch if i in translations}
            raw_review = _call_groq(
                _segment_review_prompt(marked, subset, language_name, batch, len(expected)),
                timeout=int(min(_timeout_for(marked), 120)),
                allow_retry=True,
                model=_review_model(),
                reasoning_effort=REVIEW_REASONING_EFFORT,
            )
            if not raw_review or raw_review.strip().upper().startswith(NO_CHANGES):
                continue
            # The reviewer returns only the lines it would change, so a partial
            # answer is the expected answer. Anything it does not mention keeps
            # the first pass's wording.
            corrections = parse_response(
                _strip_markdown_fences(raw_review), set(batch), require_all=False
            ) or {}
            for index, text in corrections.items():
                fixed = delocalise(by_index[index], text)
                # A correction that mangles a placeholder is simply not taken;
                # the first pass's wording for that string stands.
                if fixed is not None:
                    accepted[index] = fixed
        if accepted:
            translations = dict(translations)
            translations.update(accepted)
            current_app.logger.info(
                f'Translation review amended {len(accepted)} of {len(expected)} '
                f'strings on {route} ({language_code})'
            )

    candidate = reassemble(masked_html, segments, translations)

    restored = _restore_or_none(candidate, tokens, csrf_token, counts=counts, report=report)
    if restored is None:
        current_app.logger.warning(
            f'Translation discarded for {route} ({language_code}): '
            f'{report.get("detail", "validation failed")}'
        )
    return restored


def _translate_by_segments(masked_html, tokens, counts, csrf_token, language_name,
                           route, language_code, want_review, started, report=None):
    """Default mode: the model reads the whole page and returns only the words.

    The page is never handed back by the model and never rebuilt from anything
    it said. We hold the original, and substitute each translated string into
    the character span it came from. Markup, script and style are not merely
    protected -- they are never in the response at all.

    Tries twice. A dropped numbered line or a mangled placeholder is a coin
    flip rather than a property of the page: re-running a failed warm usually
    succeeds, which is evidence the failure is in the sampling and not in the
    input. A page that fails both attempts is saying something real, and the
    reported reason is the one from the last attempt.
    """
    segments = find_segments(masked_html)
    if not segments:
        current_app.logger.debug(f'Nothing translatable on {route}')
        if report is not None:
            report['detail'] = 'no translatable text on the page'
        return None

    localise(segments)
    marked = mark(masked_html, segments)
    expected = {s['index'] for s in segments}

    for attempt in range(1, MAX_TRANSLATION_ATTEMPTS + 1):
        attempt_report = {}
        restored = _segment_attempt(
            marked, masked_html, segments, expected, tokens, counts, csrf_token,
            language_name, route, language_code, want_review, started, attempt_report,
        )
        if restored is not None:
            if attempt > 1:
                current_app.logger.info(
                    f'Translation succeeded for {route} ({language_code}) on attempt {attempt}'
                )
            if report is not None and attempt_report.get('kept_english'):
                report['detail'] = attempt_report['kept_english_detail']
            return restored

        detail = attempt_report.get('detail', 'not translated')

        # Only a model-side slip earns a second coin flip. A missing key, a
        # retired model or an edge refusal will fail the same way instantly,
        # and retrying it just burns the budget.
        retryable = detail.startswith('discarded')
        budget = _budget_left(started)

        if attempt < MAX_TRANSLATION_ATTEMPTS and retryable and budget > RETRY_MIN_SECONDS:
            current_app.logger.info(
                f'Retrying {route} ({language_code}), attempt {attempt + 1} of '
                f'{MAX_TRANSLATION_ATTEMPTS}, after: {detail}'
            )
            continue

        if report is not None:
            if attempt > 1:
                report['detail'] = f'{detail} — failed {attempt} attempts'
            elif retryable and budget <= RETRY_MIN_SECONDS:
                report['detail'] = f'{detail} (no time left to retry)'
            else:
                report['detail'] = detail
        return None


def translate_response(html: str, language_code: str, route: str,
                       review: bool | None = None, report: dict | None = None) -> str:
    """
    Return the HTML translated to language_code, using the cache when available.
    Always returns valid HTML — falls back to the original English on any error,
    on any cache problem, and on any sign the model touched a masked value.

    The order of operations matters, and each step is load-bearing:

      1. Blank the CSRF token. It is a timed signature that changes every
         request, so it must be out of the page before the hash is taken
         (or the cache can never hit) and out of the stored row (or a hit
         would serve one member's token to another and break their POSTs).
      2. Hash the blanked page — that is the cache key.
      3. On a hit, re-inject *this* request's token and return.
      4. On a miss, mask every currency amount and account number, then
         translate. In the default 'segments' mode the model reads the whole
         page and returns only the words, numbered, and we substitute them into
         the original by character offset — the markup is never regenerated and
         never at risk. TRANSLATION_MODE=page restores the older behaviour of
         asking for the whole document back.
         Either way, restore the masked values afterwards; if a placeholder is
         missing, duplicated or invented, throw the translation away and serve
         English.
      5. Review the translation against an accounting rubric in a second call,
         and take the amended page only if it clears the same validation. A
         reviewer that answers badly costs the first-pass translation nothing.
         Pass review=False to skip it — cache warming trades it for wall-clock
         when there are more languages than there is time before a demo.
      6. Store the restored page with the CSRF placeholder still in it, and
         re-inject the live token on the way out.
    """
    if language_code not in SUPPORTED_LANGUAGES:
        return html

    # Checked here as well as in the request hook: this function is also called
    # directly by the cache warmer, and an exemption that only one caller
    # honours is not an exemption.
    if not is_translatable_route(route):
        current_app.logger.debug(f'Translation refused for exempt route {route}')
        if report is not None:
            report['detail'] = 'route is exempt from translation'
        return html

    mode = _translation_mode()
    limit = MAX_HTML_CHARS_SEGMENTS if mode == 'segments' else MAX_HTML_CHARS
    if len(html) > limit:
        current_app.logger.debug(
            f'Translation skipped for {route}: page too large '
            f'({len(html):,} chars, limit {limit:,} in {mode} mode)'
        )
        if report is not None:
            report['detail'] = f'page too large ({len(html):,} chars, limit {limit:,})'
        return html

    started = time.monotonic()

    # 1 & 2 — CSRF out, then key on what is left.
    blanked_html, csrf_token = extract_csrf(html)
    content_hash = _content_hash(blanked_html)

    # 3 — Cache hit?
    try:
        cached = TranslationCache.query.filter_by(
            route=route,
            language_code=language_code,
            content_hash=content_hash,
        ).first()
        if cached:
            return reinject_csrf(cached.translated_html, csrf_token)
    except Exception as exc:
        current_app.logger.warning(f'Translation cache read error: {exc}')

    # 4 & 5 — Cache miss. Mask the money, then hand off to the mode.
    masked_html, tokens, counts = mask_values(blanked_html)
    language_name = SUPPORTED_LANGUAGES[language_code]
    want_review = _review_enabled() if review is None else review

    translate = _translate_by_segments if mode == 'segments' else _translate_whole_page
    restored = translate(masked_html, tokens, counts, csrf_token, language_name,
                         route, language_code, want_review, started, report)
    if restored is None:
        return html

    # 6 — Store the page with the placeholder, serve it with the live token.
    try:
        db.session.execute(
            text(
                'INSERT INTO translation_cache (route, language_code, content_hash, translated_html, created_at) '
                'VALUES (:route, :lang, :hash, :html, NOW()) '
                'ON CONFLICT ON CONSTRAINT uq_translation_cache DO NOTHING'
            ),
            {'route': route, 'lang': language_code, 'hash': content_hash, 'html': restored}
        )
        db.session.commit()
    except Exception as exc:
        current_app.logger.warning(f'Translation cache write error: {exc}')
        db.session.rollback()

    return reinject_csrf(restored, csrf_token)

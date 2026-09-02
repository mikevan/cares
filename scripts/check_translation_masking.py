"""Pre-demo smoke test for the translation pipeline.

Two things fail silently in production and this script makes both visible:

  * The masking layer fails closed. If the model drops, renumbers or reformats
    a single placeholder, the whole page is discarded and the reader gets
    English. Correct, but silent.
  * The review pass is advisory. If the reviewer is useless it costs a second
    API call and changes nothing, and you would never know from the page.

Run it from a machine that can reach api.groq.com:

    python scripts/check_translation_masking.py            # Spanish, active mode
    python scripts/check_translation_masking.py es --both  # segment AND page mode
    python scripts/check_translation_masking.py es pl tl   # or pick languages
    python scripts/check_translation_masking.py --no-review

Reads GROQ_API_KEY (and optionally GROQ_TRANSLATION_MODEL) from the
environment or from a .env file in the repository root. Exits non-zero if any
language would be served untranslated.
"""

import json
import os
import sys

import requests as http_requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.translation_masking import (  # noqa: E402
    extract_csrf, mask_values, restore_values, csrf_placeholder_intact,
)
# Private on purpose -- this script deliberately exercises the exact prompts
# production sends, rather than a copy of them that can drift.
from services.translation_service import (  # noqa: E402
    DEFAULT_MODEL, GROQ_API_URL, NO_CHANGES, SUPPORTED_LANGUAGES, USER_AGENT,
    _review_prompt, _segment_review_prompt, _segment_translation_prompt,
    _translation_mode, _translation_prompt,
)
from services.translation_segments import (  # noqa: E402
    find_segments, mark, parse_response, reassemble,
)

# A page shaped like the ones that matter: account numbers, currency in three
# formats, a parenthesised negative, a proper noun, a council number that looks
# exactly like a GL account, and a cluster of terms that are ambiguous outside
# an accounting context -- balance, entry, post, statement, fund, dues.
SAMPLE_PAGE = '''<meta name="csrf-token" content="IjEyMyI.aBcDeF.signature">
<h1>Statement of Activities</h1>
<p>Bishop Kelley Council 1234, period ending 2026-06-30.</p>
<table>
<tr><th>Account</th><th>Description</th><th>Amount</th></tr>
<tr><td>4110</td><td>Dues Revenue</td><td>$1,584.00</td></tr>
<tr><td>4210</td><td>Fundraising Receipts</td><td>$2,340.15</td></tr>
<tr><td>5810</td><td>Charitable Disbursements</td><td>($975.50)</td></tr>
<tr><td colspan="2">Net change in assets</td><td>2,948.65</td></tr>
</table>
<p>Closing balance carried to the general fund. Post the entry to the ledger.</p>
<p>Prepared by the Financial Secretary. Reviewed by the Trustees.</p>'''


def _load_api_key():
    key = os.environ.get('GROQ_API_KEY')
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    try:
        with open(env_path, encoding='utf-8-sig') as handle:
            for line in handle:
                if line.strip().startswith('GROQ_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def _post(prompt, api_key, model):
    """Deliberately uses `requests`, with the same headers as the application.

    An earlier version called urllib, which meant the check exercised a
    different HTTP client from the one production uses -- and got banned by
    Cloudflare on its user agent while the app itself was fine. A pre-flight
    check that does not make the same call the app makes is not a check.
    """
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
            'max_tokens': 8192,
        },
        timeout=45,
    )
    if resp.status_code != 200:
        hint = ''
        if resp.status_code == 403 and 'error code: 1010' in (resp.text or ''):
            hint = ('  <- Cloudflare banned the client signature. Not the API key: '
                    'check the User-Agent and any TLS-inspecting proxy.')
        raise RuntimeError('HTTP %s -- %s%s' % (resp.status_code, (resp.text or '')[:400], hint))
    content = resp.json()['choices'][0]['message']['content']
    if content.startswith('```'):
        lines = content.split('\n')
        end = -1 if lines[-1].strip() == '```' else len(lines)
        content = '\n'.join(lines[1:end])
    return content


def check_segment_mode(code, api_key, model, with_review):
    """Exercise the DEFAULT path: whole page in, numbered strings out.

    This is what production runs, and it is the newest part of the pipeline, so
    it is the one most worth proving against the live model before a warm run
    rather than during one.
    """
    language_name = SUPPORTED_LANGUAGES[code]
    blanked, csrf_token = extract_csrf(SAMPLE_PAGE)
    masked, tokens, counts = mask_values(blanked)
    segments = find_segments(masked)
    marked = mark(masked, segments)
    expected = {s['index'] for s in segments}

    try:
        raw = _post(_segment_translation_prompt(marked, language_name), api_key, model)
    except Exception as exc:
        print(f'  {code} [segments]: API CALL FAILED - {exc!r}')
        return False

    translations = parse_response(raw, expected)
    if translations is None:
        usable = len([ln for ln in raw.splitlines() if ln.strip()])
        print(f'  {code} [segments]: DISCARDED - expected {len(expected)} numbered '
              f'strings, response had {usable} non-empty lines')
        return False

    if with_review:
        try:
            review = _post(_segment_review_prompt(marked, translations, language_name),
                           api_key, model)
        except Exception as exc:
            print(f'  {code} [segments]: review call failed ({exc!r}) - first pass stands')
            review = NO_CHANGES
        if review.strip().upper().startswith(NO_CHANGES):
            print(f'  {code} [segments]: review found nothing to correct')
        else:
            corrections = parse_response(review, expected, require_all=False) or {}
            print(f'  {code} [segments]: review amended {len(corrections)} '
                  f'of {len(expected)} strings')
            translations.update(corrections)

    page = reassemble(masked, segments, translations)
    if not csrf_placeholder_intact(page, csrf_token):
        print(f'  {code} [segments]: DISCARDED - CSRF placeholder lost')
        return False
    if restore_values(page, tokens, counts) is None:
        print(f'  {code} [segments]: DISCARDED - a masked value was altered')
        return False

    print(f'  {code} [segments]: ok - {len(expected)} strings translated, '
          f'{len(tokens)} masked values intact, markup untouched')
    return True


def check_language(code, api_key, model, with_review):
    language_name = SUPPORTED_LANGUAGES[code]
    blanked, csrf_token = extract_csrf(SAMPLE_PAGE)
    masked, tokens, counts = mask_values(blanked)

    try:
        translated = _post(_translation_prompt(masked, language_name), api_key, model)
    except Exception as exc:
        print(f'  {code} [page]: API CALL FAILED - {exc!r}')
        return False

    if not csrf_placeholder_intact(translated, csrf_token):
        print(f'  {code} [page]: DISCARDED - CSRF placeholder lost')
        return False
    if restore_values(translated, tokens, counts) is None:
        print(f'  {code} [page]: DISCARDED - model altered a masked value '
              f'({len(tokens)} placeholders sent)')
        return False

    print(f'  {code} [page]: translation ok - {len(tokens)} placeholders returned intact')

    if not with_review:
        return True

    try:
        reviewed = _post(_review_prompt(masked, translated, language_name), api_key, model)
    except Exception as exc:
        print(f'  {code}: review call failed ({exc!r}) - first pass would be served')
        return True

    if reviewed.strip().upper().startswith(NO_CHANGES):
        print(f'  {code}: review found nothing to correct')
        return True
    if '<' not in reviewed:
        print(f'  {code}: review answered in prose, not HTML - first pass would be served')
        return True
    if csrf_placeholder_intact(reviewed, csrf_token) and restore_values(reviewed, tokens, counts) is not None:
        changed = sum(1 for a, b in zip(translated.split(), reviewed.split()) if a != b)
        print(f'  {code}: review amended the page (~{changed} tokens differ) and validated')
    else:
        print(f'  {code}: review output REJECTED by validation - first pass would be served')
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    with_review = '--no-review' not in sys.argv

    api_key = _load_api_key()
    if not api_key:
        sys.exit('GROQ_API_KEY is not set and no .env file provides one.')

    model = os.environ.get('GROQ_TRANSLATION_MODEL', DEFAULT_MODEL)
    languages = args or ['es']

    unknown = [c for c in languages if c not in SUPPORTED_LANGUAGES]
    if unknown:
        sys.exit(f'Unsupported language code(s): {", ".join(unknown)}. '
                 f'Known: {", ".join(sorted(SUPPORTED_LANGUAGES))}')

    which = 'both' if '--both' in sys.argv else _translation_mode()
    print(f'Model: {model}   Review: {"on" if with_review else "off"}   Mode: {which}')

    results = []
    for code in languages:
        if which in ('segments', 'both'):
            results.append(check_segment_mode(code, api_key, model, with_review))
        if which in ('page', 'both'):
            results.append(check_language(code, api_key, model, with_review))

    if not all(results):
        print('\nAt least one language would be served untranslated. That is the '
              'designed failure, not a crash -- but if you were expecting a '
              'translated demo, try another model via GROQ_TRANSLATION_MODEL.')
        sys.exit(1)

    print('\nAll checked languages round-tripped cleanly.')


if __name__ == '__main__':
    main()

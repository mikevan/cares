"""
Value masking for the translation pipeline.

The translator used to be trusted with the numbers. It should not be: the
prompt asked the model to preserve currency amounts and account numbers, and
in testing every candidate model did -- but an instruction is not a guarantee,
and on a page a trustee signs, a moved decimal point is worse than an
untranslated page.

So the values never leave the building. Every currency amount and every GL
account number is replaced with an opaque placeholder before the API call and
put back verbatim afterwards. If a single placeholder is missing from the
model's response, or comes back more than once, the whole translation is
discarded and the caller serves the original English page.

The failure mode is English. It is never plausible-looking wrong money.

This module deliberately imports nothing from Flask or the models, so it can be
unit-tested on its own and reasoned about without an application context.
"""

import re

# ---------------------------------------------------------------------------
# Placeholders
# ---------------------------------------------------------------------------
# Shaped like a code identifier so a translation model leaves it alone. The
# digits are always preceded by a word character, which keeps _ACCOUNT_RE from
# matching inside a placeholder we just emitted.
_TOKEN_TEMPLATE = '__CARES_V{:04d}__'
_TOKEN_RE = re.compile(r'__CARES_V\d{4}__')

# The CSRF token is masked too, but for a different reason -- see
# translation_service.translate_response. It is a single fixed placeholder
# because there is exactly one per page and the value that goes back in is the
# *current* request's token, not the one that came out.
CSRF_PLACEHOLDER = '__CARES_CSRF_TOKEN__'

CSRF_META_RE = re.compile(
    r'(<meta\s+name=["\']csrf-token["\']\s+content=["\'])([^"\']*)(["\'])',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# What gets masked
# ---------------------------------------------------------------------------
# Script and style bodies are handed to the model untouched and are excluded
# from masking: they contain no reader-facing money, and rewriting them risks
# breaking JavaScript string literals.
_SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1\s*>', re.IGNORECASE | re.DOTALL)

# Currency, in the shapes this application actually renders:
#   $1,234.56   $ 1234    -$45.00    ($1,234.56)    1,584.00
# The last form -- a bare decimal amount with exactly two places -- is how the
# financial statements and Form 1295 schedules print money inside a column that
# already carries the dollar sign in its header.
# \d+ rather than \d{1,3} on the leading run: templates that hand a raw
# Decimal to the page print 1584.00, with no thousands separator, and a
# {1,3} bound would match only '$158' and leave '4.00' behind.
_CURRENCY_RE = re.compile(
    r'-?\$\s?-?\d+(?:,\d{3})*(?:\.\d{1,2})?'
    r'|(?<![\w.])\d+(?:,\d{3})*\.\d{2}(?![\w.])'
)

# Bare four-digit numbers are NO LONGER MASKED, and that reversal was earned.
#
# The rule used to be "currency plus GL account numbers". It also caught 2026,
# 1099 and 1295, and the first real warm run failed on exactly those strings:
# 'Annual Dues Roster 2026 - CARES', '1099 Report', '3100: Unrestricted'. In a
# two-word label the placeholder is half the content, and the model drops it.
# The masking was manufacturing the failures it existed to prevent.
#
# What makes dropping it safe: an account number in its own cell --
# <td>4110</td>, which is how the Chart of Accounts and every report render
# them -- has no letters, so segmentation never sends it to the model at all.
# The only four-digit numbers that reach the API are the ones inside labels,
# and those are protected by verification instead: the digits in a translated
# string must match the digits in the source (translation_segments.
# numeric_signature). A model that renumbers an account is caught, without a
# placeholder for it to lose.
#
# Currency is still masked and still never sent. A moved decimal point leaves
# the digits identical, which is exactly what verification cannot catch and
# exactly why masking exists.


def _mask_segment(segment: str, tokens: dict, seen: dict) -> str:
    """Mask one run of markup that is not inside <script> or <style>.

    Identical values share a placeholder. Form 1295 renders dozens of `$0`
    lines; giving each its own token produced dozens of placeholders differing
    only by a four-digit number, all standing for the same three characters,
    and the model transposed two of them -- one came back twice, its neighbour
    not at all, and the page was discarded. Telling apart placeholders that
    mean the same value buys nothing and costs exactly that.
    """

    def _replace(match):
        value = match.group(0)
        if value in seen:
            return seen[value]
        token = _TOKEN_TEMPLATE.format(len(tokens))
        tokens[token] = value
        seen[value] = token
        return token

    return _CURRENCY_RE.sub(_replace, segment)


def mask_values(html: str) -> tuple:
    """Replace every financial value with a placeholder.

    Returns (masked_html, tokens, counts):
      tokens  placeholder -> the exact original text it stands for
      counts  placeholder -> how many times it appears in the masked page

    One placeholder per distinct value, not per occurrence. `counts` is what
    makes that safe: a value appearing four times must come back four times,
    so a dropped or duplicated placeholder is still caught.
    """
    tokens: dict = {}
    seen: dict = {}
    out = []
    pos = 0

    for match in _SCRIPT_STYLE_RE.finditer(html):
        out.append(_mask_segment(html[pos:match.start()], tokens, seen))
        out.append(match.group(0))          # script/style body, untouched
        pos = match.end()

    out.append(_mask_segment(html[pos:], tokens, seen))

    masked = ''.join(out)
    counts = {token: masked.count(token) for token in tokens}
    return masked, tokens, counts


def restore_values(html: str, tokens: dict, counts: dict | None = None,
                   report: dict | None = None):
    """Put the original values back, or return None if the response is not trustworthy.

    None means: discard this translation entirely. A placeholder the model
    dropped, duplicated, or invented is evidence that it edited the parts of
    the page it was told not to touch, and nothing else it returned can be
    relied on either.
    """
    for token, original in tokens.items():
        expected = 1 if counts is None else counts.get(token, 1)
        seen = html.count(token)
        if seen != expected:
            # Name the value, not just the failure. 'the placeholder standing
            # for ($975.50) came back twice' points at a pattern; 'a masked
            # value was altered' points at nothing.
            if report is not None:
                report['detail'] = (
                    'discarded: the placeholder for %r came back %s, expected %d'
                    % (original,
                       'missing' if seen == 0 else '%d times' % seen,
                       expected)
                )
            return None
        html = html.replace(token, original)

    # Anything still matching the placeholder shape is one the model invented.
    stray = _TOKEN_RE.search(html)
    if stray:
        if report is not None:
            report['detail'] = ('discarded: the model invented a placeholder (%s) that '
                                'was never sent' % stray.group(0))
        return None

    return html


# ---------------------------------------------------------------------------
# CSRF token
# ---------------------------------------------------------------------------

def extract_csrf(html: str) -> tuple:
    """Swap the CSRF meta value for a fixed placeholder.

    Returns (html_with_placeholder, original_token_or_None). The token is an
    itsdangerous *timed* signature, so it differs on every single request --
    which is why hashing the page with it still in place gave the cache a key
    that could never repeat, and why storing it would hand one member's token
    to the next.
    """
    token = None

    def _replace(match):
        nonlocal token
        token = match.group(2)
        return match.group(1) + CSRF_PLACEHOLDER + match.group(3)

    return CSRF_META_RE.sub(_replace, html, count=1), token


def reinject_csrf(html: str, token) -> str:
    """Put this request's CSRF token into the placeholder."""
    if token is None:
        return html
    return html.replace(CSRF_PLACEHOLDER, token)


def csrf_placeholder_intact(html: str, token) -> bool:
    """True if the page still has exactly one slot for the CSRF token.

    A page that lost its placeholder in translation would render without a
    usable csrf-token meta tag, and base.html's form handler would then submit
    every POST without a token -- so this is a discard condition too.
    """
    if token is None:
        return True
    return html.count(CSRF_PLACEHOLDER) == 1

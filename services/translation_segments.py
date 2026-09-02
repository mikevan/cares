"""
Indexed-segment translation.

The model has to *read* the whole page and only *write* the words.

Sending a rendered page and asking for the rendered page back means the model
regenerates every tag, every CSS class, every href and the entire contents of
each <script> and <style> block -- verbatim, unchanged, at token cost, with a
chance of corrupting something on each one. Output is also the scarce
resource: the ceiling on a completion is a fraction of the context window, so
the document we can translate is limited by how much markup the model can
retype rather than by how much text there is to translate.

So: mark each translatable string in place with [[Sn]], send the complete
document exactly as it renders, and ask for nothing back but numbered lines.

    1: Estado de Actividades
    2: Ingresos por Cuotas

The page never leaves our hands. We hold the original and substitute each
string in place, by recorded character offset. The model cannot break a tag it
never emits, cannot reorder a table, and cannot touch a <script> block -- not
because it was told not to, but because it has no way to.

Context is untouched by any of this. The model still sees the whole page: the
table a cell sits in, the column it falls under, the statement it belongs to.
That context is the reason 'Balance' resolves to a ledger balance rather than
to equilibrium, and it is exactly what a string-extraction approach would
throw away.

Like everything else in this pipeline, it fails closed: if a single numbered
string is missing from the response, the whole translation is discarded and
the reader gets English.
"""

import re

MARKER_TEMPLATE = '[[S{}]]'
MARKER_RE = re.compile(r'\[\[S\d+\]\]')

# Masked financial values, as they appear globally across the page.
GLOBAL_VALUE_RE = re.compile(r'__CARES_V\d{4}__')

# The same values, renumbered from 1 inside each translatable string.
#
# Global placeholders were the wrong scope. A Form 1295 page carries dozens of
# them differing only by a four-digit counter, and the model transposed two --
# one came back twice, its neighbour not at all, and the page was discarded on
# every attempt. Nothing about the task requires a placeholder to be unique
# across the page: it only has to be unique within the line it sits on, which
# is the only place the model ever handles it.
#
# So each string gets [[V1]], [[V2]] of its own. Most strings have one. A token
# borrowed from another line is not in this line's map and fails immediately,
# instead of silently corrupting a value somewhere else on the page.
LOCAL_VALUE_TEMPLATE = '[[V{}]]'
LOCAL_VALUE_RE = re.compile(r'\[\[V\d+\]\]')

# Bodies whose text is never translated and never marked.
_SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1\s*>', re.IGNORECASE | re.DOTALL)

# Text between tags. The pattern cannot match inside a tag, because a tag
# contains no '>' until it ends -- and rendered pages carry no '>' inside
# attribute values (the ones in the templates live in Jinja expressions, which
# are gone by the time this sees the page).
_TEXT_NODE_RE = re.compile(r'>([^<]*)<')

# Attributes a reader actually sees.
_ATTR_RE = re.compile(r'\b(title|placeholder|aria-label|alt)="([^"]*)"', re.IGNORECASE)


def _is_translatable(text: str) -> bool:
    """Worth sending? Only strings with letters in them.

    Skips whitespace, punctuation, bare numbers, and text that is nothing but a
    masked currency placeholder -- there is no language in any of it, and every
    skipped string is one less thing the model can get wrong.
    """
    stripped = MARKER_RE.sub('', text)
    # A masked value is __CARES_V0000__ -- letters, but not words. Strip the
    # placeholders before asking whether anything linguistic is left.
    stripped = re.sub(r'__CARES_V\d{4}__|__CARES_CSRF_TOKEN__', '', stripped)
    return any(ch.isalpha() for ch in stripped)


def _protected_spans(html: str) -> list:
    return [(m.start(), m.end()) for m in _SCRIPT_STYLE_RE.finditer(html)]


def _inside(span, protected) -> bool:
    return any(start < span[0] < end or start < span[1] < end for start, end in protected)


def find_segments(html: str) -> list:
    """Every translatable string in the page, with its exact character span.

    Returns a list of {'index', 'text', 'start', 'end'}, ordered by position.
    Spans point into the HTML passed in, and nothing else is ever used to put
    the translations back.
    """
    protected = _protected_spans(html)
    found = []

    for match in _TEXT_NODE_RE.finditer(html):
        start, end = match.start(1), match.end(1)
        raw = match.group(1)
        if not raw.strip() or not _is_translatable(raw):
            continue
        # Keep surrounding whitespace out of the segment so indentation and
        # line breaks in the markup survive untouched.
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        span = (start + lead, end - trail)
        if _inside(span, protected):
            continue
        found.append({'text': html[span[0]:span[1]], 'start': span[0], 'end': span[1]})

    for match in _ATTR_RE.finditer(html):
        start, end = match.start(2), match.end(2)
        if not match.group(2).strip() or not _is_translatable(match.group(2)):
            continue
        if _inside((start, end), protected):
            continue
        found.append({'text': match.group(2), 'start': start, 'end': end})

    found.sort(key=lambda s: s['start'])
    for i, segment in enumerate(found, start=1):
        segment['index'] = i
    return found


def localise(segments: list) -> list:
    """Renumber each string's masked values from 1, local to that string.

    Fills in, on every segment:
      'sent'         the text as the model will see it
      'locals'       {'[[V1]]': '__CARES_V0042__', ...}
      'local_counts' how many times each local token occurs in that string
    """
    for segment in segments:
        mapping, counts, assigned = {}, {}, {}

        def _replace(match, mapping=mapping, counts=counts, assigned=assigned):
            global_token = match.group(0)
            if global_token not in assigned:
                local = LOCAL_VALUE_TEMPLATE.format(len(assigned) + 1)
                assigned[global_token] = local
                mapping[local] = global_token
            local = assigned[global_token]
            counts[local] = counts.get(local, 0) + 1
            return local

        segment['sent'] = GLOBAL_VALUE_RE.sub(_replace, segment['text'])
        segment['locals'] = mapping
        segment['local_counts'] = counts

    return segments


# HTML character references carry digits that are not numbers: a roster cell
# renders "Michael O&#39;Brien", and a scanner counting digit runs reads 39 out
# of the apostrophe. The model returns "Michael O'Brien", correctly, and the
# comparison then rejects a flawless translation for losing a number that was
# never on the page. Entities come out before any digit is counted.
_ENTITY_RE = re.compile(r'&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]{1,31});')

# Translations are plain text. A response containing a tag means the model ran
# past the end of the string and swept up the markup that followed it -- which
# is how '<strong>FASB ASC 958</strong>' arrived inside a sentence that ended
# at 'in compliance with '.
_TAGGISH_RE = re.compile(r'</?[A-Za-z][^>]*>')


def numeric_signature(text: str) -> list:
    """Every run of digits in a string, ignoring our own markers and placeholders.

    Numbers that are not currency are sent to the model as themselves -- an
    account number inside a label like '3100: Unrestricted', a form number in
    '1099 Report', a year in 'Annual Dues Roster 2026'. Masking them turned
    short labels into mostly-placeholder and the model dropped them, so they
    are protected by checking instead: the digits that come back must be the
    digits that went out, in the same quantities.

    This does not replace masking for money. A moved decimal point leaves the
    digits identical, which is precisely why currency never leaves the building.
    """
    bare = LOCAL_VALUE_RE.sub('', MARKER_RE.sub('', text))
    bare = _ENTITY_RE.sub(' ', bare)
    return sorted(re.findall(r'\d+', bare))


# Chart-of-accounts and account dropdowns render "1420 - Furniture & Fixtures".
# The model reliably translates the label and drops the code, because the code
# is not language. Seventy strings on one page came back that way.
#
# The code is the page's own text, so it is restored rather than argued about.
# Only when doing so makes the numbers match exactly is the repair accepted --
# it can rescue a dropped prefix, never invent or move a number.
_LEADING_CODE_RE = re.compile(r'^\s*(\d[\w.]*)\s*[-\u2013\u2014:]\s+')


def _repair_leading_code(source: str, translated: str) -> str:
    """Put back an identifier the model dropped from the front of a string."""
    match = _LEADING_CODE_RE.match(source)
    if not match:
        return translated
    if match.group(1) in translated or _LEADING_CODE_RE.match(translated):
        return translated
    return match.group(0) + translated.lstrip()


def delocalise(segment: dict, translated: str, report: dict | None = None):
    """Put this string's global placeholders back, or None if it is untrustworthy.

    Two independent rejection reasons, and they are NOT the same problem:

      * a masked currency placeholder that went missing, was repeated, or came
        from a different string
      * an unmasked number -- an account number, a form number, a year -- that
        changed, vanished or appeared

    Reporting both as "lost a value placeholder" sent the last investigation
    down the wrong path entirely, so each one now says what it actually is.
    """
    def _note(detail):
        if report is not None:
            report['detail'] = detail

    if _TAGGISH_RE.search(translated):
        _note('it returned HTML markup, not just this string\'s text — '
              'the model ran past the end of the string')
        return None

    for local, expected in segment.get('local_counts', {}).items():
        seen = translated.count(local)
        if seen != expected:
            _note('the masked amount %s came back %s'
                  % (segment['locals'][local],
                     'missing' if seen == 0 else '%d times, expected %d' % (seen, expected)))
            return None

    for found in LOCAL_VALUE_RE.finditer(translated):
        if found.group(0) not in segment.get('locals', {}):
            _note('it used %s, which belongs to a different string' % found.group(0))
            return None

    # Unmasked numbers -- account numbers, form numbers, years -- must survive
    # the round trip exactly. This is the guard that replaced masking them.
    sent_numbers = numeric_signature(segment.get('sent', ''))
    back_numbers = numeric_signature(translated)

    if back_numbers != sent_numbers:
        repaired = _repair_leading_code(segment.get('sent', ''), translated)
        if repaired is not translated and numeric_signature(repaired) == sent_numbers:
            translated = repaired
            back_numbers = sent_numbers

    if back_numbers != sent_numbers:
        _note('the numbers changed: sent %s, got %s'
              % (sent_numbers or 'none', back_numbers or 'none'))
        return None

    out = translated
    for local, global_token in segment.get('locals', {}).items():
        out = out.replace(local, global_token)
    return out


def mark(html: str, segments: list) -> str:
    """Return the copy sent to the model: [[Sn]] before each string, values localised.

    Only this copy is marked. The page we substitute back into is never
    modified.
    """
    if segments and 'sent' not in segments[0]:
        localise(segments)

    out = html
    for segment in reversed(segments):
        marker = MARKER_TEMPLATE.format(segment['index'])
        body = segment.get('sent', segment['text'])
        out = out[:segment['start']] + marker + body + out[segment['end']:]
    return out


def parse_response(text: str, expected: set, require_all: bool = True):
    """Turn 'n: translation' lines into {index: text}, or None if it is unusable.

    Forgiving about what it ignores -- an unknown index, a preamble line, a
    stray blank -- and strict about what it requires: every expected index must
    be present. Missing one means discarding the page, which is the whole
    contract.
    """
    if not text:
        return None

    line_re = re.compile(r'^\s*(\d+)\s*[:.\)]\s?(.*)$')
    parsed, current, extras = {}, None, 0

    for line in text.splitlines():
        match = line_re.match(line)
        if match:
            index = int(match.group(1))
            if index in expected:
                current = index
                parsed[index] = match.group(2)
            else:
                current = None
                extras += 1
        elif current is not None and line.strip():
            # A translation that wrapped onto another line.
            parsed[current] += '\n' + line

    if not parsed:
        return {} if not require_all else None

    if require_all and (expected - set(parsed)):
        return None

    # Models sometimes echo the marker back inside the translation.
    return {i: MARKER_RE.sub('', t).strip() for i, t in parsed.items()}


def reassemble(html: str, segments: list, translations: dict) -> str:
    """Substitute each translated string into the original page, by offset.

    Walks backwards so that every span stays valid as earlier text changes
    length. Everything that is not a recorded segment -- all markup, all
    script, all style -- comes through byte for byte, because it is never
    touched.
    """
    out = html
    for segment in reversed(segments):
        replacement = translations.get(segment['index'])
        if replacement is None:
            continue
        out = out[:segment['start']] + replacement + out[segment['end']:]
    return out

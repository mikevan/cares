"""Unit tests for indexed-segment translation.

No Flask, no database, no network: these exercise
services/translation_segments.py directly, simulating the model's reply.
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from services.translation_segments import (  # noqa: E402
    find_segments, mark, parse_response, reassemble,
)

PAGE = (
    '<div class="card">'
    '<h1>Statement of Activities</h1>'
    '<table title="Ledger detail">'
    '<tr><td>4110</td><td>Dues Revenue</td><td class="text-end">$1,584.00</td></tr>'
    '</table>'
    '<input placeholder="Search members">'
    '<style>.x{content:"Total"}</style>'
    '<script>var label = "Dues Revenue"; var n = 1584;</script>'
    '</div>'
)


def _tags(html):
    """The markup skeleton: every tag, with translatable attribute values blanked.

    title=, placeholder=, alt= and aria-label= are content, not structure — they
    are supposed to change. Everything else about a tag is not.
    """
    tags = re.findall(r'<[^>]+>', html)
    return [re.sub(r'\b(title|placeholder|aria-label|alt)="[^"]*"', r'\1=""', t)
            for t in tags]


def _translate_all(segments, fn=lambda s: '[' + s + ']'):
    return {s['index']: fn(s['text']) for s in segments}


# ---------------------------------------------------------------------------
# Finding segments
# ---------------------------------------------------------------------------

def test_finds_visible_text():
    texts = [s['text'] for s in find_segments(PAGE)]
    assert 'Statement of Activities' in texts
    assert 'Dues Revenue' in texts


def test_finds_translatable_attributes():
    texts = [s['text'] for s in find_segments(PAGE)]
    assert 'Ledger detail' in texts       # title=
    assert 'Search members' in texts      # placeholder=


def test_skips_script_and_style_contents():
    texts = [s['text'] for s in find_segments(PAGE)]
    assert not any('var label' in t for t in texts)
    assert not any('content:' in t for t in texts)
    assert 'Total' not in texts


def test_skips_strings_with_no_letters():
    texts = [s['text'] for s in find_segments(PAGE)]
    assert '4110' not in texts
    assert '$1,584.00' not in texts


def test_skips_a_string_that_is_only_a_masked_value():
    segments = find_segments('<td>__CARES_V0007__</td>')
    assert segments == []


def test_indexes_are_sequential_and_in_document_order():
    segments = find_segments(PAGE)
    assert [s['index'] for s in segments] == list(range(1, len(segments) + 1))
    assert all(a['start'] < b['start'] for a, b in zip(segments, segments[1:]))


def test_whitespace_is_not_part_of_a_segment():
    segments = find_segments('<p>\n   Dues Revenue\n</p>')
    assert [s['text'] for s in segments] == ['Dues Revenue']


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------

def test_marking_leaves_the_original_untouched():
    segments = find_segments(PAGE)
    marked = mark(PAGE, segments)
    assert '[[S1]]' in marked
    assert '[[S' not in PAGE


def test_every_segment_gets_exactly_one_marker():
    segments = find_segments(PAGE)
    marked = mark(PAGE, segments)
    for s in segments:
        assert marked.count('[[S%d]]' % s['index']) == 1


# ---------------------------------------------------------------------------
# Reassembly — the markup must survive byte for byte
# ---------------------------------------------------------------------------

def test_markup_is_identical_after_reassembly():
    segments = find_segments(PAGE)
    out = reassemble(PAGE, segments, _translate_all(segments))
    assert _tags(out) == _tags(PAGE)


def test_script_and_style_survive_untouched():
    segments = find_segments(PAGE)
    out = reassemble(PAGE, segments, _translate_all(segments))
    assert '<script>var label = "Dues Revenue"; var n = 1584;</script>' in out
    assert '<style>.x{content:"Total"}</style>' in out


def test_numbers_and_currency_survive_untouched():
    segments = find_segments(PAGE)
    out = reassemble(PAGE, segments, _translate_all(segments))
    assert '<td>4110</td>' in out
    assert '$1,584.00' in out


def test_text_is_actually_replaced():
    segments = find_segments(PAGE)
    out = reassemble(PAGE, segments, _translate_all(segments))
    assert '[Statement of Activities]' in out
    assert '>Statement of Activities<' not in out


def test_replacement_of_different_length_keeps_later_segments_correct():
    segments = find_segments(PAGE)
    long_text = {s['index']: 'X' * 200 for s in segments}
    out = reassemble(PAGE, segments, long_text)
    assert _tags(out) == _tags(PAGE)
    assert out.count('X' * 200) == len(segments)


def test_identity_translation_reproduces_the_page_exactly():
    segments = find_segments(PAGE)
    same = {s['index']: s['text'] for s in segments}
    assert reassemble(PAGE, segments, same) == PAGE


def test_masked_value_inside_a_translated_string_survives():
    page = '<p>Total collected: __CARES_V0003__ this year</p>'
    segments = find_segments(page)
    out = reassemble(page, segments,
                     {segments[0]['index']: 'Total recaudado: __CARES_V0003__ este ano'})
    assert '__CARES_V0003__' in out


# ---------------------------------------------------------------------------
# Parsing the model's reply — forgiving about noise, strict about omissions
# ---------------------------------------------------------------------------

def test_parses_numbered_lines():
    assert parse_response('1: Uno\n2: Dos', {1, 2}) == {1: 'Uno', 2: 'Dos'}


def test_missing_line_discards_everything():
    assert parse_response('1: Uno', {1, 2}) is None


def test_unknown_index_is_ignored_not_fatal():
    assert parse_response('1: Uno\n2: Dos\n99: Ruido', {1, 2}) == {1: 'Uno', 2: 'Dos'}


def test_preamble_is_ignored():
    assert parse_response('Here are the translations:\n1: Uno\n2: Dos', {1, 2}) \
        == {1: 'Uno', 2: 'Dos'}


def test_wrapped_translation_is_joined():
    out = parse_response('1: first line\ncontinued\n2: Dos', {1, 2})
    assert out[1] == 'first line\ncontinued'


def test_echoed_marker_is_stripped():
    assert parse_response('1: [[S1]]Uno', {1}) == {1: 'Uno'}


def test_empty_reply_discards():
    assert parse_response('', {1}) is None
    assert parse_response('I could not do that.', {1}) is None


def test_review_corrections_may_be_partial():
    assert parse_response('2: Mejor', {1, 2}, require_all=False) == {2: 'Mejor'}
    assert parse_response('nothing here', {1, 2}, require_all=False) == {}


# ---------------------------------------------------------------------------
# Values are numbered per string, not per page
# ---------------------------------------------------------------------------

from services.translation_masking import mask_values  # noqa: E402
from services.translation_segments import (  # noqa: E402
    delocalise, localise, LOCAL_VALUE_RE,
)

FORM_1295_ISH = (
    '<tr><td>Miscellaneous income</td><td>$0</td></tr>'
    '<tr><td>Total receipts $0 for the period</td></tr>'
    '<tr><td>Total disbursements $0 for the period</td></tr>'
)


def _prepared(html):
    masked, tokens, counts = mask_values(html)
    segments = localise(find_segments(masked))
    return masked, tokens, counts, segments


def test_each_string_numbers_its_values_from_one():
    _, _, _, segments = _prepared(FORM_1295_ISH)
    withvals = [s for s in segments if s['locals']]
    assert withvals, 'expected strings containing masked values'
    for segment in withvals:
        assert list(segment['locals']) == ['[[V%d]]' % i
                                           for i in range(1, len(segment['locals']) + 1)]


def test_the_page_sent_carries_no_global_placeholders_inside_strings():
    masked, _, _, segments = _prepared(FORM_1295_ISH)
    for segment in segments:
        assert '__CARES_V' not in segment['sent']


def test_marked_page_contains_the_localised_text():
    masked, _, _, segments = _prepared(FORM_1295_ISH)
    marked = mark(masked, segments)
    assert '[[V1]]' in marked
    assert '[[S1]]' in marked


def test_delocalise_restores_the_global_placeholder():
    _, _, _, segments = _prepared(FORM_1295_ISH)
    segment = next(s for s in segments if s['locals'])
    out = delocalise(segment, 'Recibos totales [[V1]] del periodo')
    assert out is not None
    assert '__CARES_V' in out
    assert not LOCAL_VALUE_RE.search(out)


def test_a_value_borrowed_from_another_string_is_rejected():
    """The exact Form 1295 failure: a placeholder that belongs to another line."""
    _, _, _, segments = _prepared(FORM_1295_ISH)
    segment = next(s for s in segments if s['locals'])
    assert delocalise(segment, 'Recibos totales [[V2]] del periodo') is None


def test_a_dropped_value_is_rejected():
    _, _, _, segments = _prepared(FORM_1295_ISH)
    segment = next(s for s in segments if s['locals'])
    assert delocalise(segment, 'Recibos totales del periodo') is None


def test_a_duplicated_value_is_rejected():
    _, _, _, segments = _prepared(FORM_1295_ISH)
    segment = next(s for s in segments if s['locals'])
    assert delocalise(segment, 'Totales [[V1]] y [[V1]]') is None


def test_repeated_identical_amounts_round_trip_across_the_whole_page():
    """Three strings each holding $0 — the shape that failed twice in a row."""
    from services.translation_masking import restore_values
    masked, tokens, counts, segments = _prepared(FORM_1295_ISH)
    translated = {s['index']: delocalise(s, s['sent']) for s in segments}
    page = reassemble(masked, segments, translated)
    assert restore_values(page, tokens, counts) == FORM_1295_ISH


# ---------------------------------------------------------------------------
# Unmasked numbers are verified rather than masked
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from services.translation_segments import numeric_signature  # noqa: E402


def _one_segment(label):
    masked, _, _ = mask_values('<h1>%s</h1>' % label)
    return localise(find_segments(masked))[0]


@pytest.mark.parametrize('label,translated', [
    ('1099 Report', 'Informe 1099'),
    ('3100: Unrestricted', '3100: Sin restricciones'),
    ('Annual Dues Roster 2026', 'Registro de Cuotas 2026'),
    ('Form 1295 Schedules A, B and C', 'Anexos A, B y C del Formulario 1295'),
])
def test_a_faithful_translation_keeps_its_numbers(label, translated):
    assert delocalise(_one_segment(label), translated) is not None


@pytest.mark.parametrize('label,translated', [
    ('1099 Report', 'Informe 1098'),
    ('3100: Unrestricted', '3110: Sin restricciones'),
    ('Annual Dues Roster 2026', 'Registro de Cuotas 2025'),
    ('Form 1295 Schedules', 'Anexos del Formulario'),          # dropped entirely
])
def test_a_changed_or_dropped_number_is_rejected(label, translated):
    assert delocalise(_one_segment(label), translated) is None


def test_signature_ignores_our_own_markers_and_placeholders():
    """[[S12]] and [[V1]] contain digits; they are ours, not the page's."""
    assert numeric_signature('[[S12]]Total [[V1]] for 2026') == ['2026']


def test_reordering_words_around_a_number_is_allowed():
    """Word order changes in translation; the digits do not."""
    segment = _one_segment('Report 1099 for members')
    assert delocalise(segment, 'Informe para miembros 1099') is not None


# ---------------------------------------------------------------------------
# Regressions from the third live warm run
# ---------------------------------------------------------------------------

def test_html_entities_are_not_read_as_numbers():
    """'Michael O&#39;Brien' contains no number. The apostrophe is not 39."""
    assert numeric_signature('Michael O&#39;Brien') == []
    assert numeric_signature('Smith &amp; Sons') == []
    assert numeric_signature('&#x27;Quoted&#x27;') == []
    assert numeric_signature('Form 1295 &mdash; Schedules') == ['1295']


def test_an_escaped_apostrophe_translates_to_a_real_one():
    """The exact failure: source escaped, translation not, nothing else changed."""
    segment = _one_segment('Michael O&#39;Brien')
    assert delocalise(segment, "Michael O'Brien") is not None


def test_a_translation_containing_markup_is_rejected():
    """The model ran past the string and swept up '<strong>FASB ASC 958</strong>'."""
    segment = _one_segment('All financial reports are generated in compliance with ')
    bad = ('Todos los informes financieros se generan en cumplimiento con '
           '<strong>FASB ASC 958</strong>')
    why = {}
    assert delocalise(segment, bad, report=why) is None
    assert 'HTML' in why['detail']


def test_an_invented_number_is_still_rejected():
    """Adding a form number that was never in the source is a fabrication."""
    segment = _one_segment('Schedules A, B, and C below are calculated from your ledger')
    assert delocalise(segment, 'Los Anexos A, B y C del Formulario 1295 se calculan') is None


def test_plain_angle_brackets_in_prose_are_not_mistaken_for_markup():
    segment = _one_segment('Budget under 5 percent')
    assert delocalise(segment, 'Presupuesto < 5 por ciento') is not None


# ---------------------------------------------------------------------------
# Account codes dropped from the front of a label
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('source,translated,expected', [
    ('1420 - Furniture &amp; Fixtures', 'Mobiliario y Equipo', '1420 - Mobiliario y Equipo'),
    ('5810 - Depreciation', 'Depreciación', '5810 - Depreciación'),
    ('1010 - Operating Checking Account', 'Cuenta Corriente Operativa',
     '1010 - Cuenta Corriente Operativa'),
])
def test_a_dropped_account_code_is_restored(source, translated, expected):
    """The code is the page's own text, so it goes back rather than failing."""
    assert delocalise(_one_segment(source), translated) == expected


def test_a_kept_account_code_is_left_alone():
    assert delocalise(_one_segment('5810 - Depreciation'),
                      '5810 - Depreciación') == '5810 - Depreciación'


def test_repair_never_rescues_a_changed_code():
    """5810 coming back as 5820 is not a dropped prefix; it is a wrong number."""
    assert delocalise(_one_segment('5810 - Depreciation'), '5820 - Depreciación') is None


def test_repair_never_rescues_a_shifted_row():
    """The real drift: string N answered with string N+12's content and code."""
    assert delocalise(_one_segment('1010 - Operating Checking Account'),
                      '1310 - Inversiones a Corto Plazo') is None


def test_repair_does_not_touch_strings_without_a_leading_code():
    assert delocalise(_one_segment('Membership Dues'), 'Cuotas de Membresía') \
        == 'Cuotas de Membresía'

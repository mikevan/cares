"""Unit tests for the translation masking layer.

These exercise services/translation_masking.py directly. It imports nothing
from Flask or the models on purpose, so none of this needs an app context or
a database.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from services.translation_masking import (  # noqa: E402
    CSRF_PLACEHOLDER,
    csrf_placeholder_intact,
    extract_csrf,
    mask_values,
    reinject_csrf,
    restore_values,
)


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

def test_currency_is_masked():
    html = '<td>$1,584.00</td>'
    masked, tokens, counts = mask_values(html)
    assert '$1,584.00' not in masked
    assert len(tokens) == 1
    assert list(tokens.values()) == ['$1,584.00']


def test_bare_two_place_amount_is_masked():
    """Statements print money without the sign when the header carries it."""
    masked, tokens, counts = mask_values('<td class="text-end">1,584.00</td>')
    assert '1,584.00' not in masked
    assert list(tokens.values()) == ['1,584.00']


def test_negative_and_parenthesised_amounts_are_masked():
    masked, tokens, counts = mask_values('<td>($1,234.56)</td><td>-$45.00</td>')
    assert '1,234.56' not in masked
    assert '45.00' not in masked


def test_bare_account_numbers_are_no_longer_masked():
    """Reversed deliberately after the first live run — see the module docstring.

    Masking every four-digit number turned '1099 Report' and '3100: Unrestricted'
    into mostly-placeholder, and the model dropped them. Account numbers in
    their own cells never reach the model anyway; the ones inside labels are
    protected by digit verification instead.
    """
    html = '<option value="1010">1010 - Checking</option><td>5810</td>'
    masked, tokens, counts = mask_values(html)
    assert masked == html
    assert tokens == {}


def test_currency_is_still_masked_alongside_account_numbers():
    masked, tokens, counts = mask_values('<td>4110</td><td>$1,584.00</td>')
    assert '4110' in masked          # passed through
    assert '$1,584.00' not in masked  # masked
    assert list(tokens.values()) == ['$1,584.00']


def test_currency_that_looks_like_an_account_number_is_still_currency():
    masked, tokens, counts = mask_values('<td>$1,010.00</td>')
    assert list(tokens.values()) == ['$1,010.00']


def test_script_and_style_bodies_are_left_alone():
    html = (
        '<style>.c{margin:1010px;width:9.50px}</style>'
        '<p>$1,584.00</p>'
        '<script>var total = 1584.00; var acct = "4110";</script>'
    )
    masked, tokens, counts = mask_values(html)
    assert 'margin:1010px' in masked
    assert 'width:9.50px' in masked          # a CSS length is not an amount
    assert 'var total = 1584.00' in masked   # a JS literal is not an amount
    assert '"4110"' in masked
    assert list(tokens.values()) == ['$1,584.00']   # only the <p>


def test_identical_values_share_one_placeholder():
    """Form 1295 renders dozens of `$0`. One token, four occurrences, is safer
    than four tokens the model can transpose."""
    masked, tokens, counts = mask_values('<td>$50.00</td><td>$50.00</td>')
    assert len(tokens) == 1
    token = list(tokens)[0]
    assert counts[token] == 2
    assert masked.count(token) == 2


def test_a_shared_placeholder_must_come_back_the_same_number_of_times():
    masked, tokens, counts = mask_values('<td>$0</td><td>$0</td><td>$0</td>')
    token = list(tokens)[0]
    assert restore_values(masked, tokens, counts) == '<td>$0</td><td>$0</td><td>$0</td>'
    assert restore_values(masked.replace(token, '', 1), tokens, counts) is None   # dropped
    assert restore_values(masked + token, tokens, counts) is None                 # duplicated


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

def test_round_trip_is_byte_exact():
    html = (
        '<h1>Statement of Activities</h1>'
        '<tr><td>4110 Dues Revenue</td><td>$1,584.00</td></tr>'
        '<tr><td>5810 Supplies</td><td>(2,340.15)</td></tr>'
        '<script>var x = 1;</script>'
    )
    masked, tokens, counts = mask_values(html)
    assert restore_values(masked, tokens, counts) == html


def test_round_trip_survives_translated_prose():
    html = '<p>Total collected: $1,584.00 in account 4110.</p>'
    masked, tokens, counts = mask_values(html)
    translated = masked.replace('Total collected:', 'Total recaudado:')
    translated = translated.replace('in account', 'en la cuenta')
    restored = restore_values(translated, tokens)
    assert restored == '<p>Total recaudado: $1,584.00 en la cuenta 4110.</p>'


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------

def test_dropped_placeholder_discards_the_translation():
    masked, tokens, counts = mask_values('<td>$1,584.00</td><td>$99.00</td>')
    mangled = masked.replace(list(tokens)[0], '$1.584,00')   # model "helpfully" localised it
    assert restore_values(mangled, tokens, counts) is None


def test_duplicated_placeholder_discards_the_translation():
    masked, tokens, counts = mask_values('<td>$1,584.00</td>')
    token = list(tokens)[0]
    assert restore_values(masked + token, tokens, counts) is None


def test_invented_placeholder_discards_the_translation():
    masked, tokens, counts = mask_values('<td>$1,584.00</td>')
    assert restore_values(masked + '__CARES_V0007__', tokens, counts) is None


def test_empty_page_round_trips():
    masked, tokens, counts = mask_values('<p>No transactions to report.</p>')
    assert tokens == {}
    assert restore_values(masked, tokens, counts) == '<p>No transactions to report.</p>'


# ---------------------------------------------------------------------------
# CSRF token
# ---------------------------------------------------------------------------

CSRF_META = '<meta name="csrf-token" content="{}">'


def test_csrf_token_is_replaced_by_a_stable_placeholder():
    a, token_a = extract_csrf(CSRF_META.format('IjEyMyI.aBcD.signature-one'))
    b, token_b = extract_csrf(CSRF_META.format('IjEyMyI.eFgH.signature-two'))
    assert token_a != token_b
    assert a == b                    # same cache key across requests


def test_csrf_token_reinjected_is_this_requests_token():
    blanked, _ = extract_csrf(CSRF_META.format('old-token'))
    assert reinject_csrf(blanked, 'live-token') == CSRF_META.format('live-token')


def test_stored_page_never_carries_a_real_token():
    blanked, token = extract_csrf(CSRF_META.format('secret-signature'))
    assert 'secret-signature' not in blanked
    assert CSRF_PLACEHOLDER in blanked


def test_lost_csrf_placeholder_is_a_discard_condition():
    blanked, token = extract_csrf(CSRF_META.format('t'))
    assert csrf_placeholder_intact(blanked, token)
    assert not csrf_placeholder_intact(blanked.replace(CSRF_PLACEHOLDER, 'ficha'), token)
    assert not csrf_placeholder_intact(blanked + CSRF_PLACEHOLDER, token)


def test_page_without_a_csrf_meta_is_not_a_discard_condition():
    blanked, token = extract_csrf('<p>no meta here</p>')
    assert token is None
    assert csrf_placeholder_intact(blanked, token)
    assert reinject_csrf(blanked, token) == '<p>no meta here</p>'


# ---------------------------------------------------------------------------
# Amounts without a thousands separator
# ---------------------------------------------------------------------------

def test_amount_without_separator_is_masked_whole():
    """A raw Decimal reaches the page as 1584.00, not 1,584.00."""
    masked, tokens, counts = mask_values('<td>$1584.00</td>')
    assert list(tokens.values()) == ['$1584.00']


def test_bare_amount_without_separator_is_masked():
    masked, tokens, counts = mask_values('<table data-total="1584.00">')
    assert '1584.00' not in masked
    assert list(tokens.values()) == ['1584.00']


def test_versioned_asset_paths_are_not_mistaken_for_money():
    html = '<link href="/static/css/bootstrap-5.3.2.min.css">'
    masked, tokens, counts = mask_values(html)
    assert masked == html
    assert tokens == {}

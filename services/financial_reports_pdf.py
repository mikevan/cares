"""
Financial statements -- PDF rendering
=====================================

The Balance Sheet, Income Statement, Statement of Cash Flows and Statement
of Functional Expenses as documents, using the same branded chrome as the
Trustee Audit Report and the Form 1295 schedules
(services/pdf_branding.py).

These pages previously offered a "Print" button wired to window.print(),
which produces the browser's rendering of the application -- navigation
sidebar included. That is a screenshot of a tool, not a financial
statement, and it is not something a council hands to its trustees, its
diocese or its accountant.

Every figure here comes from the same FinancialReports methods the screen
renders, passed in by the caller, so the document and the page cannot
disagree.
"""
import io

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from services import pdf_branding as brand

_AMOUNT_COL = 1.15 * inch


def _money(value):
    """Accounting presentation: parentheses for negatives, not a minus
    sign, because that is what a reader of a financial statement expects
    and what they will check against."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v < 0:
        return f"(${abs(v):,.2f})"
    return f"${v:,.2f}"


def _rows_table(rows, s, indent_first=True):
    """rows: list of (label, amount, kind) where kind is
    'item' | 'subtotal' | 'total' | 'head'."""
    data, style = [], [
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]
    for i, (label, amount, kind) in enumerate(rows):
        if kind == 'head':
            data.append([Paragraph(f"<b>{label}</b>", s['Body']), ''])
            style += [('BACKGROUND', (0, i), (-1, i), brand.PANEL),
                      ('TEXTCOLOR', (0, i), (-1, i), brand.KOFC_BLUE),
                      ('LEFTPADDING', (0, i), (0, i), 5),
                      ('TOPPADDING', (0, i), (-1, i), 5),
                      ('BOTTOMPADDING', (0, i), (-1, i), 5)]
        elif kind == 'total':
            data.append([Paragraph(f"<b>{label}</b>", s['Body']),
                         Paragraph(f"<b>{_money(amount)}</b>", s['Body'])])
            style += [('LINEABOVE', (0, i), (-1, i), 0.8, brand.INK),
                      ('LINEBELOW', (0, i), (-1, i), 1.6, brand.KOFC_BLUE),
                      ('TOPPADDING', (0, i), (-1, i), 5),
                      ('BOTTOMPADDING', (0, i), (-1, i), 5)]
        elif kind == 'subtotal':
            data.append([Paragraph(f"<b>{label}</b>", s['Body']),
                         Paragraph(f"<b>{_money(amount)}</b>", s['Body'])])
            style += [('LINEABOVE', (0, i), (-1, i), 0.5, brand.MUTED)]
        else:
            pad = '&nbsp;&nbsp;&nbsp;&nbsp;' if indent_first else ''
            data.append([Paragraph(f"{pad}{label}", s['Body']),
                         Paragraph(_money(amount), s['Body'])])
            style += [('LINEBELOW', (0, i), (-1, i), 0.25, brand.RULE)]

    t = Table(data, colWidths=[brand.CONTENT_WIDTH - _AMOUNT_COL, _AMOUNT_COL])
    t.setStyle(TableStyle(style))
    return t


def _finish(story, org, title, s, footnote=None):
    if footnote:
        story.append(Spacer(1, 12))
        story.append(Paragraph(footnote, s['Small']))
    buffer = io.BytesIO()
    return brand.build(buffer, story, org, title)


# ==================== BALANCE SHEET ====================

def build_balance_sheet_pdf(org, data, year=None):
    s = brand.styles()
    story = []
    brand.masthead(story, s, org, 'Statement of Financial Position',
                   f"As of {data.get('as_of_date', '')}")

    rows = []
    for section_key, section_label in (('assets', 'ASSETS'),
                                       ('liabilities', 'LIABILITIES'),
                                       ('net_assets', 'NET ASSETS')):
        section = data.get(section_key) or {}
        rows.append((section_label, None, 'head'))
        groups = section.get('groups') or {}
        subtotals = section.get('subtotals') or {}
        if not groups:
            rows.append(('None recorded', 0, 'item'))
        for subtype, accounts in groups.items():
            rows.append((f"<i>{subtype}</i>", None, 'head')) if False else None
            for a in accounts:
                rows.append((f"{a['number']} &nbsp; {a['name']}", a['balance'], 'item'))
            if subtype in subtotals:
                rows.append((f"Total {subtype}", subtotals[subtype], 'subtotal'))
        rows.append((f"Total {section_label.title()}", section.get('total', 0), 'total'))

    story.append(_rows_table(rows, s))
    story.append(Spacer(1, 10))
    story.append(_rows_table(
        [('Total Liabilities and Net Assets',
          data.get('total_liabilities_and_net_assets', 0), 'total')], s))

    assets = (data.get('assets') or {}).get('total', 0)
    tlna = data.get('total_liabilities_and_net_assets', 0)
    if abs(float(assets) - float(tlna)) >= 0.01:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"<b>This statement does not balance.</b> Total assets of {_money(assets)} do not "
            f"equal total liabilities and net assets of {_money(tlna)}, a difference of "
            f"{_money(float(assets) - float(tlna))}. Do not rely on this statement until the "
            f"difference is explained.", s['Body']))

    return _finish(story, org, 'Statement of Financial Position', s,
                   'Prepared on the accrual basis from posted journal entries. Net assets '
                   'include inception-to-date net income that has not yet been closed to '
                   'the net-asset accounts.')


# ==================== INCOME STATEMENT ====================

def build_income_statement_pdf(org, data, year=None):
    s = brand.styles()
    story = []
    brand.masthead(story, s, org, 'Statement of Activities',
                   f"For the period {data.get('period', '')}")

    rows = [('REVENUE AND SUPPORT', None, 'head')]
    revenues = (data.get('revenues') or {})
    for a in revenues.get('accounts', []) or [('', 0)]:
        if isinstance(a, dict):
            rows.append((f"{a['number']} &nbsp; {a['name']}", a['amount'], 'item'))
    if not revenues.get('accounts'):
        rows.append(('No revenue recorded in this period', 0, 'item'))
    rows.append(('Total Revenue and Support', revenues.get('total', 0), 'total'))

    rows.append(('EXPENSES', None, 'head'))
    expenses = (data.get('expenses') or {})
    for a in expenses.get('accounts', []):
        rows.append((f"{a['number']} &nbsp; {a['name']}", a['amount'], 'item'))
    if not expenses.get('accounts'):
        rows.append(('No expenses recorded in this period', 0, 'item'))
    rows.append(('Total Expenses', expenses.get('total', 0), 'total'))

    story.append(_rows_table(rows, s))
    story.append(Spacer(1, 12))

    net = data.get('net_income', 0)
    label = 'Change in Net Assets' + ('' if float(net) >= 0 else ' (Deficit)')
    story.append(_rows_table([(label, net, 'total')], s))

    return _finish(story, org, 'Statement of Activities', s,
                   'Revenue and expenses recognised when earned or incurred, from posted '
                   'journal entries only. Voided entries are excluded.')


# ==================== CASH FLOWS ====================

def _bucketed(rows, s, buckets, empty_label):
    """cash_receipts / cash_payments are {category: {account: amount}}."""
    any_row = False
    for category, accounts in (buckets or {}).items():
        if not accounts:
            continue
        rows.append((f"<i>{category}</i>", None, 'head'))
        for name, amount in accounts.items():
            rows.append((name, amount, 'item'))
            any_row = True
    if not any_row:
        rows.append((empty_label, 0, 'item'))


def build_cash_flow_pdf(org, data, year=None):
    s = brand.styles()
    story = []
    brand.masthead(story, s, org, 'Statement of Cash Flows',
                   f"For the period {data.get('period', '')}")

    rows = [('OPERATING ACTIVITIES', None, 'head')]
    _bucketed(rows, s, data.get('cash_receipts'), 'No operating receipts')
    rows.append(('Total cash received', data.get('total_receipts', 0), 'subtotal'))
    _bucketed(rows, s, data.get('cash_payments'), 'No operating payments')
    rows.append(('Total cash paid', data.get('total_payments', 0), 'subtotal'))
    rows.append(('Net Cash from Operating Activities',
                 data.get('operating_activities', 0), 'total'))

    rows.append(('INVESTING ACTIVITIES', None, 'head'))
    _bucketed(rows, s, data.get('investing_receipts'), 'No investing receipts')
    _bucketed(rows, s, data.get('investing_payments'), 'No investing payments')
    rows.append(('Net Cash from Investing Activities',
                 data.get('investing_activities', 0), 'total'))

    rows.append(('FINANCING ACTIVITIES', None, 'head'))
    _bucketed(rows, s, data.get('financing_inflows'), 'No financing inflows')
    _bucketed(rows, s, data.get('financing_outflows'), 'No financing outflows')
    rows.append(('Net Cash from Financing Activities',
                 data.get('financing_activities', 0), 'total'))

    story.append(_rows_table(rows, s))
    story.append(Spacer(1, 12))
    story.append(_rows_table([
        ('Net Change in Cash', data.get('net_change_in_cash', 0), 'subtotal'),
        ('Cash at Beginning of Period', data.get('beginning_cash', 0), 'item'),
        ('Cash at End of Period', data.get('ending_cash', 0), 'total'),
    ], s, indent_first=False))

    # The one arithmetic check a reader would do by hand.
    begin = float(data.get('beginning_cash', 0) or 0)
    change = float(data.get('net_change_in_cash', 0) or 0)
    end = float(data.get('ending_cash', 0) or 0)
    if abs(begin + change - end) >= 0.01:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"<b>This statement does not reconcile.</b> Beginning cash plus the net change "
            f"comes to {_money(begin + change)}, but cash at end of period is {_money(end)} "
            f"&mdash; a difference of {_money(begin + change - end)}.", s['Body']))

    return _finish(story, org, 'Statement of Cash Flows', s,
                   'Direct method, prepared from posted cash-account activity.')


# ==================== FUNCTIONAL EXPENSES ====================

def build_functional_expenses_pdf(org, data, year=None):
    s = brand.styles()
    story = []
    brand.masthead(story, s, org, 'Statement of Functional Expenses',
                   f"For the period {data.get('period', '')}")

    head = ['Expense by nature', 'Program', 'Management', 'Fundraising', 'Total']
    table = [[Paragraph(f"<b><font color='#FFFFFF'>{h}</font></b>", s['CellSmall'])
              for h in head]]
    expenses = data.get('expenses') or {}
    for name, row in expenses.items():
        table.append([
            Paragraph(f"{row.get('number','')} &nbsp; {name}", s['CellSmall']),
            Paragraph(_money(row.get('program', 0)), s['CellSmall']),
            Paragraph(_money(row.get('management', 0)), s['CellSmall']),
            Paragraph(_money(row.get('fundraising', 0)), s['CellSmall']),
            Paragraph(f"<b>{_money(row.get('total', 0))}</b>", s['CellSmall']),
        ])
    if not expenses:
        table.append([Paragraph('No expenses recorded in this period', s['CellSmall']),
                      '', '', '', ''])

    totals = data.get('totals') or {}
    table.append([
        Paragraph("<b>Total Expenses</b>", s['CellSmall']),
        Paragraph(f"<b>{_money(totals.get('program', 0))}</b>", s['CellSmall']),
        Paragraph(f"<b>{_money(totals.get('management', 0))}</b>", s['CellSmall']),
        Paragraph(f"<b>{_money(totals.get('fundraising', 0))}</b>", s['CellSmall']),
        Paragraph(f"<b>{_money(totals.get('total', 0))}</b>", s['CellSmall']),
    ])

    num = 1.05 * inch
    t = Table(table, colWidths=[brand.CONTENT_WIDTH - 4 * num] + [num] * 4, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand.KOFC_BLUE),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFB')]),
        ('LINEBELOW', (0, 1), (-1, -2), 0.25, brand.RULE),
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, brand.INK),
        ('LINEBELOW', (0, -1), (-1, -1), 1.6, brand.KOFC_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    return _finish(story, org, 'Statement of Functional Expenses', s,
                   'Expenses allocated across program services, management and general, and '
                   'fundraising, as required by FASB ASC 958-720.')

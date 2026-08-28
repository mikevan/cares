"""
Trustee Audit Report -- PDF
===========================

A real report, not a print of the web page.

The screen at /audit/log is a working tool: filter, scroll, click. What a
council's trustees actually need to come out of a Section 145 audit is a
document they can read start to finish, sign, and put in the council's
records -- one that states the period examined, what was examined, what
the examination found, and whether the record it is drawn from can be
shown to be intact. Printing the browser page produces none of that; it
produces a screenshot of a tool, with the navigation sidebar down one
side.

So this builds the document:

    1. Branded masthead -- the council's own name, number, District
       Deputy and emblem (services/pdf_branding.py).
    2. Scope: the period examined, any table filter, when it was
       generated and by whom, and a plain statement of what the audit log
       is and is not.
    3. Chain integrity -- the finding that actually matters. Both
       verification queries are re-run at generation time and the verdict
       is printed on the document, in green or in red. A trustee should
       not have to take the software's word for it in a separate screen.
    4. Summary: totals by table, by operation, and by the person who made
       the change.
    5. The detail: every change in the period, with the specific fields
       that changed on an edit.
    6. Signature lines for the trustees and the Grand Knight.

Every figure is computed from audit_log at the moment of generation. The
report holds no state of its own.
"""
from collections import Counter
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from services import pdf_branding as brand

_MAX_VALUE_CHARS = 90


def _fmt_value(value):
    if value is None:
        return '<font color="#8A97A3">(empty)</font>'
    text = str(value)
    if len(text) > _MAX_VALUE_CHARS:
        text = text[:_MAX_VALUE_CHARS - 1] + '…'
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _change_cell(s, entry, diff):
    """What changed, in words. For an UPDATE, the fields that actually
    moved and their before/after values; for an INSERT or DELETE, the
    record's own identifying detail rather than a dump of every column."""
    if entry.operation == 'UPDATE':
        if not diff:
            return Paragraph('<i>No field values changed.</i>', s['CellSmall'])
        lines = []
        for field, old, new in diff[:6]:
            lines.append(f"<b>{field}</b>: {_fmt_value(old)} &rarr; {_fmt_value(new)}")
        if len(diff) > 6:
            lines.append(f"<font color='#5A6875'>+ {len(diff) - 6} more field(s)</font>")
        return Paragraph('<br/>'.join(lines), s['CellSmall'])

    data = entry.new_data if entry.operation == 'INSERT' else entry.old_data
    if not data:
        return Paragraph('—', s['CellSmall'])
    # Prefer the columns a human would use to recognise the record.
    preferred = ('name', 'description', 'invoice_number', 'reference_number',
                 'account_number', 'account_name', 'username', 'amount',
                 'debit_amount', 'credit_amount', 'event_type', 'year', 'status')
    shown = [(k, data[k]) for k in preferred if k in data and data[k] not in (None, '')]
    if not shown:
        shown = [(k, v) for k, v in list(data.items())[:3] if k != 'id']
    return Paragraph(
        '<br/>'.join(f"<b>{k}</b>: {_fmt_value(v)}" for k, v in shown[:5]),
        s['CellSmall'])


def build_audit_report_pdf(org, rows, period_start, period_end,
                           table_filter, verification, generated_by,
                           truncated=False, row_limit=None):
    """
    rows          -- [{'entry': AuditLog, 'actor_name': str, 'diff': [...]}, ...]
    verification  -- dict from verify_chain(): total_rows, self_failures,
                     chain_breaks, intact
    """
    import io
    s = brand.styles()
    story = []
    buffer = io.BytesIO()

    period_label = (f"{period_start:%B} {period_start.day}, {period_start:%Y} "
                    f"through {period_end:%B} {period_end.day}, {period_end:%Y}")

    brand.masthead(
        story, s, org,
        'Trustee Audit Report',
        'Record of changes to financial, membership and access-control data, '
        'prepared for the semi-annual audit required by Section 145.')

    # ---- 1. Scope -------------------------------------------------------
    story.append(Paragraph('Scope of this report', s['SectionHead']))
    story.append(brand.panel(s, [
        ['Period examined', period_label],
        ['Records covered', 'All audited tables' if not table_filter else f'{table_filter} only'],
        ['Changes listed', f'{len(rows):,}' + (f' (display limit {row_limit:,} reached)'
                                               if truncated and row_limit else '')],
        ['Generated', datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')],
        ['Generated by', generated_by or 'CARES'],
    ]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'Every insert, edit and delete on an audited table is captured by a database trigger, '
        'independently of the application &mdash; a change made with a direct SQL tool is recorded '
        'the same as one made on screen. Each entry is hash-chained to the one before it, so a '
        'record that was altered or removed after the fact can be detected. This report lists what '
        'was changed and by whom; it does not, and cannot, judge whether a properly recorded '
        'transaction was appropriate. That judgement is the trustees\'.',
        s['Body']))

    # ---- 2. Chain integrity --------------------------------------------
    story.append(Paragraph('Integrity of the record', s['SectionHead']))
    intact = verification.get('intact')
    total_rows = verification.get('total_rows', 0)
    if intact:
        verdict_text = (
            f"<b>The chain is intact.</b> All {total_rows:,} entries in the audit log were "
            f"re-hashed at the moment this report was generated and every one matched, and every "
            f"entry's link to the entry before it was confirmed. No record has been altered or "
            f"removed since it was written.")
        band, ink = colors.HexColor('#EAF5EE'), brand.OK_GREEN
    else:
        verdict_text = (
            f"<b>INTEGRITY FAILURE.</b> {verification.get('self_failures', 0)} entr(ies) no longer "
            f"match their own hash and {verification.get('chain_breaks', 0)} break(s) were found in "
            f"the chain, out of {total_rows:,} total. This means the audit log was modified outside "
            f"the trigger that writes it. Treat this as evidence and escalate it; do not file this "
            f"report as a clean audit.")
        band, ink = colors.HexColor('#FDECEF'), brand.KOFC_RED
    # hexval() returns '0x00529f'; reportlab's <font color> wants '#00529f'.
    ink_hex = '#' + ink.hexval()[2:]
    verdict = Table([[Paragraph(f"<font color='{ink_hex}'>{verdict_text}</font>", s['Body'])]],
                    colWidths=[brand.CONTENT_WIDTH])
    verdict.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), band),
        ('BOX', (0, 0), (-1, -1), 0.6, ink),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.append(verdict)

    # ---- 3. Summary -----------------------------------------------------
    entries = [r['entry'] for r in rows]
    by_table = Counter(e.table_name for e in entries)
    by_op = Counter(e.operation for e in entries)
    by_actor = Counter(r['actor_name'] for r in rows)

    story.append(Paragraph('Summary of changes in the period', s['SectionHead']))

    op_rows = [['Operation', 'Count']] + [
        [op.title(), f'{by_op.get(op, 0):,}'] for op in ('INSERT', 'UPDATE', 'DELETE')]
    tbl_rows = [['Record type', 'Count']] + [
        [t.replace('_', ' '), f'{c:,}'] for t, c in by_table.most_common(9)]
    actor_rows = [['Changed by', 'Count']] + [
        [a, f'{c:,}'] for a, c in by_actor.most_common(9)]

    def mini(data, width):
        t = Table(data, colWidths=[width - 0.75 * inch, 0.75 * inch], repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TEXTCOLOR', (0, 0), (-1, 0), brand.MUTED),
            ('BACKGROUND', (0, 0), (-1, 0), brand.PANEL),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, brand.RULE),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        return t

    half = brand.CONTENT_WIDTH / 2 - 8
    summary = Table([[mini(tbl_rows, half), mini(actor_rows, half)]],
                    colWidths=[half + 8, half + 8])
    summary.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                 ('LEFTPADDING', (0, 0), (0, 0), 0),
                                 ('RIGHTPADDING', (-1, 0), (-1, 0), 0)]))
    story.append(summary)
    story.append(Spacer(1, 8))
    story.append(mini(op_rows, half))

    # ---- 4. Detail ------------------------------------------------------
    story.append(Paragraph('Changes in detail', s['SectionHead']))
    if not rows:
        story.append(Paragraph(
            'No changes were recorded on any audited table during this period.', s['Body']))
    else:
        # White explicitly inside the Paragraph: a TableStyle TEXTCOLOR does
        # not reach text that a Paragraph has already styled, so relying on
        # it leaves dark header text on the dark blue band.
        head = [Paragraph(f"<b><font color='#FFFFFF'>{h}</font></b>", s['CellSmall'])
                for h in ('Date &amp; time', 'Changed by', 'Record', 'Action', 'What changed')]
        data = [head]
        for r in rows:
            e = r['entry']
            data.append([
                Paragraph(e.changed_at.strftime('%Y-%m-%d<br/>%H:%M:%S'), s['CellMono']),
                Paragraph(r['actor_name'], s['CellSmall']),
                Paragraph(f"{e.table_name.replace('_', ' ')}<br/>"
                          f"<font color='#5A6875'>#{e.row_id}</font>", s['CellSmall']),
                Paragraph(e.operation.title(), s['CellSmall']),
                _change_cell(s, e, r['diff']),
            ])
        widths = [0.78 * inch, 0.92 * inch, 1.0 * inch, 0.55 * inch,
                  brand.CONTENT_WIDTH - (0.78 + 0.92 + 1.0 + 0.55) * inch]
        detail = Table(data, colWidths=widths, repeatRows=1)
        detail.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), brand.KOFC_BLUE),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, brand.RULE),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFB')]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(detail)
        if truncated and row_limit:
            story.append(Spacer(1, 6))
            story.append(Paragraph(
                f"This report lists the {row_limit:,} most recent changes in the period. More "
                f"exist. Narrow the date range or filter to a single record type to see the "
                f"remainder.", s['Small']))

    # ---- 5. Attestation -------------------------------------------------
    story.append(Spacer(1, 18))
    story.append(KeepTogether([
        Paragraph('Trustees&rsquo; review', s['SectionHead']),
        Paragraph(
            'We have examined the record of changes set out above for the period stated, together '
            'with the integrity verification printed on this report, and accept it as the '
            'council&rsquo;s record of account activity for that period.', s['Body']),
        Spacer(1, 4),
        brand.signature_block(s, ['Trustee', 'Trustee', 'Trustee', 'Grand Knight']),
    ]))

    story.append(Spacer(1, 6))
    story.append(Paragraph(
        'Produced by CARES. The underlying audit log is append-only and hash-chained; the '
        'verification above can be reproduced independently by anyone with read access to the '
        'database, without this application.', s['Small']))

    return brand.build(buffer, story, org, 'Trustee Audit Report',
                       doc_title=f'Trustee Audit Report — {period_label}')

"""
Shared branded PDF chrome
=========================

One masthead, one footer, one palette, used by every PDF this application
produces. Exists because the alternative -- each report module drawing its
own header -- is how a product ends up with a Form 1295 that says
"Council #14203" in Helvetica and an audit report that says nothing at
all, and a council officer noticing the difference before you do.

The branding is taken from the SAME source the web UI uses, so a PDF can
never disagree with the screen it was generated from:

    org.name      -> the council name on the masthead
    org.css_file  -> the emblem. app.py::inject_branding turns 'kofc.css'
                     into org_code 'kofc' and renders
                     static/images/kofc.svg (falling back to .png); this
                     module resolves the same code to
                     static/images/<code>.png, since reportlab has no SVG
                     support without an extra dependency.

A council with no css_file set gets a clean, unbranded masthead rather
than a broken image -- that is the CARES generic case, not an error.

Page numbering is "Page X of Y", which needs the total before any page is
written, so pages are buffered and stamped on save (see NumberedCanvas).
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

# Sampled from static/images/kofc.png -- the emblem's own colours, so the
# documents and the application agree.
KOFC_BLUE = colors.HexColor('#00529F')
KOFC_GOLD = colors.HexColor('#EDB312')
KOFC_RED = colors.HexColor('#ED164C')
INK = colors.HexColor('#16202B')
MUTED = colors.HexColor('#5A6875')
RULE = colors.HexColor('#DDE3E9')
PANEL = colors.HexColor('#F1F4F7')
OK_GREEN = colors.HexColor('#1B6F4A')

PAGE_SIZE = letter
MARGIN_LEFT = 0.75 * inch
MARGIN_RIGHT = 0.75 * inch
MARGIN_TOP = 0.75 * inch
MARGIN_BOTTOM = 0.85 * inch
CONTENT_WIDTH = PAGE_SIZE[0] - MARGIN_LEFT - MARGIN_RIGHT


def styles():
    """Document styles. Built fresh per document because reportlab's
    sample stylesheet is mutable and shared."""
    s = getSampleStyleSheet()
    s.add(ParagraphStyle('CouncilName', parent=s['Normal'], fontName='Helvetica-Bold',
                         fontSize=15, leading=18, textColor=KOFC_BLUE))
    s.add(ParagraphStyle('CouncilMeta', parent=s['Normal'], fontName='Helvetica',
                         fontSize=8.5, leading=11, textColor=MUTED))
    s.add(ParagraphStyle('ReportTitle', parent=s['Normal'], fontName='Helvetica-Bold',
                         fontSize=19, leading=23, textColor=INK, spaceBefore=2))
    s.add(ParagraphStyle('ReportSubtitle', parent=s['Normal'], fontName='Helvetica',
                         fontSize=10.5, leading=14, textColor=MUTED))
    s.add(ParagraphStyle('SectionHead', parent=s['Normal'], fontName='Helvetica-Bold',
                         fontSize=11.5, leading=14, textColor=KOFC_BLUE,
                         spaceBefore=14, spaceAfter=5))
    s.add(ParagraphStyle('Body', parent=s['Normal'], fontName='Helvetica',
                         fontSize=9.5, leading=13, textColor=INK))
    s.add(ParagraphStyle('Small', parent=s['Normal'], fontName='Helvetica',
                         fontSize=8, leading=10.5, textColor=MUTED))
    s.add(ParagraphStyle('CellSmall', parent=s['Normal'], fontName='Helvetica',
                         fontSize=7.5, leading=9.5, textColor=INK))
    s.add(ParagraphStyle('CellMono', parent=s['Normal'], fontName='Courier',
                         fontSize=7, leading=9, textColor=INK))
    return s


def council_line(org):
    """'Bishop Kelley Council #14203' -- however much of that we have."""
    if not org:
        return 'Council'
    name = org.name or 'Council'
    number = getattr(org, 'council_number', None)
    return f"{name}  ·  Council #{number}" if number else name


def emblem_path(org):
    """Absolute path to the org's emblem PNG, or None.

    Mirrors app.py::inject_branding: css_file 'kofc.css' -> code 'kofc' ->
    static/images/kofc.png. Returns None rather than raising when the org
    has no branding or the file is absent, so an unbranded deployment
    still gets a clean document.
    """
    css_file = getattr(org, 'css_file', None) if org else None
    if not css_file or not css_file.endswith('.css'):
        return None
    code = css_file[:-4]
    try:
        from flask import current_app
        root = current_app.root_path
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, 'static', 'images', f'{code}.png')
    return path if os.path.exists(path) else None


def _emblem_flowable(org, height=0.62 * inch):
    path = emblem_path(org)
    if not path:
        return None
    try:
        iw, ih = ImageReader(path).getSize()
        return Image(path, width=height * (iw / float(ih)), height=height)
    except Exception:
        return None


def masthead(story, s, org, title, subtitle=None):
    """Emblem + council identity, a blue/gold rule, then the report title.

    Called once at the top of every document. Later pages get the slim
    running header drawn by page_furniture() instead.
    """
    emblem = _emblem_flowable(org)
    ident = [Paragraph(org.name if org and org.name else 'Council', s['CouncilName'])]
    number = getattr(org, 'council_number', None) if org else None
    bits = []
    if number:
        bits.append(f"Council #{number}")
    dd = getattr(org, 'district_deputy_name', None) if org else None
    if dd:
        bits.append(f"District Deputy: {dd}")
    if bits:
        ident.append(Paragraph('&nbsp;&nbsp;·&nbsp;&nbsp;'.join(bits), s['CouncilMeta']))

    if emblem:
        head = Table([[emblem, ident]], colWidths=[0.78 * inch, CONTENT_WIDTH - 0.78 * inch])
    else:
        head = Table([[ident]], colWidths=[CONTENT_WIDTH])
    head.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('RIGHTPADDING', (-1, 0), (-1, 0), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(head)

    rule = Table([[''], ['']], colWidths=[CONTENT_WIDTH], rowHeights=[2.6, 1.4])
    rule.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), KOFC_BLUE),
        ('BACKGROUND', (0, 1), (0, 1), KOFC_GOLD),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(rule)
    story.append(Spacer(1, 14))
    story.append(Paragraph(title, s['ReportTitle']))
    if subtitle:
        story.append(Paragraph(subtitle, s['ReportSubtitle']))
    story.append(Spacer(1, 10))


def make_canvas(org, report_title):
    """Canvas subclass that stamps a running header and 'Page X of Y'.

    The total page count is not known until the document is finished, so
    every page is held in memory and the furniture is drawn on save().
    That is the standard reportlab approach for 'of Y' numbering; the cost
    is memory proportional to the document, which for a council's audit
    report is nothing.
    """
    council = council_line(org)

    class NumberedCanvas(_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._furniture(total)
                super().showPage()
            super().save()

        def _furniture(self, total):
            page = self._pageNumber
            width, height = PAGE_SIZE

            # Running header, second page onward. The first page already
            # carries the full masthead.
            if page > 1:
                self.setFont('Helvetica', 7.5)
                self.setFillColor(MUTED)
                self.drawString(MARGIN_LEFT, height - 0.5 * inch, council)
                self.drawRightString(width - MARGIN_RIGHT, height - 0.5 * inch, report_title)
                self.setStrokeColor(RULE)
                self.setLineWidth(0.5)
                self.line(MARGIN_LEFT, height - 0.58 * inch,
                          width - MARGIN_RIGHT, height - 0.58 * inch)

            self.setStrokeColor(KOFC_GOLD)
            self.setLineWidth(1.2)
            self.line(MARGIN_LEFT, 0.62 * inch, width - MARGIN_RIGHT, 0.62 * inch)

            self.setFont('Helvetica', 7.5)
            self.setFillColor(MUTED)
            self.drawString(MARGIN_LEFT, 0.46 * inch, council)
            self.setFillColor(KOFC_BLUE)
            self.setFont('Helvetica-Bold', 7.5)
            self.drawRightString(width - MARGIN_RIGHT, 0.46 * inch, f'Page {page} of {total}')

    return NumberedCanvas


def build(buffer, story, org, report_title, doc_title=None):
    """Render `story` into `buffer` with the shared page furniture."""
    from reportlab.platypus import SimpleDocTemplate
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE_SIZE,
        leftMargin=MARGIN_LEFT, rightMargin=MARGIN_RIGHT,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOTTOM,
        title=doc_title or report_title,
        author=council_line(org),
        subject=report_title,
    )
    doc.build(story, canvasmaker=make_canvas(org, report_title))
    return buffer


def panel(s, rows, col_widths=None, head=True):
    """A small label/value table used for parameter and summary blocks."""
    t = Table(rows, colWidths=col_widths or [1.85 * inch, CONTENT_WIDTH - 1.85 * inch])
    style = [
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), MUTED),
        ('TEXTCOLOR', (1, 0), (1, -1), INK),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -2), 0.25, RULE),
    ]
    t.setStyle(TableStyle(style))
    return t


def signature_block(s, roles):
    """Wet-signature lines. Deliberately drawn rules rather than form
    fields: a document a trustee signs should not be something a PDF
    reader lets someone type into afterwards."""
    cells = []
    for role in roles:
        cells.append([
            Paragraph('&nbsp;', s['Body']),
            Paragraph(f"<font size=7 color='#5A6875'>{role}</font>", s['Small']),
        ])
    col = CONTENT_WIDTH / 2.0 - 6
    rows, style, r = [], [], 0
    for i in range(0, len(roles), 2):
        pair = roles[i:i + 2]
        rows.append([Paragraph('&nbsp;', s['Body'])] * len(pair))
        rows.append([Paragraph(f"<font size=7.5 color='#5A6875'>{p} &mdash; signature and date</font>",
                               s['Small']) for p in pair])
        style += [
            ('LINEBELOW', (0, r), (len(pair) - 1, r), 0.6, INK),
            ('TOPPADDING', (0, r), (-1, r), 16),
            ('BOTTOMPADDING', (0, r), (-1, r), 2),
            ('TOPPADDING', (0, r + 1), (-1, r + 1), 2),
            ('BOTTOMPADDING', (0, r + 1), (-1, r + 1), 10),
        ]
        r += 2
    t = Table(rows, colWidths=[col, col][:max(len(roles), 1)] if len(roles) > 1 else [CONTENT_WIDTH])
    t.setStyle(TableStyle(style + [
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))
    return t

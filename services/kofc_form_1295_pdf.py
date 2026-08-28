"""
Knights of Columbus Form 1295 -- PDF rendering
=================================================

Turns the dicts services/kofc_form_1295.py computes into a printable PDF
per schedule, so a trustee can download exactly what they see on screen
(blueprints/audit_routes.py's /audit/form-1295 page) and attach it to
whatever they file with Supreme and the state office. Deliberately three
separate, small PDFs (one per schedule) rather than one combined
document, matching how the on-screen report and the Form 1295 paper
process both split them.

Uses reportlab -- pure Python, no external binary (wkhtmltopdf, a
system-level Cairo/Pango install) required, which matters since this app
is deployed on plain Windows and Render.com boxes without assuming any
extra system packages are present.

Every dollar figure and count on these PDFs comes straight from
services/kofc_form_1295.py's ledger calculations -- there is no
interactive/fillable field anywhere on them, deliberately: a number a
trustee signs and files should never be something a PDF reader lets
someone quietly type over after the fact. The only things filled in
outside the ledger (an explanation for a non-zero miscellaneous line, and
who attested the schedules) come from a Form1295Submission record, which
is itself on the tamper-evident audit trail (see models.py) -- so even
that narrative text has a real, auditable source, not a blank the PDF
itself leaves open.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

_HEADER_STYLE_NAME = 'Heading1'
_SUBHEADER_STYLE_NAME = 'Heading2'
_BODY_STYLE_NAME = 'Normal'

_TABLE_STYLE = TableStyle([
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ('TOPPADDING', (0, 0), (-1, -1), 4),
    ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ('LINEBELOW', (0, 0), (-1, -2), 0.25, colors.lightgrey),
    ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
    ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
])


def _money(value):
    return f"${value:,.2f}"


def _header(story, styles, org, title, subtitle):
    """Council emblem, name, number and District Deputy, over the blue and
    gold rule -- the same masthead the Trustee Audit Report uses, from
    services/pdf_branding.py. These schedules go to Supreme and the state
    office over a council's name; they should look like the council's own
    document, not like a generic export."""
    from services import pdf_branding as brand
    brand.masthead(story, brand.styles(), org, title, subtitle)


def _attestation_footer(story, styles, org, submission):
    """Appended to every schedule PDF: the District Deputy this gets
    routed to (if the council has recorded one), and whether/when someone
    attested these schedules in CARES. Deliberately NOT a signature line
    a PDF reader can fill in -- see the module docstring for why."""
    story.append(Spacer(1, 0.3 * inch))
    district_deputy = getattr(org, 'district_deputy_name', None) if org else None
    if district_deputy:
        story.append(Paragraph(f"District Deputy of record: {district_deputy}", styles[_BODY_STYLE_NAME]))
    if submission and submission.is_attested:
        attested_by = submission.attested_by.username if submission.attested_by else 'a CARES user'
        story.append(Paragraph(
            f"Attested in CARES by {attested_by} on {submission.attested_at.strftime('%B %d, %Y')} "
            f"(this attestation is itself recorded on the tamper-evident audit trail).",
            styles[_BODY_STYLE_NAME],
        ))
    else:
        story.append(Paragraph(
            "Not yet attested in CARES for this period -- see the Form 1295 Schedules page.",
            styles[_BODY_STYLE_NAME],
        ))
    story.append(Paragraph(
        "This document still requires the Grand Knight's and trustees' physical signatures "
        "on the official Form 1295 before it is filed with Supreme and the state council.",
        styles[_BODY_STYLE_NAME],
    ))


_REPORT_TITLE = 'Knights of Columbus Form 1295'


def _build(story_builder, org=None):
    """Render through services/pdf_branding.py so these schedules carry the
    same masthead, running header, gold rule and 'Page X of Y' as every
    other document this application produces."""
    from services import pdf_branding as brand
    buffer = io.BytesIO()
    styles = brand.styles()
    story = []
    story_builder(story, styles)
    return brand.build(buffer, story, org, _REPORT_TITLE)


def build_schedule_a_pdf(org, data, submission=None, _story_only=False):
    def _story(story, styles):
        _header(story, styles, org, 'Form 1295 -- Schedule A: Membership',
                f"Period: {data['period_start']} to {data['period_end']}")

        rows = [['', '']]
        rows.append(['Members, start of period', str(data['members_start_of_period'])])
        for event_type, count in data['additions'].items():
            rows.append([f"  + {event_type}", str(count)])
        rows.append(['Total for period', str(data['total_for_period'])])
        for event_type, count in data['deductions'].items():
            rows.append([f"  - {event_type}", str(count)])
        rows.append(['Total deductions', str(data['total_deductions'])])
        rows.append(['Number of members, end of period', str(data['members_end_of_period'])])
        story.append(Table(rows, colWidths=[4.5 * inch, 1.5 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.15 * inch))

        if not data['reconciled']:
            story.append(Paragraph(
                f"NOTE: this roll-forward ({data['members_end_of_period']}) does not match the "
                f"live active-member count ({data['active_members_actual']}). Some status change "
                f"likely happened without a logged membership event -- review the member "
                f"directory before filing.",
                styles[_BODY_STYLE_NAME],
            ))
            story.append(Spacer(1, 0.15 * inch))

        dues_rows = [
            ['', ''],
            [f"Dues records for {data['dues_year']}", str(data['dues_records_for_year'])],
            [f"Dues paid for {data['dues_year']}", str(data['dues_paid_for_year'])],
            ['Dues collected in this period', _money(data['dues_collected_in_period'])],
        ]
        story.append(Table(dues_rows, colWidths=[4.5 * inch, 1.5 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            "Membership records are tracked in this system's member directory and membership "
            "event log, satisfying Schedule A's confirmation requirement.",
            styles[_BODY_STYLE_NAME],
        ))
        _attestation_footer(story, styles, org, submission)
    if _story_only:
        return _story
    return _build(_story, org)


def build_schedule_b_pdf(org, data, submission=None, _story_only=False):
    def _story(story, styles):
        _header(story, styles, org, 'Form 1295 -- Schedule B: Cash Transactions',
                f"Period: {data['period_start']} to {data['period_end']}")

        fs = data['financial_secretary']
        story.append(Paragraph('Financial Secretary', styles[_SUBHEADER_STYLE_NAME]))
        fs_rows = [['', '']]
        fs_rows.append(['Opening funds in possession', _money(fs['opening_funds_in_possession'])])
        fs_rows.append(['Dues & initiations received', _money(fs['dues_and_initiations_received'])])
        for f in fs['top_fundraisers']:
            fs_rows.append([f"Fundraiser: {f['name']}", _money(f['amount'])])
        fs_rows.append(['Miscellaneous income', _money(fs['misc_income'])])
        fs_rows.append(['Total cash received', _money(fs['total_cash_received'])])
        fs_rows.append(['Transferred to Treasurer', f"({_money(fs['transferred_to_treasurer'])})"])
        fs_rows.append(['Closing funds in possession', _money(fs['closing_funds_in_possession'])])
        story.append(Table(fs_rows, colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))
        if submission and submission.misc_income_explanation:
            story.append(Paragraph(f"Miscellaneous income explained: {submission.misc_income_explanation}",
                                    styles[_BODY_STYLE_NAME]))
        elif fs['misc_income'] > 0:
            story.append(Paragraph(
                "Miscellaneous income is non-zero and has no explanation on file -- add one on "
                "the Form 1295 Schedules page before filing.",
                styles[_BODY_STYLE_NAME],
            ))
        story.append(Spacer(1, 0.25 * inch))

        tr = data['treasurer']
        if not tr.get('reconciles', True):
            story.append(Paragraph(
                "<b>DOES NOT RECONCILE.</b> Opening balance plus receipts minus "
                "disbursements does not equal the closing balance shown below; the "
                "difference is " + _money(tr['unreconciled_difference']) + ". This "
                "schedule should not be filed until that difference is explained.",
                styles[_BODY_STYLE_NAME],
            ))
            story.append(Spacer(1, 8))
        story.append(Paragraph('Treasurer (Checking Account)', styles[_SUBHEADER_STYLE_NAME]))
        tr_rows = [
            ['', ''],
            ['Opening balance', _money(tr['opening_balance'])],
            ['Received from Financial Secretary', _money(tr['received_from_financial_secretary'])],
            ['Transfers from savings', _money(tr['transfers_from_savings'])],
            ['Checking account interest', _money(tr['checking_account_interest'])],
            ['Per capita - Supreme Council', f"({_money(tr['per_capita_supreme_council'])})"],
            ['Per capita - State Council', f"({_money(tr['per_capita_state_council'])})"],
            ['General council expenses', f"({_money(tr['general_council_expenses'])})"],
            ['Transfers to savings', f"({_money(tr['transfers_to_savings'])})"],
            ['Charitable donations', f"({_money(tr['charitable_donations'])})"],
            ['Transfers to investments', f"({_money(tr['transfers_to_investments'])})"],
            ['Total receipts', _money(tr['total_receipts'])],
            ['Total disbursements', f"({_money(tr['total_disbursements'])})"],
            ['Closing balance', _money(tr['closing_balance'])],
        ]
        story.append(Table(tr_rows, colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(data['note'], styles[_BODY_STYLE_NAME]))
        _attestation_footer(story, styles, org, submission)
    if _story_only:
        return _story
    return _build(_story, org)


def build_schedule_c_pdf(org, data, submission=None, _story_only=False):
    def _story(story, styles):
        _header(story, styles, org, 'Form 1295 -- Schedule C: Financial Position',
                f"As of {data['as_of_date']}")

        current = data['assets']['current']
        story.append(Paragraph('Current Assets', styles[_SUBHEADER_STYLE_NAME]))
        current_rows = [
            ['', ''],
            ['Financial Secretary cash on hand', _money(current['financial_secretary_cash_on_hand'])],
            ['Checking account', _money(current['checking_account'])],
            ['Savings account', _money(current['savings_account'])],
            ['Money market account', _money(current['money_market_account'])],
            [f"Due from members ({current['due_from_members_note']})", _money(current['due_from_members'])],
            ['Total current assets', _money(current['total_current_assets'])],
        ]
        story.append(Table(current_rows, colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))

        liabilities = data['liabilities']
        story.append(Paragraph('Liabilities', styles[_SUBHEADER_STYLE_NAME]))
        liability_rows = [
            ['', ''],
            ['Supreme Council charges', _money(liabilities['supreme_council_charges'])],
            ['State Council charges', _money(liabilities['state_council_charges'])],
            [f"Advance payments ({liabilities['advance_payments_note']})", _money(liabilities['advance_payments'])],
            ['Miscellaneous liabilities', _money(liabilities['misc_liabilities'])],
            ['Total liabilities', _money(liabilities['total_liabilities'])],
        ]
        story.append(Table(liability_rows, colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))
        if submission and submission.misc_liabilities_explanation:
            story.append(Paragraph(f"Miscellaneous liabilities explained: {submission.misc_liabilities_explanation}",
                                    styles[_BODY_STYLE_NAME]))
        elif liabilities['misc_liabilities'] > 0:
            story.append(Paragraph(
                "Miscellaneous liabilities are non-zero and have no explanation on file -- add "
                "one on the Form 1295 Schedules page before filing.",
                styles[_BODY_STYLE_NAME],
            ))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Table(
            [['Net Current Assets', _money(data['net_current_assets'])]],
            colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE,
        ))
        story.append(Spacer(1, 0.25 * inch))

        long_term = data['assets']['long_term']
        story.append(Paragraph('Long-Term / Other Assets', styles[_SUBHEADER_STYLE_NAME]))
        long_term_rows = [
            ['', ''],
            ['Certificates of deposit', _money(long_term['certificates_of_deposit'])],
            ['Mutual fund investments', _money(long_term['mutual_fund_investments'])],
            ['Other assets', _money(long_term['other_assets'])],
            ['Total long-term assets', _money(long_term['total_long_term_assets'])],
        ]
        story.append(Table(long_term_rows, colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE))
        story.append(Spacer(1, 0.2 * inch))

        story.append(Table(
            [
                ['Total Assets', _money(data['assets']['total_assets'])],
                ['Total Net Assets', _money(data['total_net_assets'])],
            ],
            colWidths=[4 * inch, 2 * inch], style=_TABLE_STYLE,
        ))
        _attestation_footer(story, styles, org, submission)
    if _story_only:
        return _story
    return _build(_story, org)

def build_all_schedules_pdf(org, schedule_a, schedule_b, schedule_c, submission=None):
    """Schedules A, B and C as one document.

    The Form 1295 page offers a single download for the whole filing as
    well as the three individual schedules, because that is how a council
    actually hands it over -- a trustee does not want three separate PDFs
    to staple together. Each schedule keeps its own masthead and starts a
    new page, matching the paper form's structure.
    """
    from reportlab.platypus import PageBreak
    parts = [
        build_schedule_a_pdf(org, schedule_a, submission, _story_only=True),
        build_schedule_b_pdf(org, schedule_b, submission, _story_only=True),
        build_schedule_c_pdf(org, schedule_c, submission, _story_only=True),
    ]

    def _story(story, styles):
        for i, part in enumerate(parts):
            if i:
                story.append(PageBreak())
            part(story, styles)

    return _build(_story, org)
"""
Financial Reports Blueprint
Handles all financial report routes
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from models import db, Project, JournalEntry, ChartOfAccounts
from services.reports import FinancialReports
from services.usage_service import log_event
from datetime import date
from sqlalchemy import func

# Create the blueprint
reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


# ==================== REPORTS ====================


def _get_available_years(org_id):
    """Return a list of years (int) which have Posted JournalEntry rows for the org"""
    # Use SQLite strftime or SQL extract depending on dialect
    try:
        dialect = db.engine.dialect.name
        if dialect == 'postgresql' or dialect == 'mysql':
            years_q = db.session.query(func.extract('year', JournalEntry.entry_date).label('year'))\
                .join(Project, JournalEntry.project_id == Project.id)\
                .filter(Project.organization_id == org_id, JournalEntry.status == 'Posted')\
                .distinct().order_by(func.extract('year', JournalEntry.entry_date).desc()).all()
            years = [int(y[0]) for y in years_q if y[0]]
        else:
            years_q = db.session.query(func.strftime('%Y', JournalEntry.entry_date).label('year'))\
                .join(Project, JournalEntry.project_id == Project.id)\
                .filter(Project.organization_id == org_id, JournalEntry.status == 'Posted')\
                .distinct().order_by(func.strftime('%Y', JournalEntry.entry_date).desc()).all()
            years = [int(y[0]) for y in years_q if y[0]]
    except Exception:
        years = []
    
    # Remove any duplicates and sort descending (avoid using list() due to name shadowing)
    years = sorted([y for y in set(years)], reverse=True)
    return years


@reports_bp.route('/')
@login_required
def index():
    """Display reports menu"""
    return render_template('reports.html')


@reports_bp.route('/balance-sheet')
@login_required
def balance_sheet():
    """Display balance sheet report"""
    year_param = request.args.get('year', None, type=int)
    
    # Get available years
    available_years = _get_available_years(current_user.organization_id)
    
    # Determine year to use
    if year_param is None:
        if current_user.default_report_year and int(current_user.default_report_year) in available_years:
            year = int(current_user.default_report_year)
        else:
            latest_year = db.session.query(func.max(func.extract('year', JournalEntry.entry_date)))                .join(Project, JournalEntry.project_id == Project.id)                .filter(Project.organization_id == current_user.organization_id, JournalEntry.status == 'Posted')                .scalar()
            try:
                year = int(latest_year) if latest_year else date.today().year
            except Exception:
                year = date.today().year
    else:
        year = year_param
    
    # Balance sheet is as of December 31 of the selected year
    as_of_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.balance_sheet_detailed(as_of_date)
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'balance_sheet', 'year': year})

    # Debugging support
    if request.args.get('debug') == '1' or request.args.get('format') == 'json':
        current_app.logger.info(f"Balance sheet debug for org={current_user.organization_id} date={as_of_date}")
        return jsonify(data)

    current_app.logger.debug(f"Balance sheet for org={current_user.organization_id} date={as_of_date}")

    return render_template('balance_sheet.html', data=data, year=year, available_years=available_years)


@reports_bp.route('/income-statement')
@login_required
def income_statement():
    """Display income statement report"""
    # If the caller provides a year explicitly, use it; otherwise, prefer the user's default only if it has data, else default to the most recent year with posted data
    year_param = request.args.get('year', None, type=int)

    # compute available years early so we can validate a saved default
    available_years = _get_available_years(current_user.organization_id)

    if year_param is None:
        if current_user.default_report_year and int(current_user.default_report_year) in available_years:
            year = int(current_user.default_report_year)
            current_app.logger.debug(f"Using user default year={year} for org={current_user.organization_id}")
        else:
            # Query for the latest year which has posted journal entries for this organization
            # FIXED: Changed from strftime to extract for PostgreSQL compatibility
            latest_year = db.session.query(func.max(func.extract('year', JournalEntry.entry_date))).join(Project, JournalEntry.project_id == Project.id).filter(Project.organization_id == current_user.organization_id, JournalEntry.status == 'Posted').scalar()
            try:
                year = int(latest_year) if latest_year else date.today().year
            except Exception:
                year = date.today().year
    else:
        year = year_param

    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    # Available years for UI dropdown
    available_years = _get_available_years(current_user.organization_id)

    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.income_statement(start_date, end_date)
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'income_statement', 'year': year})

    # Debugging support: return JSON if requested and log counts
    if request.args.get('debug') == '1' or request.args.get('format') == 'json':
        current_app.logger.info(f"Income statement debug for org={current_user.organization_id} year={year} -> revenues={len(data.get('revenues', {}).get('accounts', []))}, expenses={len(data.get('expenses', {}).get('accounts', []))}")
        return jsonify(data)

    current_app.logger.debug(f"Income statement for org={current_user.organization_id} year={year} -> revenues={len(data.get('revenues', {}).get('accounts', []))}, expenses={len(data.get('expenses', {}).get('accounts', []))}")

    return render_template('income_statement.html', data=data, year=year, available_years=available_years)


@reports_bp.route('/cash-flow')
@login_required
def cash_flow():
    """Display cash flow statement report"""
    year_param = request.args.get('year', None, type=int)

    # compute available years early so we can validate a saved default
    available_years = _get_available_years(current_user.organization_id)

    if year_param is None:
        if current_user.default_report_year and int(current_user.default_report_year) in available_years:
            year = int(current_user.default_report_year)
        else:
            # FIXED: Changed from strftime to extract for PostgreSQL compatibility
            latest_year = db.session.query(func.max(func.extract('year', JournalEntry.entry_date))).join(Project, JournalEntry.project_id == Project.id).filter(Project.organization_id == current_user.organization_id, JournalEntry.status == 'Posted').scalar()
            try:
                year = int(latest_year) if latest_year else date.today().year
            except Exception:
                year = date.today().year
    else:
        year = year_param

    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'

    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.cash_flow_statement(start_date, end_date)
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'cash_flow', 'year': year})

    if request.args.get('debug') == '1' or request.args.get('format') == 'json':
        current_app.logger.info(f"Cash flow debug for org={current_user.organization_id} year={year} -> net_change={data.get('net_change_in_cash')}")
        return jsonify(data)

    current_app.logger.debug(f"Cash flow for org={current_user.organization_id} year={year} -> net_change={data.get('net_change_in_cash')}")

    return render_template('cash_flow.html', data=data, year=year, available_years=available_years)

@reports_bp.route('/functional-expenses')
@login_required
def functional_expenses():
    """Display functional expenses report"""
    year_param = request.args.get('year', None, type=int)
    
    # Compute available years early so we can validate a saved default
    available_years = _get_available_years(current_user.organization_id)
    
    if year_param is None:
        if current_user.default_report_year and int(current_user.default_report_year) in available_years:
            year = int(current_user.default_report_year)
        else:
            # FIXED: Changed from strftime to extract for PostgreSQL compatibility
            latest_year = db.session.query(func.max(func.extract('year', JournalEntry.entry_date))).join(Project, JournalEntry.project_id == Project.id).filter(Project.organization_id == current_user.organization_id, JournalEntry.status == 'Posted').scalar()
            try:
                year = int(latest_year) if latest_year else date.today().year
            except Exception:
                year = date.today().year
    else:
        year = year_param

    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'

    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.functional_expenses(start_date, end_date)
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'functional_expenses', 'year': year})

    if request.args.get('debug') == '1' or request.args.get('format') == 'json':
        current_app.logger.info(f"Functional expenses debug for org={current_user.organization_id} year={year} -> total_expenses={data.get('total_expenses')}")
        return jsonify(data)

    current_app.logger.debug(f"Functional expenses for org={current_user.organization_id} year={year} -> total_expenses={data.get('total_expenses')}")

    return render_template('functional_expenses.html', data=data, year=year, available_years=available_years)
# ==================== PDF EXPORTS ====================
#
# These replace the window.print() buttons the report pages used to carry.
# A browser print produces the application's own chrome -- sidebar, nav,
# filter controls -- around the numbers, which is a screenshot of a tool
# rather than a financial statement. Each route below renders the same
# data the page renders, through the shared branded document chrome in
# services/pdf_branding.py.
#
# The year comes from the query string, which the page always supplies via
# the PDF button, so the document matches whatever the reader is looking
# at rather than silently defaulting to a different year.

def _pdf_response(filename, buffer):
    from flask import Response
    response = Response(buffer.getvalue(), mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


def _pdf_year():
    year = request.args.get('year', None, type=int)
    if year:
        return year
    available = _get_available_years(current_user.organization_id)
    return available[0] if available else date.today().year


@reports_bp.route('/balance-sheet.pdf')
@login_required
def balance_sheet_pdf():
    from services.financial_reports_pdf import build_balance_sheet_pdf
    year = _pdf_year()
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.balance_sheet_detailed(f'{year}-12-31')
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'balance_sheet_pdf', 'year': year})
    return _pdf_response(f'statement-of-financial-position-{year}.pdf',
                         build_balance_sheet_pdf(current_user.organization, data, year))


@reports_bp.route('/income-statement.pdf')
@login_required
def income_statement_pdf():
    from services.financial_reports_pdf import build_income_statement_pdf
    year = _pdf_year()
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.income_statement(f'{year}-01-01', f'{year}-12-31')
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'income_statement_pdf', 'year': year})
    return _pdf_response(f'statement-of-activities-{year}.pdf',
                         build_income_statement_pdf(current_user.organization, data, year))


@reports_bp.route('/cash-flow.pdf')
@login_required
def cash_flow_pdf():
    from services.financial_reports_pdf import build_cash_flow_pdf
    year = _pdf_year()
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.cash_flow_statement(f'{year}-01-01', f'{year}-12-31')
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'cash_flow_pdf', 'year': year})
    return _pdf_response(f'statement-of-cash-flows-{year}.pdf',
                         build_cash_flow_pdf(current_user.organization, data, year))


@reports_bp.route('/functional-expenses.pdf')
@login_required
def functional_expenses_pdf():
    from services.financial_reports_pdf import build_functional_expenses_pdf
    year = _pdf_year()
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.functional_expenses(f'{year}-01-01', f'{year}-12-31')
    log_event('report.generated', organization_id=current_user.organization_id,
              user_id=current_user.id, meta={'report': 'functional_expenses_pdf', 'year': year})
    return _pdf_response(f'statement-of-functional-expenses-{year}.pdf',
                         build_functional_expenses_pdf(current_user.organization, data, year))

"""
Financial Reports Blueprint
Handles all financial report routes
"""

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from models import db
from reports import FinancialReports
from datetime import date

# Create the blueprint
reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


# ==================== REPORTS ====================

@reports_bp.route('/')
@login_required
def list():
    """Display reports menu"""
    return render_template('reports.html')


@reports_bp.route('/balance-sheet')
@login_required
def balance_sheet():
    """Display balance sheet report"""
    as_of_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.balance_sheet(as_of_date)
    return render_template('balance_sheet.html', data=data, as_of_date=as_of_date)


@reports_bp.route('/income-statement')
@login_required
def income_statement():
    """Display income statement report"""
    year = request.args.get('year', date.today().year, type=int)
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.income_statement(start_date, end_date)
    return render_template('income_statement.html', data=data, year=year)


@reports_bp.route('/cash-flow')
@login_required
def cash_flow():
    """Display cash flow statement report"""
    year = request.args.get('year', date.today().year, type=int)
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.cash_flow_statement(start_date, end_date)
    return render_template('cash_flow.html', data=data, year=year)


@reports_bp.route('/functional-expenses')
@login_required
def functional_expenses():
    """Display functional expenses report"""
    year = request.args.get('year', date.today().year, type=int)
    start_date = f'{year}-01-01'
    end_date = f'{year}-12-31'
    
    reports = FinancialReports(db.session, current_user.organization_id)
    data = reports.functional_expenses(start_date, end_date)
    return render_template('functional_expenses.html', data=data, year=year)

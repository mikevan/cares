"""
Comprehensive Sample Data Loader for CARES
Demonstrates full nonprofit accounting capabilities including:
- Multiple asset types (cash, receivables, fixed assets, investments)
- Liabilities (loans, payables, deferred revenue)
- Diverse revenue sources (donations, grants, program fees, events)
- Various expense categories across programs
- Depreciation
- Restricted and unrestricted funds
"""

from app import app, db
from models import Organization, User, Project, Member, JournalEntry, JournalEntryLine, ChartOfAccounts, Vendor, Invoice, InvoicePayment
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text
import random

def clear_existing_data():
    """Clear existing sample data"""
    print("Clearing existing data...")
    JournalEntryLine.query.delete()
    JournalEntry.query.delete()
    InvoicePayment.query.delete()
    Invoice.query.delete()
    Vendor.query.delete()
    
    # Delete junction tables first (foreign key constraints)
    db.session.execute(text("DELETE FROM project_members"))
    db.session.execute(text("DELETE FROM project_leaders"))
    
    Member.query.delete()
    Project.query.delete()
    
    # Keep the first user and organization
    User.query.filter(User.id > 1).delete()
    Organization.query.filter(Organization.id > 1).delete()
    
    db.session.commit()
    print("Existing data cleared.")

def create_members(org_id):
    """Create sample members"""
    print("Creating members...")
    members_data = [
        {'name': 'John Smith', 'email': 'john.smith@example.com', 'phone': '555-0101'},
        {'name': 'Mary Johnson', 'email': 'mary.johnson@example.com', 'phone': '555-0102'},
        {'name': 'Robert Williams', 'email': 'robert.williams@example.com', 'phone': '555-0103'},
        {'name': 'Patricia Brown', 'email': 'patricia.brown@example.com', 'phone': '555-0104'},
        {'name': 'Michael Jones', 'email': 'michael.jones@example.com', 'phone': '555-0105'},
        {'name': 'Linda Garcia', 'email': 'linda.garcia@example.com', 'phone': '555-0106'},
        {'name': 'David Miller', 'email': 'david.miller@example.com', 'phone': '555-0107'},
        {'name': 'Barbara Davis', 'email': 'barbara.davis@example.com', 'phone': '555-0108'},
        {'name': 'William Rodriguez', 'email': 'william.rodriguez@example.com', 'phone': '555-0109'},
        {'name': 'Elizabeth Martinez', 'email': 'elizabeth.martinez@example.com', 'phone': '555-0110'},
    ]
    
    for member_data in members_data:
        member = Member(
            name=member_data['name'],
            email=member_data['email'],
            phone=member_data['phone'],
            organization_id=org_id
        )
        db.session.add(member)
    
    db.session.commit()
    print(f"Created {len(members_data)} members.")


def create_comprehensive_projects(org_id):
    """Create diverse projects demonstrating different funding and activities"""
    projects = [
        {
            'name': 'Youth Education Program',
            'description': 'After-school tutoring and mentorship for underserved youth',
            'budget': Decimal('75000.00'),
            'status': 'Active'
        },
        {
            'name': 'Community Food Bank',
            'description': 'Weekly food distribution to families in need',
            'budget': Decimal('125000.00'),
            'status': 'Active'
        },
        {
            'name': 'Senior Wellness Center',
            'description': 'Health and wellness activities for seniors',
            'budget': Decimal('85000.00'),
            'status': 'Active'
        },
        {
            'name': 'Emergency Housing Assistance',
            'description': 'Temporary housing support for homeless families',
            'budget': Decimal('150000.00'),
            'status': 'Active'
        },
        {
            'name': 'Job Training Initiative',
            'description': 'Skills training and job placement services',
            'budget': Decimal('95000.00'),
            'status': 'Active'
        },
        {
            'name': 'Annual Fundraising Gala',
            'description': 'Major fundraising event for general operations',
            'budget': Decimal('45000.00'),
            'status': 'Active'
        },
        {
            'name': 'General Operations',
            'description': 'Day-to-day organizational operations',
            'budget': Decimal('200000.00'),
            'status': 'Active'
        }
    ]
    
    created_projects = []
    for proj_data in projects:
        project = Project(
            name=proj_data['name'],
            description=proj_data['description'],
            budget=proj_data['budget'],
            status=proj_data['status'],
            organization_id=org_id
        )
        db.session.add(project)
        created_projects.append(project)
    
    db.session.commit()
    print(f"Created {len(created_projects)} projects.")
    return created_projects

def create_transaction(project, date, description, reference, lines, user_id=1):
    """Helper to create a journal entry with lines"""
    entry = JournalEntry(
        entry_date=date,
        description=description,
        reference_number=reference,
        project_id=project.id,
        status='Posted',
        created_by=user_id
    )
    db.session.add(entry)
    db.session.flush()
    
    for line_data in lines:
        account = ChartOfAccounts.query.filter_by(account_number=line_data['account']).first()
        if account:
            line = JournalEntryLine(
                journal_entry_id=entry.id,
                account_id=account.id,
                debit_amount=line_data.get('debit', 0),
                credit_amount=line_data.get('credit', 0),
                memo=line_data.get('memo', description)
            )
            db.session.add(line)

def load_opening_balances(projects):
    """Load opening balances - organization starts with initial funding"""
    print("Loading opening balances...")
    general_ops = [p for p in projects if p.name == 'General Operations'][0]
    base_date = datetime(2024, 1, 1).date()
    
    # Initial endowment/funding
    create_transaction(
        general_ops,
        base_date,
        "Initial organizational funding",
        "INIT-001",
        [
            {'account': '1010', 'debit': 150000, 'memo': 'Starting cash - unrestricted'},
            {'account': '3100', 'credit': 150000, 'memo': 'Net assets without donor restrictions'}
        ]
    )
    
    # Restricted grant received (not yet spent)
    create_transaction(
        general_ops,
        base_date,
        "Multi-year foundation grant for program expansion",
        "GRANT-001",
        [
            {'account': '1010', 'debit': 100000, 'memo': 'Grant cash received'},
            {'account': '3200', 'credit': 100000, 'memo': 'Net assets with donor restrictions'}
        ]
    )
    
    db.session.commit()
    print("Opening balances loaded.")

def load_asset_transactions(projects):
    """Load transactions that create various assets"""
    print("Loading asset transactions...")
    general_ops = [p for p in projects if p.name == 'General Operations'][0]
    youth_ed = [p for p in projects if p.name == 'Youth Education Program'][0]
    
    # Purchase office equipment
    create_transaction(
        general_ops,
        datetime(2024, 1, 15).date(),
        "Purchase computers and office equipment",
        "PO-1001",
        [
            {'account': '1410', 'debit': 15000, 'memo': 'Computer equipment'},
            {'account': '1010', 'credit': 15000, 'memo': 'Cash payment'}
        ]
    )
    
    # Purchase furniture
    create_transaction(
        general_ops,
        datetime(2024, 1, 20).date(),
        "Purchase office furniture",
        "PO-1002",
        [
            {'account': '1420', 'debit': 8000, 'memo': 'Office furniture'},
            {'account': '1010', 'credit': 8000, 'memo': 'Cash payment'}
        ]
    )
    
    # Purchase vehicle for program activities
    create_transaction(
        youth_ed,
        datetime(2024, 2, 1).date(),
        "Purchase van for youth program transportation",
        "PO-1003",
        [
            {'account': '1430', 'debit': 35000, 'memo': 'Program vehicle'},
            {'account': '1010', 'credit': 10000, 'memo': 'Down payment'},
            {'account': '2310', 'credit': 25000, 'memo': 'Vehicle loan'}
        ]
    )
    
    # Grant receivable (promised but not yet received)
    create_transaction(
        youth_ed,
        datetime(2024, 3, 1).date(),
        "City grant awarded for youth education",
        "GRANT-002",
        [
            {'account': '1210', 'debit': 50000, 'memo': 'Grant receivable'},
            {'account': '4030', 'credit': 50000, 'memo': 'Foundation grant revenue'}
        ]
    )
    
    # Investment in short-term securities
    create_transaction(
        general_ops,
        datetime(2024, 3, 15).date(),
        "Purchase short-term investments",
        "INV-001",
        [
            {'account': '1310', 'debit': 25000, 'memo': 'Short-term investments'},
            {'account': '1010', 'credit': 25000, 'memo': 'Cash to investments'}
        ]
    )
    
    db.session.commit()
    print("Asset transactions loaded.")

def load_liability_transactions(projects):
    """Load transactions creating liabilities"""
    print("Loading liability transactions...")
    general_ops = [p for p in projects if p.name == 'General Operations'][0]
    food_bank = [p for p in projects if p.name == 'Community Food Bank'][0]
    
    # Accounts payable - supplies purchased on credit
    create_transaction(
        food_bank,
        datetime(2024, 4, 1).date(),
        "Purchase food supplies on account",
        "INV-2001",
        [
            {'account': '5320', 'debit': 12000, 'memo': 'Food supplies expense'},
            {'account': '2110', 'credit': 12000, 'memo': 'Accounts payable'}
        ]
    )
    
    # Deferred revenue - grant received for future program
    create_transaction(
        general_ops,
        datetime(2024, 4, 15).date(),
        "Grant received for 2025 program (deferred)",
        "GRANT-003",
        [
            {'account': '1010', 'debit': 30000, 'memo': 'Cash received'},
            {'account': '2410', 'credit': 30000, 'memo': 'Deferred revenue - future program'}
        ]
    )
    
    # Accrued payroll
    create_transaction(
        general_ops,
        datetime(2024, 4, 30).date(),
        "Accrue April payroll (not yet paid)",
        "PAY-001",
        [
            {'account': '5010', 'debit': 18000, 'memo': 'Salary expense'},
            {'account': '2210', 'credit': 18000, 'memo': 'Accrued salaries payable'}
        ]
    )
    
    # Line of credit draw
    create_transaction(
        general_ops,
        datetime(2024, 5, 1).date(),
        "Draw on line of credit for operations",
        "LOC-001",
        [
            {'account': '1010', 'debit': 20000, 'memo': 'Cash from LOC'},
            {'account': '2320', 'credit': 20000, 'memo': 'Line of credit balance'}
        ]
    )
    
    db.session.commit()
    print("Liability transactions loaded.")

def load_revenue_transactions(projects):
    """Load diverse revenue transactions"""
    print("Loading revenue transactions...")
    
    youth_ed = [p for p in projects if p.name == 'Youth Education Program'][0]
    food_bank = [p for p in projects if p.name == 'Community Food Bank'][0]
    senior = [p for p in projects if p.name == 'Senior Wellness Center'][0]
    housing = [p for p in projects if p.name == 'Emergency Housing Assistance'][0]
    job_train = [p for p in projects if p.name == 'Job Training Initiative'][0]
    gala = [p for p in projects if p.name == 'Annual Fundraising Gala'][0]
    general = [p for p in projects if p.name == 'General Operations'][0]
    
    revenues = [
        # Individual donations
        (general, datetime(2024, 5, 15), "Individual donor contributions", "DON-001", '4010', 15000),
        (youth_ed, datetime(2024, 5, 20), "Individual donations for education program", "DON-002", '4010', 8500),
        (housing, datetime(2024, 6, 1), "Major gift for housing assistance", "DON-003", '4010', 25000),
        
        # Corporate contributions
        (food_bank, datetime(2024, 6, 10), "Corporate sponsorship - Local Bank", "CORP-001", '4020', 10000),
        (job_train, datetime(2024, 6, 15), "Corporate training partnership", "CORP-002", '4020', 15000),
        
        # Foundation grants
        (senior, datetime(2024, 7, 1), "Senior services grant", "GRANT-004", '4030', 20000),
        (youth_ed, datetime(2024, 7, 15), "Education foundation grant", "GRANT-005", '4030', 30000),
        
        # Government grants
        (housing, datetime(2024, 8, 1), "HUD emergency housing grant", "GGRANT-001", '4040', 75000),
        (job_train, datetime(2024, 8, 15), "Workforce development grant", "GGRANT-002", '4040', 40000),
        
        # Membership dues
        (general, datetime(2024, 9, 1), "Annual membership dues", "DUES-001", '4110', 12000),
        
        # Program service revenue
        (senior, datetime(2024, 9, 15), "Senior wellness program fees", "FEES-001", '4120', 5500),
        (job_train, datetime(2024, 9, 20), "Job training program fees", "FEES-002", '4120', 8000),
        
        # Special event revenue
        (gala, datetime(2024, 10, 15), "Annual gala ticket sales", "EVENT-001", '4210', 35000),
        (gala, datetime(2024, 10, 15), "Gala auction proceeds", "EVENT-002", '4210', 18000),
        
        # In-kind donations
        (food_bank, datetime(2024, 10, 20), "In-kind food donations", "INKIND-001", '4310', 22000),
    ]
    
    for project, date, desc, ref, account, amount in revenues:
        create_transaction(
            project,
            date,
            desc,
            ref,
            [
                {'account': '1010', 'debit': amount, 'memo': 'Cash received'},
                {'account': account, 'credit': amount, 'memo': desc}
            ]
        )
    
    # Receive the grant receivable
    create_transaction(
        youth_ed,
        datetime(2024, 10, 25).date(),
        "Receive city grant (previously recorded as receivable)",
        "GRANT-002-PAY",
        [
            {'account': '1010', 'debit': 50000, 'memo': 'Cash received'},
            {'account': '1210', 'credit': 50000, 'memo': 'Clear receivable'}
        ]
    )
    
    db.session.commit()
    print("Revenue transactions loaded.")

def load_expense_transactions(projects):
    """Load diverse operating expenses"""
    print("Loading expense transactions...")
    
    youth_ed = [p for p in projects if p.name == 'Youth Education Program'][0]
    food_bank = [p for p in projects if p.name == 'Community Food Bank'][0]
    senior = [p for p in projects if p.name == 'Senior Wellness Center'][0]
    housing = [p for p in projects if p.name == 'Emergency Housing Assistance'][0]
    job_train = [p for p in projects if p.name == 'Job Training Initiative'][0]
    gala = [p for p in projects if p.name == 'Annual Fundraising Gala'][0]
    general = [p for p in projects if p.name == 'General Operations'][0]
    
    expenses = [
        # Salaries
        (youth_ed, datetime(2024, 5, 31), "May salaries - program staff", "PAY-101", '5010', 15000),
        (food_bank, datetime(2024, 5, 31), "May salaries - food bank", "PAY-102", '5010', 12000),
        (senior, datetime(2024, 5, 31), "May salaries - wellness center", "PAY-103", '5010', 10000),
        (housing, datetime(2024, 5, 31), "May salaries - housing team", "PAY-104", '5010', 14000),
        (job_train, datetime(2024, 5, 31), "May salaries - training staff", "PAY-105", '5010', 11000),
        (general, datetime(2024, 5, 31), "May salaries - admin staff", "PAY-106", '5110', 20000),
        
        # Payroll taxes
        (general, datetime(2024, 5, 31), "May payroll taxes", "TAX-101", '5020', 8200),
        
        # Employee benefits
        (general, datetime(2024, 5, 31), "May employee health insurance", "BEN-101", '5030', 6500),
        
        # Rent
        (general, datetime(2024, 6, 1), "June office rent", "RENT-601", '5210', 4500),
        
        # Utilities
        (general, datetime(2024, 6, 15), "Utilities - electric, water, gas", "UTIL-601", '5220', 1200),
        
        # Office supplies
        (general, datetime(2024, 7, 1), "Office supplies purchase", "SUP-701", '5310', 850),
        
        # Program supplies
        (youth_ed, datetime(2024, 7, 10), "Educational materials and books", "SUP-702", '5320', 3200),
        (senior, datetime(2024, 7, 15), "Wellness program supplies", "SUP-703", '5320', 1800),
        (job_train, datetime(2024, 7, 20), "Training materials", "SUP-704", '5320', 2400),
        
        # Professional fees
        (general, datetime(2024, 8, 1), "Legal fees", "PROF-801", '5410', 2500),
        (general, datetime(2024, 8, 15), "Accounting services", "PROF-802", '5410', 3000),
        
        # Marketing
        (gala, datetime(2024, 9, 1), "Gala advertising and promotion", "MKT-901", '5510', 4500),
        (general, datetime(2024, 9, 15), "Website hosting and marketing", "MKT-902", '5510', 1200),
        
        # Insurance
        (general, datetime(2024, 10, 1), "General liability insurance", "INS-1001", '5610', 5000),
        
        # Equipment maintenance
        (general, datetime(2024, 10, 15), "Computer equipment repairs", "MAINT-1001", '5710', 800),
        
        # Vehicle expenses
        (youth_ed, datetime(2024, 10, 20), "Van fuel and maintenance", "VEH-1001", '5720', 650),
        
        # Gala direct costs
        (gala, datetime(2024, 10, 10), "Gala venue rental", "GALA-1001", '5320', 8000),
        (gala, datetime(2024, 10, 12), "Gala catering", "GALA-1002", '5320', 12000),
        
        # Client assistance (housing)
        (housing, datetime(2024, 11, 1), "Emergency housing payments", "ASSIST-1101", '5320', 15000),
        (housing, datetime(2024, 11, 15), "Client utility assistance", "ASSIST-1102", '5320', 3500),
    ]
    
    for project, date, desc, ref, account, amount in expenses:
        create_transaction(
            project,
            date,
            desc,
            ref,
            [
                {'account': account, 'debit': amount, 'memo': desc},
                {'account': '1010', 'credit': amount, 'memo': 'Cash payment'}
            ]
        )
    
    # Pay the accounts payable
    create_transaction(
        food_bank,
        datetime(2024, 11, 20).date(),
        "Pay food supplier invoice",
        "PAY-1120",
        [
            {'account': '2110', 'debit': 12000, 'memo': 'Clear payable'},
            {'account': '1010', 'credit': 12000, 'memo': 'Cash payment'}
        ]
    )
    
    # Pay accrued payroll
    create_transaction(
        general,
        datetime(2024, 5, 5).date(),
        "Pay April accrued salaries",
        "PAY-505",
        [
            {'account': '2210', 'debit': 18000, 'memo': 'Clear accrued payroll'},
            {'account': '1010', 'credit': 18000, 'memo': 'Cash payment'}
        ]
    )
    
    db.session.commit()
    print("Expense transactions loaded.")

def load_depreciation(projects):
    """Load depreciation entries"""
    print("Loading depreciation...")
    general = [p for p in projects if p.name == 'General Operations'][0]
    
    # Monthly depreciation for the year
    depreciation_entries = [
        (datetime(2024, 1, 31), "January depreciation", 450),
        (datetime(2024, 2, 29), "February depreciation", 450),
        (datetime(2024, 3, 31), "March depreciation", 450),
        (datetime(2024, 4, 30), "April depreciation", 450),
        (datetime(2024, 5, 31), "May depreciation", 450),
        (datetime(2024, 6, 30), "June depreciation", 450),
        (datetime(2024, 7, 31), "July depreciation", 450),
        (datetime(2024, 8, 31), "August depreciation", 450),
        (datetime(2024, 9, 30), "September depreciation", 450),
        (datetime(2024, 10, 31), "October depreciation", 450),
        (datetime(2024, 11, 30), "November depreciation", 450),
    ]
    
    for date, desc, amount in depreciation_entries:
        create_transaction(
            general,
            date,
            desc,
            f"DEP-{date.strftime('%m%y')}",
            [
                {'account': '5810', 'debit': amount, 'memo': 'Depreciation expense'},
                {'account': '1590', 'credit': amount, 'memo': 'Accumulated depreciation'}
            ]
        )
    
    db.session.commit()
    print("Depreciation loaded.")

def load_loan_payments(projects):
    """Load loan payment entries"""
    print("Loading loan payments...")
    youth_ed = [p for p in projects if p.name == 'Youth Education Program'][0]
    general = [p for p in projects if p.name == 'General Operations'][0]
    
    # Vehicle loan payments (principal + interest)
    loan_payments = [
        (datetime(2024, 3, 1), 500, 80),
        (datetime(2024, 4, 1), 505, 75),
        (datetime(2024, 5, 1), 510, 70),
        (datetime(2024, 6, 1), 515, 65),
        (datetime(2024, 7, 1), 520, 60),
        (datetime(2024, 8, 1), 525, 55),
        (datetime(2024, 9, 1), 530, 50),
        (datetime(2024, 10, 1), 535, 45),
        (datetime(2024, 11, 1), 540, 40),
    ]
    
    for date, principal, interest in loan_payments:
        create_transaction(
            youth_ed,
            date,
            f"Vehicle loan payment - {date.strftime('%B')}",
            f"LOAN-{date.strftime('%m%y')}",
            [
                {'account': '2310', 'debit': principal, 'memo': 'Loan principal'},
                {'account': '5910', 'debit': interest, 'memo': 'Interest expense'},
                {'account': '1010', 'credit': principal + interest, 'memo': 'Cash payment'}
            ]
        )
    
    # Line of credit payment
    create_transaction(
        general,
        datetime(2024, 11, 15).date(),
        "Partial LOC repayment",
        "LOC-1115",
        [
            {'account': '2320', 'debit': 5000, 'memo': 'LOC principal payment'},
            {'account': '5910', 'debit': 150, 'memo': 'LOC interest'},
            {'account': '1010', 'credit': 5150, 'memo': 'Cash payment'}
        ]
    )
    
    db.session.commit()
    print("Loan payments loaded.")

def load_restricted_fund_transactions(projects):
    """Load transactions showing restricted fund activity"""
    print("Loading restricted fund transactions...")
    housing = [p for p in projects if p.name == 'Emergency Housing Assistance'][0]
    
    # Release restriction as funds are spent
    create_transaction(
        housing,
        datetime(2024, 11, 30).date(),
        "Release donor restrictions - housing program expenses incurred",
        "RESTRICT-1130",
        [
            {'account': '3200', 'debit': 50000, 'memo': 'Release net assets with restrictions'},
            {'account': '3100', 'credit': 50000, 'memo': 'Reclassify to unrestricted'}
        ]
    )
    
    db.session.commit()
    print("Restricted fund transactions loaded.")

def create_vendors(org_id):
    """Create sample vendors for AP demonstration"""
    print("Creating vendors...")
    vendors_data = [
        {'name': 'Acme Office Supplies', 'contact_name': 'Tom Harris',
         'email': 'tom@acmeoffice.example.com', 'phone': '555-0201',
         'payment_terms': 'Net30', 'is_1099': False},
        {'name': 'City Printing Co.', 'contact_name': 'Susan Lee',
         'email': 'susan@cityprinting.example.com', 'phone': '555-0202',
         'payment_terms': 'Net15', 'is_1099': True},
        {'name': 'St. Michael Hall Rental', 'contact_name': 'Fr. James',
         'email': 'rental@stmichael.example.com', 'phone': '555-0203',
         'payment_terms': 'Due on Receipt', 'is_1099': False},
        {'name': 'Community Catering LLC', 'contact_name': 'Maria Torres',
         'email': 'maria@commcatering.example.com', 'phone': '555-0204',
         'payment_terms': 'Net30', 'is_1099': True},
        {'name': 'Reliable Maintenance Inc.', 'contact_name': 'Dave Kowalski',
         'email': 'dave@reliablemaint.example.com', 'phone': '555-0205',
         'payment_terms': 'Net30', 'is_1099': True},
    ]

    vendors = []
    for v in vendors_data:
        vendor = Vendor(organization_id=org_id, **v)
        db.session.add(vendor)
        vendors.append(vendor)

    db.session.commit()
    print(f"  Created {len(vendors)} vendors.")
    return vendors


def load_ap_transactions(projects, vendors):
    """Create sample AP invoices in various states"""
    print("Loading AP transactions...")

    admin_user = User.query.first()
    project = projects[0]

    acc_5010 = ChartOfAccounts.query.filter_by(account_number='5010').first()
    acc_5710 = ChartOfAccounts.query.filter_by(account_number='5710').first()
    acc_5610 = ChartOfAccounts.query.filter_by(account_number='5610').first()

    from services.ap_service import create_invoice, record_payment
    from decimal import Decimal
    from datetime import date, timedelta

    samples = [
        # (vendor_idx, gl_account, invoice_number, days_ago_issued, days_until_due, amount, pay_amount)
        (0, acc_5010, 'INV-2001', 45, -15, Decimal('235.00'), Decimal('235.00')),   # Paid
        (1, acc_5710, 'INV-2002', 20,  10, Decimal('180.00'), None),                # Open, not due
        (2, acc_5010, 'INV-2003', 60, -35, Decimal('500.00'), None),                # Open, overdue
        (3, acc_5710, 'INV-2004', 10,  20, Decimal('1200.00'), Decimal('600.00')),  # Partial
        (4, acc_5610, 'INV-2005', 30,   0, Decimal('85.00'),  None),                # Open, due today
    ]

    today = date.today()
    for vendor_idx, gl_acc, inv_num, days_ago, days_until_due, amount, pay_amount in samples:
        if not gl_acc:
            continue
        inv_date = today - timedelta(days=days_ago)
        due_date = today + timedelta(days=days_until_due)

        inv = create_invoice(
            organization_id=project.organization_id,
            vendor_id=vendors[vendor_idx].id,
            project_id=project.id,
            gl_account_number=gl_acc.account_number,
            gl_account_id=gl_acc.id,
            invoice_number=inv_num,
            invoice_date=inv_date,
            due_date=due_date,
            amount=amount,
            notes=f'Sample invoice {inv_num}',
            created_by=admin_user.id,
        )

        if pay_amount:
            record_payment(
                invoice=inv,
                payment_amount=pay_amount,
                payment_date=today,
                reference_number=f'CHK-{inv_num}',
                created_by=admin_user.id,
            )

    print(f"  Created {len(samples)} sample invoices.")

def main():
    """Main loader function"""
    print("\n=== CARES Comprehensive Data Loader ===\n")
        
    # Get or create organization
    org = Organization.query.first()
    if not org:
        print("No organization found. Please run init_db.py first.")
        return
        
    print(f"Loading data for organization: {org.name}\n")
        
    # Clear existing sample data
    clear_existing_data()
        
    # Create members
    create_members(org.id)
        
    # Create projects
    projects = create_comprehensive_projects(org.id)
    
    # Load all transaction types
    load_opening_balances(projects)
    load_asset_transactions(projects)
    load_liability_transactions(projects)
    load_revenue_transactions(projects)
    load_expense_transactions(projects)
    load_depreciation(projects)
    load_loan_payments(projects)
    load_restricted_fund_transactions(projects)
    vendors = create_vendors(org.id)
    load_ap_transactions(projects, vendors)
        
    print("\n=== Data Load Complete ===")
    print("\nSummary of loaded data:")
    print(f"- Members: {Member.query.count()}")
    print(f"- Projects: {len(projects)}")
    print(f"- Journal Entries: {JournalEntry.query.count()}")
    print(f"- Journal Entry Lines: {JournalEntryLine.query.count()}")
    print(f"- Vendors: {Vendor.query.count()}")
    print(f"- Invoices: {Invoice.query.count()}")
    print("\nThe system now demonstrates:")
    print("âœ“ Multiple asset types (cash, receivables, equipment, vehicles, investments)")
    print("âœ“ Various liabilities (payables, loans, deferred revenue, accrued expenses)")
    print("âœ“ Diverse revenue sources (donations, grants, fees, events)")
    print("âœ“ Comprehensive expenses across programs and administration")
    print("âœ“ Depreciation tracking")
    print("âœ“ Loan payments with principal and interest")
    print("âœ“ Restricted and unrestricted net assets")
    print("\nYou can now view complete financial statements showing the full capabilities!")

if __name__ == '__main__':
    with app.app_context():
        main()

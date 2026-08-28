#!/usr/bin/env python3
"""
Sample Data Loader for CARES
Creates realistic demonstration data including:
- Users in all roles (Admin, Treasurer, ProjectLeader, Member)
- Members (20 sample members)
- Projects (7 typical Council activities)
- Transactions (40+ entries over 6 months, all mapped to projects)
- Balanced financials showing healthy Council operations

Safe to run multiple times - checks for existing sample data.
"""

from app import app, db
from models import User, Organization, Member, Project, ChartOfAccounts, JournalEntry, JournalEntryLine
from services.project_service import assign_member
from datetime import datetime, timedelta
from decimal import Decimal
import random

# Sample data flags
SAMPLE_EMAIL_DOMAIN = "@sample-kofc.local"
SAMPLE_USERNAME_PREFIX = "demo_"

def data_already_loaded():
    """Check if sample data already exists"""
    sample_user = User.query.filter(User.username.like(f'{SAMPLE_USERNAME_PREFIX}%')).first()
    return sample_user is not None

def get_default_org():
    """Get the default organization (should exist from init_db)"""
    org = Organization.query.first()
    if not org:
        print("ERROR: No organization found. Run init_db.py first.")
        return None
    return org

def create_sample_users(org_id):
    """Create users in all roles for testing"""
    users = []
    
    # Admin user (in addition to default admin)
    admin = User(
        username=f"{SAMPLE_USERNAME_PREFIX}admin",
        email=f"admin{SAMPLE_EMAIL_DOMAIN}",
        role="Admin",
        organization_id=org_id,
        active=True
    )
    admin.set_password("demo123")
    users.append(admin)
    
    # Treasurer
    treasurer = User(
        username=f"{SAMPLE_USERNAME_PREFIX}treasurer",
        email=f"treasurer{SAMPLE_EMAIL_DOMAIN}",
        role="Treasurer",
        organization_id=org_id,
        active=True
    )
    treasurer.set_password("demo123")
    users.append(treasurer)
    
    # Project Leaders (2)
    for i in range(1, 3):
        leader = User(
            username=f"{SAMPLE_USERNAME_PREFIX}leader{i}",
            email=f"leader{i}{SAMPLE_EMAIL_DOMAIN}",
            role="ProjectLeader",
            organization_id=org_id,
            active=True
        )
        leader.set_password("demo123")
        users.append(leader)
    
    # Regular Members (2)
    for i in range(1, 3):
        member = User(
            username=f"{SAMPLE_USERNAME_PREFIX}member{i}",
            email=f"member{i}{SAMPLE_EMAIL_DOMAIN}",
            role="Member",
            organization_id=org_id,
            active=True
        )
        member.set_password("demo123")
        users.append(member)
    
    for user in users:
        db.session.add(user)
    
    db.session.flush()
    return users

def create_sample_members(org_id):
    """Create realistic sample members"""
    
    # Realistic sample member names
    knight_names = [
        ("James", "McCarthy", "123 Oak St", "Bentonville", "AR", "72712"),
        ("Robert", "O'Brien", "456 Maple Ave", "Rogers", "AR", "72756"),
        ("Michael", "Sullivan", "789 Pine Rd", "Springdale", "AR", "72762"),
        ("Thomas", "Murphy", "321 Elm St", "Fayetteville", "AR", "72701"),
        ("William", "Kelly", "654 Cedar Ln", "Bentonville", "AR", "72712"),
        ("David", "Ryan", "987 Birch Dr", "Rogers", "AR", "72758"),
        ("Joseph", "Connor", "147 Walnut St", "Springdale", "AR", "72764"),
        ("Daniel", "Walsh", "258 Ash Ave", "Bentonville", "AR", "72713"),
        ("Matthew", "Brennan", "369 Spruce Rd", "Fayetteville", "AR", "72703"),
        ("Anthony", "Fitzgerald", "741 Hickory Ln", "Rogers", "AR", "72756"),
        ("Mark", "Gallagher", "852 Willow Dr", "Springdale", "AR", "72762"),
        ("Steven", "Donovan", "963 Cherry St", "Bentonville", "AR", "72712"),
        ("Paul", "Callahan", "159 Poplar Ave", "Fayetteville", "AR", "72701"),
        ("Andrew", "Sheehan", "357 Magnolia Rd", "Rogers", "AR", "72758"),
        ("Kenneth", "McGrath", "486 Dogwood Ln", "Springdale", "AR", "72764"),
        ("Brian", "O'Donnell", "624 Sycamore Dr", "Bentonville", "AR", "72713"),
        ("George", "Reilly", "735 Cypress St", "Fayetteville", "AR", "72703"),
        ("Edward", "Quinn", "846 Redwood Ave", "Rogers", "AR", "72756"),
        ("Ronald", "Kennedy", "957 Oakwood Rd", "Springdale", "AR", "72762"),
        ("Timothy", "Doherty", "168 Pinewood Ln", "Bentonville", "AR", "72712"),
    ]
    
    members = []
    base_date = datetime.now() - timedelta(days=800)  # ~2 years ago
    
    for i, (first, last, addr, city, state, zip_code) in enumerate(knight_names):
        # Vary join dates
        join_date = base_date + timedelta(days=random.randint(0, 600))
        
        # Most active, a few inactive
        is_active = i < 17  # 17 active, 3 inactive
        
        member = Member(
            name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower()}@example.com",
            phone=f"479-555-{1000 + i:04d}",
            address=addr,
            city=city,
            state=state,
            zip_code=zip_code,
            join_date=join_date.date(),
            active=is_active,
            organization_id=org_id
        )
        members.append(member)
        db.session.add(member)
    
    db.session.flush()
    return members

def create_sample_projects(org_id, members):
    """Create typical service organization projects"""
    
    projects_data = [
        {
            "name": "Council Operations",
            "description": "General council operations, dues collection, and administrative expenses",
            "budget": Decimal("50000.00"),
            "status": "Active",
            "start_date": datetime(2024, 7, 1).date(),
            "leaders": 2,
            "volunteers": 5
        },
        {
            "name": "Annual Fish Fry",
            "description": "Lenten Friday fish fry fundraiser - community outreach and fellowship",
            "budget": Decimal("8000.00"),
            "status": "Active",
            "start_date": datetime(2025, 2, 14).date(),
            "end_date": datetime(2025, 3, 28).date(),
            "leaders": 2,
            "volunteers": 8
        },
        {
            "name": "Scholarship Fund",
            "description": "Annual scholarships for graduating high school seniors",
            "budget": Decimal("15000.00"),
            "status": "Active",
            "start_date": datetime(2024, 9, 1).date(),
            "leaders": 1,
            "volunteers": 3
        },
        {
            "name": "Community Service",
            "description": "Food bank support, highway cleanup, and local charity work",
            "budget": Decimal("5000.00"),
            "status": "Active",
            "start_date": datetime(2024, 7, 1).date(),
            "leaders": 2,
            "volunteers": 10
        },
        {
            "name": "Christmas Charity Drive",
            "description": "Toys for tots and family adoption program",
            "budget": Decimal("12000.00"),
            "status": "Completed",
            "start_date": datetime(2024, 11, 1).date(),
            "end_date": datetime(2024, 12, 24).date(),
            "leaders": 2,
            "volunteers": 6
        },
        {
            "name": "Building Maintenance",
            "description": "Council hall repairs, utilities, and building improvements",
            "budget": Decimal("10000.00"),
            "status": "Active",
            "start_date": datetime(2024, 7, 1).date(),
            "leaders": 1,
            "volunteers": 4
        },
        {
            "name": "Summer Charity Raffle",
            "description": "Annual raffle fundraiser for local charities",
            "budget": Decimal("3000.00"),
            "status": "Completed",
            "start_date": datetime(2024, 6, 1).date(),
            "end_date": datetime(2024, 8, 15).date(),
            "leaders": 1,
            "volunteers": 5
        }
    ]
    
    projects = []
    active_members = [m for m in members if m.active]
    
    for proj_data in projects_data:
        project = Project(
            name=proj_data["name"],
            description=proj_data["description"],
            budget=proj_data["budget"],
            status=proj_data["status"],
            start_date=proj_data["start_date"],
            end_date=proj_data.get("end_date"),
            organization_id=org_id
        )
        
        db.session.add(project)
        db.session.flush()  # project needs an id before assignments can reference it

        # Assign leaders
        num_leaders = proj_data.get("leaders", 1)
        leaders = random.sample(active_members, min(num_leaders, len(active_members)))
        for leader in leaders:
            assign_member(project, leader, role='Leader')

        # Assign volunteers (including leaders)
        num_volunteers = proj_data.get("volunteers", 3)
        volunteers = random.sample(active_members, min(num_volunteers, len(active_members)))
        for volunteer in volunteers:
            assign_member(project, volunteer, role='Volunteer')

        projects.append(project)

    db.session.flush()
    return projects

def get_account_by_number(account_number):
    """Helper to get account by number"""
    return ChartOfAccounts.query.filter_by(account_number=account_number).first()

def create_transaction(entry_date, description, project, reference, created_by_id, lines_data):
    """
    Helper to create a balanced journal entry
    lines_data format: [(account_number, debit_amount, credit_amount, memo), ...]
    """
    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project.id,
        reference_number=reference,
        created_by=created_by_id,
        status='Posted'
    )
    db.session.add(entry)
    db.session.flush()
    
    total_debits = Decimal('0')
    total_credits = Decimal('0')
    
    for account_number, debit, credit, memo in lines_data:
        account = get_account_by_number(account_number)
        if not account:
            raise ValueError(f"Account {account_number} not found")
        
        line = JournalEntryLine(
            journal_entry_id=entry.id,
            account_id=account.id,
            debit_amount=Decimal(str(debit)),
            credit_amount=Decimal(str(credit)),
            memo=memo or description
        )
        db.session.add(line)
        total_debits += Decimal(str(debit))
        total_credits += Decimal(str(credit))
    
    # Verify balanced
    if abs(total_debits - total_credits) > Decimal('0.01'):
        raise ValueError(f"Unbalanced entry: Debits={total_debits}, Credits={total_credits}")
    
    return entry

def create_sample_transactions(projects, users):
    """Create realistic 6 months of transactions for a service organization"""
    
    # Get the treasurer user for most transactions
    treasurer = next((u for u in users if u.role == 'Treasurer'), users[0])
    
    # Get projects by name for easier reference
    ops_project = next((p for p in projects if p.name == "Council Operations"), projects[0])
    fish_fry = next((p for p in projects if "Fish Fry" in p.name), projects[1])
    scholarship = next((p for p in projects if "Scholarship" in p.name), projects[2])
    community = next((p for p in projects if "Community Service" in p.name), projects[3])
    christmas = next((p for p in projects if "Christmas" in p.name), projects[4])
    building = next((p for p in projects if "Building" in p.name), projects[5])
    raffle = next((p for p in projects if "Raffle" in p.name), projects[6])
    
    transactions = []
    
    # Starting balance entry (opening the books 6 months ago)
    start_date = datetime.now() - timedelta(days=180)
    
    # Transaction 1: Opening balance
    transactions.append(create_transaction(
        entry_date=start_date.date(),
        description="Opening balance - Council funds as of " + start_date.strftime('%B %Y'),
        project=ops_project,
        reference="OB-2024",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '25000.00', '0.00', 'Operating checking account'),
            ('3100', '0.00', '25000.00', 'Net assets without restrictions')
        ]
    ))
    
    # Transaction 2-11: Monthly dues (10 members x $50 = $500/month for 4 months)
    for month_offset in [0, 30, 60, 90]:
        date = start_date + timedelta(days=month_offset)
        transactions.append(create_transaction(
            entry_date=date.date(),
            description=f"Monthly membership dues - {date.strftime('%B %Y')}",
            project=ops_project,
            reference=f"DUES-{date.strftime('%Y%m')}",
            created_by_id=treasurer.id,
            lines_data=[
                ('1010', '500.00', '0.00', 'Dues payment received'),
                ('4110', '0.00', '500.00', 'Membership dues revenue')
            ]
        ))
    
    # Transaction 12: Individual donation for scholarship fund
    date = start_date + timedelta(days=15)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Individual donation for scholarship fund - Anonymous donor",
        project=scholarship,
        reference="DON-001",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '1000.00', '0.00', 'Donation received'),
            ('4010', '0.00', '1000.00', 'Individual contribution')
        ]
    ))
    
    # Transaction 13: Corporate donation for Fish Fry
    date = start_date + timedelta(days=45)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Corporate sponsorship - Local Restaurant Supply Co.",
        project=fish_fry,
        reference="DON-002",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '2500.00', '0.00', 'Sponsorship received'),
            ('4020', '0.00', '2500.00', 'Corporate contribution')
        ]
    ))
    
    # Transaction 14: Foundation grant for community service
    date = start_date + timedelta(days=60)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Grant received - Community Foundation of Northwest Arkansas",
        project=community,
        reference="GRANT-2024-001",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '5000.00', '0.00', 'Grant funds received'),
            ('4030', '0.00', '5000.00', 'Foundation grant')
        ]
    ))
    
    # Transaction 15: Fish Fry event revenue (multiple weeks)
    for week in [90, 97, 104, 111, 118, 125]:
        date = start_date + timedelta(days=week)
        amount = Decimal(str(random.uniform(800, 1200))).quantize(Decimal('0.01'))
        transactions.append(create_transaction(
            entry_date=date.date(),
            description=f"Fish Fry dinner sales - {date.strftime('%B %d, %Y')}",
            project=fish_fry,
            reference=f"FF-{date.strftime('%Y%m%d')}",
            created_by_id=treasurer.id,
            lines_data=[
                ('1010', str(amount), '0.00', 'Cash receipts'),
                ('4210', '0.00', str(amount), 'Special event revenue')
            ]
        ))
    
    # Transaction 16: Raffle ticket sales (completed project)
    date = start_date + timedelta(days=70)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Charity raffle ticket sales",
        project=raffle,
        reference="RAF-001",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '3500.00', '0.00', 'Raffle proceeds'),
            ('4210', '0.00', '3500.00', 'Special event revenue')
        ]
    ))
    
    # EXPENSES
    
    # Transaction 17-20: Monthly rent (4 months)
    for month_offset in [5, 35, 65, 95]:
        date = start_date + timedelta(days=month_offset)
        transactions.append(create_transaction(
            entry_date=date.date(),
            description=f"Council hall rent - {date.strftime('%B %Y')}",
            project=building,
            reference=f"CHK-{1000 + month_offset}",
            created_by_id=treasurer.id,
            lines_data=[
                ('5210', '1200.00', '0.00', 'Monthly rent expense'),
                ('1010', '0.00', '1200.00', 'Check payment')
            ]
        ))
    
    # Transaction 21-24: Monthly utilities (4 months)
    for month_offset in [10, 40, 70, 100]:
        date = start_date + timedelta(days=month_offset)
        amount = Decimal(str(random.uniform(250, 350))).quantize(Decimal('0.01'))
        transactions.append(create_transaction(
            entry_date=date.date(),
            description=f"Utilities - Electric and gas - {date.strftime('%B %Y')}",
            project=building,
            reference=f"CHK-{1100 + month_offset}",
            created_by_id=treasurer.id,
            lines_data=[
                ('5220', str(amount), '0.00', 'Utility expenses'),
                ('1010', '0.00', str(amount), 'Check payment')
            ]
        ))
    
    # Transaction 25: Fish Fry supplies - food vendor
    date = start_date + timedelta(days=85)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Fish Fry food supplies - Sysco Foods",
        project=fish_fry,
        reference="CHK-2001",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '2800.00', '0.00', 'Program supplies - food'),
            ('1010', '0.00', '2800.00', 'Check payment')
        ]
    ))
    
    # Transaction 26: Fish Fry supplies - paper goods
    date = start_date + timedelta(days=88)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Fish Fry disposable serving supplies - Sam's Club",
        project=fish_fry,
        reference="CHK-2002",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '450.00', '0.00', 'Program supplies - disposables'),
            ('1010', '0.00', '450.00', 'Check payment')
        ]
    ))
    
    # Transaction 27: Community service - food bank donation
    date = start_date + timedelta(days=75)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Food bank donation - Northwest Arkansas Food Bank",
        project=community,
        reference="CHK-2010",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '1500.00', '0.00', 'Program charitable contribution'),
            ('1010', '0.00', '1500.00', 'Check payment')
        ]
    ))
    
    # Transaction 28: Office supplies
    date = start_date + timedelta(days=50)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Office supplies - Office Depot",
        project=ops_project,
        reference="CHK-2015",
        created_by_id=treasurer.id,
        lines_data=[
            ('5310', '185.00', '0.00', 'Office supplies'),
            ('1010', '0.00', '185.00', 'Check payment')
        ]
    ))
    
    # Transaction 29: Professional fees - accounting
    date = start_date + timedelta(days=120)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Annual tax preparation services - Smith & Associates CPA",
        project=ops_project,
        reference="CHK-2020",
        created_by_id=treasurer.id,
        lines_data=[
            ('5110', '750.00', '0.00', 'Professional accounting fees'),
            ('1010', '0.00', '750.00', 'Check payment')
        ]
    ))
    
    # Transaction 30: Insurance payment
    date = start_date + timedelta(days=30)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Annual general liability insurance - State Farm",
        project=ops_project,
        reference="CHK-2025",
        created_by_id=treasurer.id,
        lines_data=[
            ('5610', '1200.00', '0.00', 'Insurance expense'),
            ('1010', '0.00', '1200.00', 'Check payment')
        ]
    ))
    
    # Transaction 31: Scholarship award disbursement
    date = start_date + timedelta(days=140)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Scholarship award - Sarah Johnson - University of Arkansas",
        project=scholarship,
        reference="CHK-3001",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '2500.00', '0.00', 'Program services - scholarship'),
            ('1010', '0.00', '2500.00', 'Check payment')
        ]
    ))
    
    # Transaction 32: Scholarship award disbursement
    date = start_date + timedelta(days=142)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Scholarship award - Michael Torres - NorthWest Arkansas Community College",
        project=scholarship,
        reference="CHK-3002",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '2000.00', '0.00', 'Program services - scholarship'),
            ('1010', '0.00', '2000.00', 'Check payment')
        ]
    ))
    
    # Transaction 33: Christmas charity - toy purchase
    date = start_date + timedelta(days=155)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Toys for Tots toy purchases - Walmart",
        project=christmas,
        reference="CHK-3010",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '1800.00', '0.00', 'Program supplies - charitable'),
            ('1010', '0.00', '1800.00', 'Check payment')
        ]
    ))
    
    # Transaction 34: Raffle prizes (completed)
    date = start_date + timedelta(days=55)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Raffle prize purchases - Best Buy gift cards",
        project=raffle,
        reference="CHK-3015",
        created_by_id=treasurer.id,
        lines_data=[
            ('5510', '1200.00', '0.00', 'Fundraising expense - prizes'),
            ('1010', '0.00', '1200.00', 'Check payment')
        ]
    ))
    
    # Transaction 35: Advertising for Fish Fry
    date = start_date + timedelta(days=82)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Fish Fry advertising - Northwest Arkansas Democrat-Gazette",
        project=fish_fry,
        reference="CHK-3020",
        created_by_id=treasurer.id,
        lines_data=[
            ('5510', '350.00', '0.00', 'Advertising expense'),
            ('1010', '0.00', '350.00', 'Check payment')
        ]
    ))
    
    # Transaction 36: Building maintenance
    date = start_date + timedelta(days=110)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="HVAC system repair - Comfort Systems Inc.",
        project=building,
        reference="CHK-3025",
        created_by_id=treasurer.id,
        lines_data=[
            ('5320', '875.00', '0.00', 'Building maintenance'),
            ('1010', '0.00', '875.00', 'Check payment')
        ]
    ))
    
    # Transaction 37: Bank fees
    date = start_date + timedelta(days=150)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Monthly bank service fees - 6 months",
        project=ops_project,
        reference="AUTO-DEBIT",
        created_by_id=treasurer.id,
        lines_data=[
            ('5810', '90.00', '0.00', 'Bank service charges'),
            ('1010', '0.00', '90.00', 'Bank fees')
        ]
    ))
    
    # Transaction 38: Donation from previous month (higher amount)
    date = start_date + timedelta(days=165)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description="Major donation - Building fund - Anonymous",
        project=building,
        reference="DON-003",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '5000.00', '0.00', 'Major gift received'),
            ('4010', '0.00', '5000.00', 'Individual contribution')
        ]
    ))
    
    # Transaction 39: More dues (recent)
    date = start_date + timedelta(days=170)
    transactions.append(create_transaction(
        entry_date=date.date(),
        description=f"Monthly membership dues - {date.strftime('%B %Y')}",
        project=ops_project,
        reference=f"DUES-{date.strftime('%Y%m')}",
        created_by_id=treasurer.id,
        lines_data=[
            ('1010', '600.00', '0.00', 'Dues payment received'),
            ('4110', '0.00', '600.00', 'Membership dues revenue')
        ]
    ))
    
    # Transaction 40: One voided transaction (example of correction)
    date = start_date + timedelta(days=80)
    voided_entry = create_transaction(
        entry_date=date.date(),
        description="VOIDED - Duplicate entry - Office supplies (see CHK-2015)",
        project=ops_project,
        reference="CHK-2016-VOID",
        created_by_id=treasurer.id,
        lines_data=[
            ('5310', '185.00', '0.00', 'VOIDED - duplicate'),
            ('1010', '0.00', '185.00', 'VOIDED - duplicate')
        ]
    )
    voided_entry.status = 'Voided'
    transactions.append(voided_entry)
    
    return transactions

def main():
    """Main data loading function"""
    with app.app_context():
        # Check if already loaded
        if data_already_loaded():
            print("❌ Sample data already loaded!")
            print("   Found existing demo users.")
            print("   To reload, delete the database and run init_db.py first.")
            return
        
        print("🎯 Loading CARES Sample Data...")
        print()
        
        # Get organization
        org = get_default_org()
        if not org:
            return
        
        print(f"✓ Organization: {org.name}")
        
        try:
            # Create users
            print("\n👥 Creating sample users...")
            users = create_sample_users(org.id)
            db.session.commit()
            print(f"   ✓ Created {len(users)} users:")
            for user in users:
                print(f"     • {user.username} ({user.role}) - Password: demo123")
            
            # Create members
            print("\n👥  Creating sample members...")
            members = create_sample_members(org.id)
            db.session.commit()
            print(f"   ✓ Created {len(members)} members")
            print(f"     • {len([m for m in members if m.active])} active, {len([m for m in members if not m.active])} inactive")
            
            # Create projects
            print("\n📋 Creating Council projects...")
            projects = create_sample_projects(org.id, members)
            db.session.commit()
            print(f"   ✓ Created {len(projects)} projects:")
            for proj in projects:
                print(f"     • {proj.name} ({proj.status})")
            
            # Create transactions
            print("\n💰 Creating financial transactions (6 months of activity)...")
            transactions = create_sample_transactions(projects, users)
            db.session.commit()
            print(f"   ✓ Created {len(transactions)} journal entries")
            print(f"     • All transactions properly balanced")
            print(f"     • All transactions mapped to projects")
            print(f"     • 1 voided entry included for demonstration")
            
            # Calculate final balance
            cash_account = get_account_by_number('1010')
            cash_lines = JournalEntryLine.query.filter_by(account_id=cash_account.id).all()
            total_debits = sum(line.debit_amount for line in cash_lines)
            total_credits = sum(line.credit_amount for line in cash_lines)
            final_balance = total_debits - total_credits
            
            print("\n📊 Financial Summary:")
            print(f"   • Opening Balance: $25,000.00")
            print(f"   • Final Balance: ${final_balance:,.2f}")
            print(f"   • Net Change: ${final_balance - 25000:,.2f}")
            
            print("\n✅ Sample data loaded successfully!")
            print("\n🔐 Login credentials for testing:")
            print("   ┌─────────────────┬──────────────┬──────────┐")
            print("   │ Username        │ Password     │ Role     │")
            print("   ├─────────────────┼──────────────┼──────────┤")
            print("   │ admin           │ admin123     │ Admin    │")
            print("   │ demo_admin      │ demo123      │ Admin    │")
            print("   │ demo_treasurer  │ demo123      │ Treasurer│")
            print("   │ demo_leader1    │ demo123      │ Proj Ldr │")
            print("   │ demo_leader2    │ demo123      │ Proj Ldr │")
            print("   │ demo_member1    │ demo123      │ Member   │")
            print("   │ demo_member2    │ demo123      │ Member   │")
            print("   └─────────────────┴──────────────┴──────────┘")
            print("\n💡 Next steps:")
            print("   1. Login to the system")
            print("   2. View the Dashboard for overview")
            print("   3. Check Reports → Balance Sheet to see financial position")
            print("   4. Browse Members (20 sample members)")
            print("   5. View Projects (7 Council activities)")
            print("   6. Review Transactions (40+ entries)")
            print("\n🎉 Ready for demonstration!\n")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    main()

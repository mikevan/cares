"""
CARES Production Migration Script
Safely adds missing accounts and fixes data issues without destroying existing data
Can be run multiple times safely (idempotent)
"""

from app import app, db
from models import ChartOfAccounts, JournalEntry, JournalEntryLine, Project
from datetime import datetime
from sqlalchemy import inspect

def add_missing_accounts():
    """Add any missing accounts to the chart - safe to run multiple times"""
    print("Step 1: Checking Chart of Accounts...")
    
    required_accounts = [
        # Cash & Investments (missing from old init)
        ('1310', 'Short-term Investments', 'Asset', 'Investments', 'Debit'),
        
        # Fixed Assets (missing from old init)
        ('1410', 'Computer Equipment', 'Asset', 'Fixed Assets', 'Debit'),
        ('1420', 'Furniture & Fixtures', 'Asset', 'Fixed Assets', 'Debit'),
        ('1430', 'Vehicles', 'Asset', 'Fixed Assets', 'Debit'),
        ('1590', 'Accumulated Depreciation', 'Asset', 'Contra-Asset', 'Credit'),  # CRITICAL
        
        # Liabilities (missing from old init)
        ('2210', 'Accrued Salaries Payable', 'Liability', 'Accrued Liabilities', 'Credit'),
        ('2310', 'Notes Payable - Long-term', 'Liability', 'Long-term Liabilities', 'Credit'),
        ('2320', 'Line of Credit', 'Liability', 'Long-term Liabilities', 'Credit'),
        ('2410', 'Deferred Grant Revenue', 'Liability', 'Deferred Revenue', 'Credit'),
        
        # Net Assets (missing from old init)
        ('3210', 'Net Assets With Donor Restrictions - Purpose', 'Net Asset', 'Restricted', 'Credit'),
        
        # Revenue (missing from old init)
        ('4040', 'Government Grants', 'Revenue', 'Grants', 'Credit'),
        ('4120', 'Program Service Fees', 'Revenue', 'Program Revenue', 'Credit'),
        
        # Expenses (missing from old init)
        ('5030', 'Employee Benefits', 'Expense', 'Personnel', 'Debit'),
        ('5720', 'Vehicle Expenses', 'Expense', 'Program Services', 'Debit'),
        ('5910', 'Interest Expense', 'Expense', 'Other Expenses', 'Debit'),
    ]
    
    added_count = 0
    for acc_data in required_accounts:
        existing = ChartOfAccounts.query.filter_by(account_number=acc_data[0]).first()
        if not existing:
            account = ChartOfAccounts(
                account_number=acc_data[0],
                account_name=acc_data[1],
                account_type=acc_data[2],
                account_subtype=acc_data[3],
                normal_balance=acc_data[4],
                active=True
            )
            db.session.add(account)
            added_count += 1
            print(f"  + Adding {acc_data[0]} - {acc_data[1]}")
    
    if added_count > 0:
        db.session.commit()
        print(f"✓ Added {added_count} missing accounts")
    else:
        print("✓ All required accounts exist")

def fix_account_names():
    """Fix any accounts that have wrong names"""
    print("\nStep 2: Verifying account names...")
    
    fixes = [
        ('5810', 'Depreciation'),  # Was "Bank Fees" in old init
    ]
    
    fixed_count = 0
    for acc_number, correct_name in fixes:
        account = ChartOfAccounts.query.filter_by(account_number=acc_number).first()
        if account and account.account_name != correct_name:
            print(f"  ! Fixing {acc_number}: '{account.account_name}' -> '{correct_name}'")
            account.account_name = correct_name
            fixed_count += 1
    
    if fixed_count > 0:
        db.session.commit()
        print(f"✓ Fixed {fixed_count} account names")
    else:
        print("✓ All account names correct")

def fix_depreciation_entries():
    """Fix depreciation entries that used wrong account (1510 instead of 1590)"""
    print("\nStep 3: Checking depreciation entries...")
    
    # Find depreciation entries that might have wrong accounts
    acc_5810 = ChartOfAccounts.query.filter_by(account_number='5810').first()
    acc_1510 = ChartOfAccounts.query.filter_by(account_number='1510').first()
    acc_1590 = ChartOfAccounts.query.filter_by(account_number='1590').first()
    
    if not acc_5810 or not acc_1590:
        print("  ⚠ Required accounts missing - cannot verify depreciation")
        return
    
    # Find entries where 5810 (depreciation expense) is paired with 1510 (Land) instead of 1590
    bad_entries = []
    if acc_1510:
        depreciation_entries = JournalEntry.query.filter(
            JournalEntry.description.ilike('%depreciation%')
        ).all()
        
        for entry in depreciation_entries:
            lines = JournalEntryLine.query.filter_by(journal_entry_id=entry.id).all()
            has_5810 = any(line.account_id == acc_5810.id for line in lines)
            has_1510 = any(line.account_id == acc_1510.id for line in lines)
            
            if has_5810 and has_1510:
                bad_entries.append(entry)
    
    if bad_entries:
        print(f"  ! Found {len(bad_entries)} depreciation entries with wrong accounts")
        print(f"    These entries credit Land (1510) instead of Accumulated Depreciation (1590)")
        
        for entry in bad_entries:
            lines = JournalEntryLine.query.filter_by(journal_entry_id=entry.id).all()
            for line in lines:
                if line.account_id == acc_1510.id:
                    print(f"    Fixing entry {entry.reference_number}: {entry.description}")
                    line.account_id = acc_1590.id
        
        db.session.commit()
        print(f"✓ Fixed {len(bad_entries)} depreciation entries")
    else:
        print("✓ No depreciation entries need fixing")

def verify_database_integrity():
    """Verify that critical accounts and data exist"""
    print("\nStep 4: Verifying database integrity...")
    
    # Check critical accounts
    critical_accounts = ['1010', '1590', '3100', '4010', '5010', '5810']
    missing = []
    
    for acc_num in critical_accounts:
        if not ChartOfAccounts.query.filter_by(account_number=acc_num).first():
            missing.append(acc_num)
    
    if missing:
        print(f"  ⚠ WARNING: Missing critical accounts: {', '.join(missing)}")
        print(f"    This may indicate incomplete initialization")
        return False
    
    print("✓ All critical accounts exist")
    
    # Check if any data exists
    entry_count = JournalEntry.query.count()
    print(f"✓ Database has {entry_count} journal entries")
    
    return True

def show_summary():
    """Show summary of database state"""
    print("\n" + "="*60)
    print("Database Summary:")
    print("="*60)
    
    account_count = ChartOfAccounts.query.filter_by(active=True).count()
    entry_count = JournalEntry.query.count()
    line_count = JournalEntryLine.query.count()
    
    print(f"Chart of Accounts: {account_count} active accounts")
    print(f"Transactions: {entry_count} journal entries, {line_count} lines")
    
    # Check for depreciation
    acc_1590 = ChartOfAccounts.query.filter_by(account_number='1590').first()
    if acc_1590:
        dep_entries = JournalEntry.query.filter(
            JournalEntry.description.ilike('%depreciation%')
        ).count()
        print(f"Depreciation: {dep_entries} entries found")
    
    print("="*60)

def main():
    """Run all migration steps"""
    with app.app_context():
        print("\n" + "="*60)
        print("CARES Production Migration")
        print("Safe to run multiple times - will not destroy existing data")
        print("="*60 + "\n")
        
        try:
            # Step 1: Add missing accounts
            add_missing_accounts()
            
            # Step 2: Fix account names
            fix_account_names()
            
            # Step 3: Fix depreciation entries
            fix_depreciation_entries()
            
            # Step 4: Verify integrity
            if not verify_database_integrity():
                print("\n⚠ WARNING: Database integrity check failed!")
                print("   You may need to run a full initialization.")
            
            # Show summary
            show_summary()
            
            print("\n✓ Migration complete!")
            print("\nNext steps:")
            print("1. Replace load_comprehensive_data.py with fixed version")
            print("2. Replace start.sh with updated version")
            print("3. Restart the application")
            
        except Exception as e:
            print(f"\n❌ ERROR during migration: {e}")
            print("Rolling back changes...")
            db.session.rollback()
            raise

if __name__ == '__main__':
    main()

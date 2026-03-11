"""
CARES Test Harness - Integration Tests - AP Routes & Service
=============================================================
Tests for accounts payable: vendors, invoices, payments, void, aging.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from models import Vendor, Invoice, InvoicePayment, ChartOfAccounts
from services.ap_service import create_invoice, record_payment, void_invoice, APServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_accounts(db_session):
    """Return (expense_account, ap_account) — must exist from chart init."""
    expense = db_session.query(ChartOfAccounts).filter_by(account_number='5010').first()
    assert expense, "Account 5010 must exist (run chart of accounts init)"
    return expense


def _make_vendor(db_session, organization):
    vendor = Vendor(
        organization_id=organization.id,
        name='Test Vendor Co.',
        payment_terms='Net30',
        is_1099=False,
        active=True,
    )
    db_session.add(vendor)
    db_session.flush()
    return vendor


def _make_invoice(db_session, organization, vendor, project, user, amount=Decimal('500.00')):
    expense = _get_accounts(db_session)
    inv = create_invoice(
        organization_id=organization.id,
        vendor_id=vendor.id,
        project_id=project.id,
        gl_account_number=expense.account_number,
        gl_account_id=expense.id,
        invoice_number='INV-TEST-001',
        invoice_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        amount=amount,
        notes='Test invoice',
        created_by=user.id,
    )
    return inv


# ---------------------------------------------------------------------------
# AP Service — Unit-style tests (no HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAPService:

    def test_create_invoice_posts_gl(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)

        inv = _make_invoice(db_session, organization, vendor, project, user)

        assert inv.id is not None
        assert inv.status == 'Open'
        assert inv.amount == Decimal('500.00')
        assert inv.amount_paid == Decimal('0.00')
        assert inv.journal_entry_id is not None

    def test_create_invoice_unknown_vendor_raises(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        expense = _get_accounts(db_session)

        with pytest.raises(APServiceError, match="Vendor not found"):
            create_invoice(
                organization_id=organization.id,
                vendor_id=99999,
                project_id=project.id,
                gl_account_number=expense.account_number,
                gl_account_id=expense.id,
                invoice_number='INV-BAD',
                invoice_date=date.today(),
                due_date=date.today() + timedelta(days=30),
                amount=Decimal('100.00'),
                notes='',
                created_by=user.id,
            )

    def test_full_payment_marks_paid(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('200.00'))

        record_payment(
            invoice=inv,
            payment_amount=Decimal('200.00'),
            payment_date=date.today(),
            reference_number='CHK-001',
            created_by=user.id,
        )

        assert inv.status == 'Paid'
        assert inv.amount_paid == Decimal('200.00')
        assert inv.amount_due == Decimal('0.00')

    def test_partial_payment_marks_partial(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('300.00'))

        record_payment(
            invoice=inv,
            payment_amount=Decimal('100.00'),
            payment_date=date.today(),
            reference_number='CHK-002',
            created_by=user.id,
        )

        assert inv.status == 'Partial'
        assert inv.amount_due == Decimal('200.00')

    def test_overpayment_raises(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('100.00'))

        with pytest.raises(APServiceError, match="exceeds amount due"):
            record_payment(
                invoice=inv,
                payment_amount=Decimal('999.00'),
                payment_date=date.today(),
                reference_number='CHK-003',
                created_by=user.id,
            )

    def test_payment_on_paid_invoice_raises(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('50.00'))

        record_payment(invoice=inv, payment_amount=Decimal('50.00'),
                       payment_date=date.today(), reference_number='CHK-004',
                       created_by=user.id)

        with pytest.raises(APServiceError, match="already paid"):
            record_payment(invoice=inv, payment_amount=Decimal('50.00'),
                           payment_date=date.today(), reference_number='CHK-005',
                           created_by=user.id)

    def test_void_open_invoice(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user)

        void_invoice(inv)
        assert inv.status == 'Voided'

    def test_void_paid_invoice_raises(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('75.00'))

        record_payment(invoice=inv, payment_amount=Decimal('75.00'),
                       payment_date=date.today(), reference_number='CHK-006',
                       created_by=user.id)

        with pytest.raises(APServiceError, match="Cannot void a paid invoice"):
            void_invoice(inv)

    def test_aging_buckets(self, db_session, organization):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization)
        project = ProjectFactory(organization=organization)
        vendor = _make_vendor(db_session, organization)
        expense = _get_accounts(db_session)

        cases = [
            (10,   'Current'),
            (-5,   '1-30'),
            (-35,  '31-60'),
            (-65,  '61-90'),
            (-95,  '90+'),
        ]
        for days_until_due, expected_bucket in cases:
            inv = create_invoice(
                organization_id=organization.id,
                vendor_id=vendor.id,
                project_id=project.id,
                gl_account_number=expense.account_number,
                gl_account_id=expense.id,
                invoice_number=f'INV-AGE-{days_until_due}',
                invoice_date=date.today() - timedelta(days=10),
                due_date=date.today() + timedelta(days=days_until_due),
                amount=Decimal('100.00'),
                notes='',
                created_by=user.id,
            )
            assert inv.aging_bucket == expected_bucket, (
                f"Expected {expected_bucket} for due_date offset {days_until_due}, "
                f"got {inv.aging_bucket}"
            )


# ---------------------------------------------------------------------------
# AP Routes — HTTP tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAPRoutes:

    def test_vendors_requires_auth(self, client):
        response = client.get('/ap/vendors')
        assert response.status_code == 302
        assert '/login' in response.location

    def test_vendors_requires_treasurer(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        member = UserFactory(organization=organization, role='Member')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(member.id)
            sess['_fresh'] = True

        response = client.get('/ap/vendors')
        assert response.status_code == 302  # redirected away (no permission)

    def test_vendors_list_renders(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, role='Treasurer')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/ap/vendors')
        assert response.status_code == 200

    def test_create_vendor(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, role='Admin')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.post('/ap/vendors/new', data={
            'name': 'New Test Vendor',
            'contact_name': 'Jane Doe',
            'email': 'jane@example.com',
            'phone': '555-9999',
            'address': '123 Main St',
            'city': 'Testville',
            'state': 'TX',
            'zip_code': '75001',
            'payment_terms': 'Net30',
        }, follow_redirects=False)

        assert response.status_code == 302
        vendor = db_session.query(Vendor).filter_by(name='New Test Vendor').first()
        assert vendor is not None

    def test_invoices_list_renders(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, role='Treasurer')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/ap/')
        assert response.status_code == 200

    def test_create_invoice_via_route(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization, role='Admin')
        project = ProjectFactory(organization=organization)
        db_session.flush()

        vendor = _make_vendor(db_session, organization)
        db_session.flush()

        expense = _get_accounts(db_session)

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.post('/ap/invoices/new', data={
            'vendor_id': str(vendor.id),
            'project_id': str(project.id),
            'gl_account_id': str(expense.id),
            'invoice_number': 'INV-ROUTE-001',
            'invoice_date': date.today().strftime('%Y-%m-%d'),
            'due_date': (date.today() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'amount': '250.00',
            'notes': 'Route test invoice',
        }, follow_redirects=False)

        assert response.status_code == 302
        inv = db_session.query(Invoice).filter_by(invoice_number='INV-ROUTE-001').first()
        assert inv is not None
        assert inv.amount == Decimal('250.00')

    def test_pay_invoice_via_route(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization, role='Admin')
        project = ProjectFactory(organization=organization)
        db_session.flush()

        vendor = _make_vendor(db_session, organization)
        db_session.flush()

        inv = _make_invoice(db_session, organization, vendor, project, user, Decimal('400.00'))
        db_session.flush()

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.post(f'/ap/invoices/{inv.id}/pay', data={
            'amount': '400.00',
            'payment_date': date.today().strftime('%Y-%m-%d'),
            'reference_number': 'CHK-ROUTE-001',
        }, follow_redirects=False)

        assert response.status_code == 302
        db_session.refresh(inv)
        assert inv.status == 'Paid'

    def test_void_invoice_via_route(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory, ProjectFactory
        user = UserFactory(organization=organization, role='Admin')
        project = ProjectFactory(organization=organization)
        db_session.flush()

        vendor = _make_vendor(db_session, organization)
        db_session.flush()

        inv = _make_invoice(db_session, organization, vendor, project, user)
        db_session.flush()

        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.post(f'/ap/invoices/{inv.id}/void',
                               follow_redirects=False)

        assert response.status_code == 302
        db_session.refresh(inv)
        assert inv.status == 'Voided'

    def test_aging_report_renders(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, role='Treasurer')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/ap/aging')
        assert response.status_code == 200

    def test_1099_report_renders(self, client, organization, db_session):
        from tests.fixtures.factories import UserFactory
        user = UserFactory(organization=organization, role='Treasurer')
        db_session.flush()
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

        response = client.get('/ap/1099')
        assert response.status_code == 200

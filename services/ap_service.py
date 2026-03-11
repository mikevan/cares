"""
CARES Accounts Payable Service
Handles invoice lifecycle and payment recording.
All GL posting is delegated to journal_service.
"""

from decimal import Decimal
from datetime import date
from models import db, Vendor, Invoice, InvoicePayment
from services.journal_service import post_simple_entry, JournalServiceError

AP_ACCOUNT  = '2110'   # Accounts Payable
CASH_ACCOUNT = '1010'  # Operating Checking


class APServiceError(Exception):
    pass


def create_invoice(
    *,
    organization_id: int,
    vendor_id: int,
    project_id: int,
    gl_account_number: str,   # expense account to debit
    gl_account_id: int,       # stored on Invoice for display
    invoice_number: str,
    invoice_date: date,
    due_date: date,
    amount: Decimal,
    notes: str,
    created_by: int,
) -> Invoice:
    """
    Create a vendor invoice and auto-post the GL entry:
        DR  expense account
        CR  2110 Accounts Payable
    """
    vendor = Vendor.query.filter_by(id=vendor_id, organization_id=organization_id).first()
    if not vendor:
        raise APServiceError("Vendor not found.")

    description = notes or f"Invoice from {vendor.name}"

    try:
        je = post_simple_entry(
            entry_date=invoice_date,
            description=description,
            project_id=project_id,
            created_by=created_by,
            debit_account=gl_account_number,
            credit_account=AP_ACCOUNT,
            amount=amount,
            reference_number=invoice_number,
            memo=description,
        )
    except JournalServiceError as e:
        raise APServiceError(str(e))

    invoice = Invoice(
        organization_id=organization_id,
        vendor_id=vendor_id,
        project_id=project_id,
        gl_account_id=gl_account_id,
        journal_entry_id=je.id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        amount=amount,
        amount_paid=Decimal('0.00'),
        status='Open',
        notes=notes,
        created_by=created_by,
    )
    db.session.add(invoice)
    db.session.commit()
    return invoice


def record_payment(
    *,
    invoice: Invoice,
    payment_amount: Decimal,
    payment_date: date,
    reference_number: str,
    created_by: int,
) -> InvoicePayment:
    """
    Record a payment against an open invoice and auto-post:
        DR  2110 Accounts Payable
        CR  1010 Cash
    Raises APServiceError if invoice is not payable or amount is invalid.
    """
    if invoice.status in ('Paid', 'Voided'):
        raise APServiceError("Invoice is already paid or voided.")
    if payment_amount <= 0:
        raise APServiceError("Payment amount must be greater than zero.")
    if payment_amount > invoice.amount_due:
        raise APServiceError(
            f"Payment ${payment_amount:.2f} exceeds amount due ${invoice.amount_due:.2f}."
        )

    description = (
        f"Payment — {invoice.vendor.name} "
        f"inv #{invoice.invoice_number or invoice.id}"
    )

    try:
        je = post_simple_entry(
            entry_date=payment_date,
            description=description,
            project_id=invoice.project_id,
            created_by=created_by,
            debit_account=AP_ACCOUNT,
            credit_account=CASH_ACCOUNT,
            amount=payment_amount,
            reference_number=reference_number,
            memo=description,
        )
    except JournalServiceError as e:
        raise APServiceError(str(e))

    payment = InvoicePayment(
        invoice_id=invoice.id,
        journal_entry_id=je.id,
        amount=payment_amount,
        payment_date=payment_date,
    )
    db.session.add(payment)

    invoice.amount_paid = (invoice.amount_paid or Decimal('0.00')) + payment_amount
    invoice.status = 'Paid' if invoice.amount_paid >= invoice.amount else 'Partial'

    db.session.commit()
    return payment


def void_invoice(invoice: Invoice) -> Invoice:
    """Mark an unpaid invoice as Voided. Does not reverse the GL entry."""
    if invoice.status == 'Paid':
        raise APServiceError("Cannot void a paid invoice.")
    if invoice.status == 'Voided':
        raise APServiceError("Invoice is already voided.")

    invoice.status = 'Voided'
    db.session.commit()
    return invoice

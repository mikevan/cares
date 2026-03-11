"""
CARES Journal Service
Single gateway for all journal entry creation and management.

Every feature that needs to post to the GL calls this service.
Nothing writes directly to JournalEntry or JournalEntryLine except here.

Future hook points (not yet implemented):
  - Period open/closed validation
  - Audit trail
  - Fund assignment
  - RLS context verification
"""

from decimal import Decimal
from datetime import date
from models import db, JournalEntry, JournalEntryLine, ChartOfAccounts


class JournalServiceError(Exception):
    """Raised when a journal entry cannot be posted."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_account(account_number: str) -> ChartOfAccounts:
    """Return an active ChartOfAccounts row by account number, or raise."""
    acct = ChartOfAccounts.query.filter_by(
        account_number=account_number, active=True
    ).first()
    if not acct:
        raise JournalServiceError(
            f"Account {account_number} not found or inactive in Chart of Accounts."
        )
    return acct


def _build_line(journal_entry_id: int, account_id: int,
                debit: Decimal, credit: Decimal, memo: str = '') -> JournalEntryLine:
    return JournalEntryLine(
        journal_entry_id=journal_entry_id,
        account_id=account_id,
        debit_amount=debit,
        credit_amount=credit,
        memo=memo or '',
    )


def _verify_balance(lines: list) -> None:
    """Raise JournalServiceError if debits != credits (within $0.01)."""
    total_debits = sum(l['debit'] for l in lines)
    total_credits = sum(l['credit'] for l in lines)
    if abs(total_debits - total_credits) > Decimal('0.01'):
        raise JournalServiceError(
            f"Entry is not balanced — Debits: ${total_debits:.2f}, "
            f"Credits: ${total_credits:.2f}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def post_entry(
    *,
    entry_date: date,
    description: str,
    project_id: int,
    created_by: int,
    lines: list,          # [{'account_number': str, 'debit': Decimal, 'credit': Decimal, 'memo': str}, ...]
    reference_number: str = '',
    status: str = 'Posted',
) -> JournalEntry:
    """
    Post a full journal entry with arbitrary lines.

    Each line dict must have:
        account_number  str       COA account number e.g. '1010'
        debit           Decimal   amount (0 if credit side)
        credit          Decimal   amount (0 if debit side)
        memo            str       optional line memo

    Returns the committed JournalEntry.
    Raises JournalServiceError on validation failure.
    Caller is responsible for db.session.rollback() on exception.
    """
    if not lines:
        raise JournalServiceError("A journal entry must have at least one line.")

    _verify_balance(lines)

    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        reference_number=reference_number or '',
        created_by=created_by,
        status=status,
    )
    db.session.add(entry)
    db.session.flush()  # get entry.id before adding lines

    for line in lines:
        debit = Decimal(str(line.get('debit', 0)))
        credit = Decimal(str(line.get('credit', 0)))
        if debit == 0 and credit == 0:
            continue
        acct = _resolve_account(line['account_number'])
        db.session.add(_build_line(entry.id, acct.id, debit, credit, line.get('memo', '')))

    db.session.commit()
    return entry


def post_simple_entry(
    *,
    entry_date: date,
    description: str,
    project_id: int,
    created_by: int,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    reference_number: str = '',
    memo: str = '',
    status: str = 'Posted',
) -> JournalEntry:
    """
    Post a two-line (debit / credit) journal entry.
    Convenience wrapper around post_entry for the common case.
    """
    return post_entry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        created_by=created_by,
        reference_number=reference_number,
        status=status,
        lines=[
            {'account_number': debit_account,  'debit': amount, 'credit': Decimal('0'), 'memo': memo or description},
            {'account_number': credit_account, 'debit': Decimal('0'), 'credit': amount, 'memo': memo or description},
        ],
    )


def post_entry_from_account_ids(
    *,
    entry_date: date,
    description: str,
    project_id: int,
    created_by: int,
    lines: list,          # [{'account_id': int, 'debit': Decimal, 'credit': Decimal, 'memo': str}, ...]
    reference_number: str = '',
    status: str = 'Posted',
) -> JournalEntry:
    """
    Post a journal entry using account IDs directly (used by accountant mode
    where the form submits account_id values from the COA dropdown).

    Raises JournalServiceError on validation failure.
    """
    if not lines:
        raise JournalServiceError("A journal entry must have at least one line.")

    _verify_balance(lines)

    entry = JournalEntry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        reference_number=reference_number or '',
        created_by=created_by,
        status=status,
    )
    db.session.add(entry)
    db.session.flush()

    for line in lines:
        debit = Decimal(str(line.get('debit', 0)))
        credit = Decimal(str(line.get('credit', 0)))
        if debit == 0 and credit == 0:
            continue
        db.session.add(_build_line(
            entry.id, int(line['account_id']), debit, credit, line.get('memo', '')
        ))

    db.session.commit()
    return entry


# Simple-mode transaction templates — account numbers only, no Flask context
SIMPLE_MODE_TEMPLATES = {
    'received_dues':     {'debit': '1010', 'credit': '4110'},
    'received_donation': {'debit': '1010', 'credit': '4010'},
    'received_grant':    {'debit': '1010', 'credit': '4030'},
    'paid_vendor':       {'debit': '5320', 'credit': '1010'},
    'paid_rent':         {'debit': '5210', 'credit': '1010'},
    'paid_utilities':    {'debit': '5220', 'credit': '1010'},
    'paid_salary':       {'debit': '5010', 'credit': '1010'},
}


def post_simple_mode_entry(
    *,
    transaction_type: str,
    entry_date: date,
    description: str,
    project_id: int,
    created_by: int,
    amount: Decimal,
    reference_number: str = '',
) -> JournalEntry:
    """
    Post a simple-mode (volunteer-friendly) transaction using a named template.
    Raises JournalServiceError for unknown types or missing accounts.
    """
    template = SIMPLE_MODE_TEMPLATES.get(transaction_type)
    if not template:
        raise JournalServiceError(f"Unknown transaction type: '{transaction_type}'.")

    return post_simple_entry(
        entry_date=entry_date,
        description=description,
        project_id=project_id,
        created_by=created_by,
        debit_account=template['debit'],
        credit_account=template['credit'],
        amount=amount,
        reference_number=reference_number,
    )


def void_entry(entry_id: int, voided_by: int) -> JournalEntry:
    """
    Mark a journal entry as Voided.
    Does not reverse the entry — reversal is a separate operation.
    Raises JournalServiceError if entry cannot be voided.
    """
    entry = JournalEntry.query.get(entry_id)
    if not entry:
        raise JournalServiceError(f"Journal entry #{entry_id} not found.")
    if entry.status == 'Voided':
        raise JournalServiceError(f"Journal entry #{entry_id} is already voided.")

    entry.status = 'Voided'
    db.session.commit()
    return entry

"""
CARES Accounts Receivable Service
=================================

Receivables for a nonprofit, which means two different bodies of guidance
behind one word, and a third case that only exists once a state or regional
council sits above its chapters.

    EXCHANGE      The organization delivered something and is owed payment --
                  program fees, hall rental, billed event tickets. ASC 606.
                  Recognize when earned; the receivable exists immediately.

    CONTRIBUTION  A donor promised money. ASC 958-605. An UNCONDITIONAL
    / GRANT       promise is revenue and an asset now. A CONDITIONAL promise
                  -- one with a measurable barrier and a right of return or
                  release -- is NOTHING until that barrier is substantially
                  met: no receivable, no revenue, no journal entry. This
                  service will not post one, which is the point.

    ASSESSMENT    One organization in this deployment billing another -- a
                  state or regional council charging its chapters per capita.
                  Posts both sides; see post_assessment().

Three further rules that separate this from an invoice tracker:

  * Amounts collectible beyond a year are discounted to present value. Face
    sits on the receivable, the recognized amount is the present value, and
    the difference lives in contra-asset 1225 and unwinds to contribution
    revenue as the collection dates approach. A five-year $50,000 pledge is
    not a $50,000 asset.

  * Collectibility is estimated, not assumed. An allowance (contra-asset
    1290) reduces the carrying amount without touching the face.

  * Revenue carries its net-asset classification. A promise collectible in a
    future period is time-restricted even when the donor named no purpose.

All GL posting goes through services/journal_service.py. Nothing here writes
journal entries directly, for the same reason ap_service.py doesn't.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from models import (
    db, Invoice, Organization, Payer, PledgeInstallment, Receivable,
    ReceivablePayment, Vendor,
)
from services.journal_service import post_entry, post_simple_entry, JournalServiceError
from services.usage_service import log_event

CASH_ACCOUNT = '1010'
AP_ACCOUNT = '2110'

# Which receivable account each kind of promise lands in.
RECEIVABLE_ACCOUNTS = {
    'Exchange': '1210',      # Accounts Receivable
    'Contribution': '1220',  # Pledges Receivable
    'Grant': '1230',         # Grants Receivable
    'Assessment': '1240',    # Due from Affiliated Organizations
}
DISCOUNT_ACCOUNT = '1225'    # Discount on Pledges Receivable (contra-asset)
ALLOWANCE_ACCOUNT = '1290'   # Allowance for Doubtful Accounts (contra-asset)
BAD_DEBT_EXPENSE = '5940'    # Provision for Uncollectible Accounts
ASSESSMENT_REVENUE = '4130'  # Assessments & Per Capita Billed

# A promise collectible within this many days is not discounted -- the time
# value is immaterial and the unwinding entries would be noise.
DISCOUNT_THRESHOLD_DAYS = 365
DEFAULT_DISCOUNT_RATE = Decimal('0.0500')

_CENTS = Decimal('0.01')


class ARServiceError(Exception):
    pass


def _money(value):
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def present_value(amount, rate, from_date, to_date):
    """Discount `amount` back from `to_date` to `from_date`.

    Straight compound discounting on an actual/365.25 year fraction. Returns
    the amount unchanged when it is due on or before `from_date`, so a
    current receivable never picks up a spurious discount.
    """
    amount = Decimal(str(amount))
    days = (to_date - from_date).days
    if days <= 0 or not rate:
        return _money(amount)
    years = Decimal(days) / Decimal('365.25')
    return _money(amount / ((Decimal('1') + Decimal(str(rate))) ** years))


def _account_for(receivable_type):
    try:
        return RECEIVABLE_ACCOUNTS[receivable_type]
    except KeyError:
        raise ARServiceError(
            f"Unknown receivable type {receivable_type!r}. "
            f"Expected one of: {', '.join(RECEIVABLE_ACCOUNTS)}."
        )


# ==================== CREATION ====================

def create_receivable(
    *,
    organization_id,
    project_id,
    gl_account_id,
    revenue_account_number,
    payer,
    invoice_number,
    invoice_date,
    due_date,
    amount,
    created_by,
    receivable_type='Exchange',
    restriction='Without Donor Restrictions',
    is_conditional=False,
    condition_description=None,
    installments=None,
    discount_rate=None,
    notes=None,
):
    """Create a receivable and post its recognition entry, if one is due.

    `installments` is an optional list of (due_date, amount) for a multi-year
    promise; when given, the schedule drives the present-value calculation and
    `amount` must equal the total.

    Returns the Receivable. A conditional promise comes back with
    status 'Conditional' and journal_entry_id None -- deliberately, and see
    recognize_conditional() for what changes that.
    """
    amount = _money(amount)
    if amount <= 0:
        raise ARServiceError("Receivable amount must be greater than zero.")
    if isinstance(payer, Payer):
        if payer.organization_id != organization_id:
            raise ARServiceError("Payer belongs to a different organization.")
        payer_id, payer_name = payer.id, payer.name
    else:
        payer_id, payer_name = None, str(payer)

    ar_account = _account_for(receivable_type)

    receivable = Receivable(
        organization_id=organization_id,
        project_id=project_id,
        gl_account_id=gl_account_id,
        payer_id=payer_id,
        payer_name=payer_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        amount=amount,
        amount_received=Decimal('0.00'),
        receivable_type=receivable_type,
        restriction=restriction,
        is_conditional=bool(is_conditional),
        condition_description=condition_description,
        notes=notes,
        created_by=created_by,
        status='Conditional' if is_conditional else 'Open',
    )
    db.session.add(receivable)
    db.session.flush()

    if installments:
        _build_installments(receivable, installments, invoice_date, discount_rate)

    if not is_conditional:
        _post_recognition(receivable, revenue_account_number, ar_account,
                          invoice_date, created_by)

    db.session.commit()
    log_event('ar.receivable_created', organization_id=organization_id, user_id=created_by,
              meta={'receivable_id': receivable.id, 'amount': str(amount),
                    'type': receivable_type, 'conditional': bool(is_conditional)})
    return receivable


def _build_installments(receivable, installments, measurement_date, discount_rate):
    """Lay out a multi-year schedule and discount each payment separately.

    Each installment is discounted from its own due date, because the whole
    point of present value here is that money due in year five is worth less
    than money due in year one. Discounting the total once, at the average
    date, gets a different and wrong answer.
    """
    total = sum(_money(a) for _, a in installments)
    if total != _money(receivable.amount):
        raise ARServiceError(
            f"Installments total ${total:,.2f} but the receivable is "
            f"${_money(receivable.amount):,.2f}. They must agree."
        )

    furthest = max(d for d, _ in installments)
    long_dated = (furthest - measurement_date).days > DISCOUNT_THRESHOLD_DAYS
    rate = Decimal(str(discount_rate)) if discount_rate is not None else (
        DEFAULT_DISCOUNT_RATE if long_dated else Decimal('0'))

    pv_total = Decimal('0.00')
    for i, (due, amt) in enumerate(sorted(installments), start=1):
        amt = _money(amt)
        pv = present_value(amt, rate, measurement_date, due) if rate else amt
        db.session.add(PledgeInstallment(
            receivable_id=receivable.id, sequence=i, due_date=due, amount=amt,
            present_value=pv, discount_amount=_money(amt - pv),
            discount_amortized=Decimal('0.00'), status='Scheduled',
        ))
        pv_total += pv

    receivable.discount_rate = rate or None
    receivable.present_value = _money(pv_total)
    receivable.discount_unamortized = _money(receivable.amount - pv_total)
    db.session.flush()


def _post_recognition(receivable, revenue_account_number, ar_account,
                      entry_date, created_by):
    """Post the entry that puts the receivable and its revenue on the books.

    Undiscounted:   DR receivable            CR revenue
    Discounted:     DR receivable (face)     CR 1225 discount (contra-asset)
                                             CR revenue (present value)

    The face amount is what the payer owes; the present value is what the
    organization may recognize today. The contra-asset carries the difference
    and unwinds through amortize_discount().
    """
    face = _money(receivable.amount)
    discount = _money(receivable.discount_unamortized or 0)
    description = (f"{receivable.receivable_type} receivable - {receivable.payer_name}"
                   + (f" inv #{receivable.invoice_number}" if receivable.invoice_number else ""))
    try:
        if discount > 0:
            entry = post_entry(
                entry_date=entry_date, description=description,
                project_id=receivable.project_id, created_by=created_by,
                reference_number=receivable.invoice_number or f'AR-{receivable.id}',
                status='Posted',
                lines=[
                    {'account_number': ar_account, 'debit': face,
                     'credit': Decimal('0'), 'memo': f'{description} (face)'},
                    {'account_number': DISCOUNT_ACCOUNT, 'debit': Decimal('0'),
                     'credit': discount, 'memo': 'Discount to present value'},
                    {'account_number': revenue_account_number, 'debit': Decimal('0'),
                     'credit': _money(face - discount), 'memo': f'{description} (present value)'},
                ],
            )
        else:
            entry = post_simple_entry(
                entry_date=entry_date, description=description,
                project_id=receivable.project_id, created_by=created_by,
                debit_account=ar_account, credit_account=revenue_account_number,
                amount=face, reference_number=receivable.invoice_number or f'AR-{receivable.id}',
                memo=description,
            )
    except JournalServiceError as e:
        raise ARServiceError(str(e))

    receivable.journal_entry_id = entry.id
    if receivable.status == 'Conditional':
        receivable.status = 'Open'
    db.session.flush()
    return entry


# ==================== CONDITIONAL PROMISES ====================

def recognize_conditional(*, receivable, revenue_account_number, condition_met_date,
                          created_by):
    """Recognize a conditional promise now that its barrier has been met.

    Until this is called the promise is disclosure only -- it appears on no
    balance sheet and in no revenue total. This is the moment it becomes an
    asset, and the entry is dated when the condition was satisfied, not when
    the award letter arrived.
    """
    if not receivable.is_conditional:
        raise ARServiceError("This receivable is not conditional; it is already recognized.")
    if receivable.condition_met_date is not None:
        raise ARServiceError("This receivable's condition has already been met and recognized.")

    receivable.condition_met_date = condition_met_date
    _post_recognition(receivable, revenue_account_number,
                      _account_for(receivable.receivable_type),
                      condition_met_date, created_by)
    db.session.commit()
    log_event('ar.condition_met', organization_id=receivable.organization_id,
              user_id=created_by, meta={'receivable_id': receivable.id})
    return receivable


# ==================== COLLECTION ====================

def record_receipt(*, receivable, amount, payment_date, created_by,
                   reference_number='', installment=None):
    """Record cash received:  DR 1010 Cash   CR the receivable account."""
    if not receivable.is_recognized:
        raise ARServiceError(
            "Cannot record a receipt against a conditional promise that has not been "
            "recognized. Meet the condition first (recognize_conditional)."
        )
    if receivable.status in ('Paid', 'Voided', 'Written Off'):
        raise ARServiceError(f"Receivable is {receivable.status.lower()}.")
    amount = _money(amount)
    if amount <= 0:
        raise ARServiceError("Payment amount must be greater than zero.")
    if amount > receivable.amount_due:
        raise ARServiceError(
            f"Payment ${amount:,.2f} exceeds the ${receivable.amount_due:,.2f} outstanding."
        )

    description = f"Payment received - {receivable.payer_name}"
    try:
        entry = post_simple_entry(
            entry_date=payment_date, description=description,
            project_id=receivable.project_id, created_by=created_by,
            debit_account=CASH_ACCOUNT,
            credit_account=_account_for(receivable.receivable_type),
            amount=amount, reference_number=reference_number, memo=description,
        )
    except JournalServiceError as e:
        raise ARServiceError(str(e))

    db.session.add(ReceivablePayment(
        receivable_id=receivable.id,
        installment_id=installment.id if installment else None,
        journal_entry_id=entry.id, amount=amount, payment_date=payment_date,
        reference_number=reference_number,
    ))
    receivable.amount_received = _money((receivable.amount_received or 0) + amount)
    receivable.status = 'Paid' if receivable.amount_received >= receivable.amount else 'Partial'

    if installment:
        installment.amount_received = _money((installment.amount_received or 0) + amount)
        installment.status = ('Paid' if installment.amount_received >= installment.amount
                              else 'Partial')

    db.session.commit()
    return receivable


# ==================== DISCOUNT UNWINDING ====================

def amortize_discount(*, receivable, through_date, created_by):
    """Unwind the present-value discount that has expired as of `through_date`.

    The discount is not interest income -- it is contribution revenue the
    organization could not recognize earlier because the money was not yet
    due. Each installment's discount is released in proportion to how much of
    its discount period has elapsed.

        DR 1225 Discount on Pledges Receivable
            CR contribution revenue

    Returns the amount amortized, or Decimal('0.00') when there is nothing to
    release -- calling it repeatedly on the same date is harmless.
    """
    if not receivable.is_recognized:
        return Decimal('0.00')

    measurement = receivable.invoice_date
    release = Decimal('0.00')
    per_installment = []
    for inst in receivable.installments:
        if inst.discount_remaining <= 0:
            continue
        span = (inst.due_date - measurement).days
        if span <= 0:
            earned = inst.discount_remaining
        else:
            elapsed = max(0, min(span, (through_date - measurement).days))
            target = _money(inst.discount_amount * Decimal(elapsed) / Decimal(span))
            earned = _money(target - (inst.discount_amortized or 0))
        if earned > 0:
            per_installment.append((inst, earned))
            release += earned

    if release <= 0:
        return Decimal('0.00')

    revenue_account = _revenue_account_for_discount(receivable)
    description = f"Pledge discount amortization - {receivable.payer_name}"
    try:
        post_simple_entry(
            entry_date=through_date, description=description,
            project_id=receivable.project_id, created_by=created_by,
            debit_account=DISCOUNT_ACCOUNT, credit_account=revenue_account,
            amount=release, reference_number=f'AR-DISC-{receivable.id}', memo=description,
        )
    except JournalServiceError as e:
        raise ARServiceError(str(e))

    for inst, earned in per_installment:
        inst.discount_amortized = _money((inst.discount_amortized or 0) + earned)
    receivable.discount_unamortized = _money((receivable.discount_unamortized or 0) - release)
    db.session.commit()
    return release


def _revenue_account_for_discount(receivable):
    """Which revenue account the released discount credits.

    Taken from the original recognition entry rather than guessed, so the
    unwinding lands in the same account the pledge was recognized in.
    """
    entry = receivable.journal_entry
    if entry:
        for line in entry.lines:
            number = line.account.account_number
            if number.startswith('4') and line.credit_amount and line.credit_amount > 0:
                return number
    return '4010'


# ==================== COLLECTIBILITY ====================

def set_allowance(*, receivable, allowance_amount, created_by, as_of_date=None):
    """Record the portion of this receivable not expected to be collected.

        DR 5940 Provision for Uncollectible Accounts
            CR 1290 Allowance for Doubtful Accounts

    Posts only the change since the last estimate, so revising an allowance
    upward or downward does the right thing without a reversal first. The
    face amount is untouched -- the payer still owes what they owe.
    """
    allowance_amount = _money(allowance_amount)
    if allowance_amount < 0:
        raise ARServiceError("Allowance cannot be negative.")
    if allowance_amount > receivable.amount_due:
        raise ARServiceError("Allowance cannot exceed the outstanding balance.")

    previous = _money(receivable.allowance_amount or 0)
    delta = _money(allowance_amount - previous)
    if delta == 0:
        return receivable

    as_of_date = as_of_date or date.today()
    description = f"Allowance for uncollectible - {receivable.payer_name}"
    debit, credit, magnitude = (
        (BAD_DEBT_EXPENSE, ALLOWANCE_ACCOUNT, delta) if delta > 0
        else (ALLOWANCE_ACCOUNT, BAD_DEBT_EXPENSE, -delta)
    )
    try:
        post_simple_entry(
            entry_date=as_of_date, description=description,
            project_id=receivable.project_id, created_by=created_by,
            debit_account=debit, credit_account=credit, amount=magnitude,
            reference_number=f'AR-ALLOW-{receivable.id}', memo=description,
        )
    except JournalServiceError as e:
        raise ARServiceError(str(e))

    receivable.allowance_amount = allowance_amount
    db.session.commit()
    return receivable


def write_off(*, receivable, write_off_date, created_by):
    """Write off an uncollectible receivable against the allowance.

        DR 1290 Allowance (to the extent one was provided)
        DR 5940 Provision  (any excess never provided for)
            CR the receivable account

    Writing off consumes the allowance rather than expensing the whole
    balance again -- expensing twice is the usual mistake here.
    """
    if receivable.status in ('Paid', 'Written Off', 'Voided'):
        raise ARServiceError(f"Receivable is already {receivable.status.lower()}.")
    outstanding = receivable.amount_due
    if outstanding <= 0:
        raise ARServiceError("Nothing outstanding to write off.")

    provided = min(_money(receivable.allowance_amount or 0), outstanding)
    unprovided = _money(outstanding - provided)
    description = f"Write-off - {receivable.payer_name}"

    lines = []
    if provided > 0:
        lines.append({'account_number': ALLOWANCE_ACCOUNT, 'debit': provided,
                      'credit': Decimal('0'), 'memo': 'Allowance consumed'})
    if unprovided > 0:
        lines.append({'account_number': BAD_DEBT_EXPENSE, 'debit': unprovided,
                      'credit': Decimal('0'), 'memo': 'Not previously provided for'})
    lines.append({'account_number': _account_for(receivable.receivable_type),
                  'debit': Decimal('0'), 'credit': outstanding, 'memo': description})

    try:
        post_entry(
            entry_date=write_off_date, description=description,
            project_id=receivable.project_id, created_by=created_by,
            reference_number=f'AR-WO-{receivable.id}', status='Posted', lines=lines,
        )
    except JournalServiceError as e:
        raise ARServiceError(str(e))

    receivable.status = 'Written Off'
    receivable.written_off_date = write_off_date
    receivable.allowance_amount = Decimal('0.00')
    db.session.commit()
    log_event('ar.written_off', organization_id=receivable.organization_id,
              user_id=created_by, meta={'receivable_id': receivable.id,
                                        'amount': str(outstanding)})
    return receivable


# ==================== INTER-ORGANIZATION BILLING ====================

def _assert_affiliated(billing_org_id, counterparty_org_id):
    """Refuse to touch a second organization's books unless the two are
    directly related in this deployment.

    This is the guard on the only code path in the application that writes a
    journal entry into an organization other than the caller's. It is
    deliberately narrow: parent-to-child or child-to-parent, one hop, both
    present in this database. Note that the Chart of Accounts is not yet
    organization-scoped (see the V2 backlog), so both organizations are
    posting against the same account rows -- which is fine while a
    deployment holds one council hierarchy and must be revisited when
    per-organization accounts land.
    """
    billing = Organization.query.get(billing_org_id)
    counterparty = Organization.query.get(counterparty_org_id)
    if not billing or not counterparty:
        raise ARServiceError("Both organizations must exist in this deployment.")
    if billing.id == counterparty.id:
        raise ARServiceError("An organization cannot bill itself.")
    related = (counterparty.parent_id == billing.id) or (billing.parent_id == counterparty.id)
    if not related:
        raise ARServiceError(
            f"'{counterparty.name}' is not a parent or child of '{billing.name}'. "
            f"Assessments may only be billed between directly affiliated organizations."
        )
    return billing, counterparty


def post_assessment(
    *,
    billing_organization_id,
    counterparty_organization_id,
    project_id,
    gl_account_id,
    payer,
    amount,
    invoice_number,
    invoice_date,
    due_date,
    created_by,
    counterparty_project_id,
    counterparty_expense_account='5850',
    counterparty_gl_account_id=None,
    notes=None,
):
    """Bill an affiliated organization, posting both sides.

    A state or regional council charging a chapter per capita is one economic
    event recorded in two sets of books:

        billing org (HQ)   DR 1240 Due from Affiliated Organizations
                               CR 4130 Assessments & Per Capita Billed

        counterparty       DR 5850/5860 Per Capita expense
        (the chapter)          CR 2110 Accounts Payable

    The chapter's side is created as a real Invoice through the AP tables, so
    it appears on their invoice list and aging exactly like any other bill,
    and both records point at each other rather than being matched by eye.

    Only callable between directly affiliated organizations -- see
    _assert_affiliated for why that guard exists and what it does not cover.
    """
    _assert_affiliated(billing_organization_id, counterparty_organization_id)
    amount = _money(amount)

    receivable = create_receivable(
        organization_id=billing_organization_id,
        project_id=project_id,
        gl_account_id=gl_account_id,
        revenue_account_number=ASSESSMENT_REVENUE,
        payer=payer,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        amount=amount,
        created_by=created_by,
        receivable_type='Assessment',
        notes=notes,
    )
    receivable.counterparty_organization_id = counterparty_organization_id

    # The chapter's payable. A vendor row for the billing organization is
    # created on first use so the chapter's AP screens have something to
    # group and age by, the same as any other supplier.
    billing_org = Organization.query.get(billing_organization_id)
    vendor = Vendor.query.filter_by(organization_id=counterparty_organization_id,
                                    name=billing_org.name).first()
    if not vendor:
        vendor = Vendor(organization_id=counterparty_organization_id, name=billing_org.name,
                        contact_name='Assessments', payment_terms='Net30', active=True,
                        notes='Affiliated organization. Created automatically by an assessment.')
        db.session.add(vendor)
        db.session.flush()

    description = f"Assessment from {billing_org.name} - {invoice_number or receivable.id}"
    try:
        counterparty_entry = post_simple_entry(
            entry_date=invoice_date, description=description,
            project_id=counterparty_project_id, created_by=created_by,
            debit_account=counterparty_expense_account, credit_account=AP_ACCOUNT,
            amount=amount, reference_number=invoice_number or f'ASMT-{receivable.id}',
            memo=description,
        )
    except JournalServiceError as e:
        raise ARServiceError(f"Billing side posted but the counterparty side failed: {e}")

    counterparty_invoice = Invoice(
        organization_id=counterparty_organization_id,
        vendor_id=vendor.id,
        project_id=counterparty_project_id,
        gl_account_id=counterparty_gl_account_id or gl_account_id,
        journal_entry_id=counterparty_entry.id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        amount=amount,
        amount_paid=Decimal('0.00'),
        status='Open',
        notes=f'Assessment billed by {billing_org.name}.',
        created_by=created_by,
    )
    db.session.add(counterparty_invoice)
    db.session.flush()

    receivable.counterparty_invoice_id = counterparty_invoice.id
    db.session.commit()
    log_event('ar.assessment_posted', organization_id=billing_organization_id,
              user_id=created_by,
              meta={'receivable_id': receivable.id, 'amount': str(amount),
                    'counterparty_organization_id': counterparty_organization_id,
                    'counterparty_invoice_id': counterparty_invoice.id})
    return receivable, counterparty_invoice


# ==================== REPORTING ====================

def aging(organization_id, as_of=None):
    """Open receivables bucketed by how far past due they are.

    Conditional promises are excluded: they are not assets and belong in
    disclosure, not in an aging schedule. They are returned separately so a
    treasurer can still see what has been committed but not yet earned.
    """
    buckets = {'Current': [], '1-30': [], '31-60': [], '61-90': [], '90+': []}
    totals = {k: Decimal('0.00') for k in buckets}
    conditional = []

    rows = Receivable.query.filter(
        Receivable.organization_id == organization_id,
        Receivable.status.in_(['Open', 'Partial', 'Conditional']),
    ).order_by(Receivable.due_date).all()

    for r in rows:
        if not r.is_recognized:
            conditional.append(r)
            continue
        buckets[r.aging_bucket].append(r)
        totals[r.aging_bucket] += r.amount_due

    return {
        'buckets': buckets,
        'totals': totals,
        'total_outstanding': sum(totals.values(), Decimal('0.00')),
        'conditional': conditional,
        'conditional_total': sum((r.amount for r in conditional), Decimal('0.00')),
        'as_of': as_of or date.today(),
    }


def payer_statement(payer, as_of=None):
    """Everything owed by one payer, with its payment history."""
    rows = Receivable.query.filter(
        Receivable.payer_id == payer.id,
        Receivable.status.in_(['Open', 'Partial', 'Conditional']),
    ).order_by(Receivable.invoice_date).all()
    recognized = [r for r in rows if r.is_recognized]
    return {
        'payer': payer,
        'receivables': recognized,
        'conditional': [r for r in rows if not r.is_recognized],
        'total_due': sum((r.amount_due for r in recognized), Decimal('0.00')),
        'as_of': as_of or date.today(),
    }

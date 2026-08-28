"""
Trustee Audit Report Blueprint
================================

Chapter-facing (not hidden) read-only view over the audit trail (see
audit_schema.py / models.AuditLog), built for exactly the workflow
Knights of Columbus Section 145 already requires: trustees auditing the
financial secretary's and treasurer's books at least every six months.
Pick a date range and see every change to every audited record in it --
who made it, when, and the full before/after values -- plus a button to
independently verify that the hash chain hasn't been broken, tampered
with, or had a row quietly deleted out of it.

Deliberately Admin-gated for now, matching every other admin-only screen
in this app (e.g. settings_routes.py), rather than adding a new Trustee
role -- see the V2 backlog for giving a council's actual trustees their
own read-only access without full Admin rights.

Deliberately NOT organization-scoped: V1 is single-chapter scope (see
kofc-v2-backlog.md), so there is only ever one real chapter's data in a
given deployment's database. Per-organization filtering of audit_log
belongs with the rest of the multi-tenancy work in V2, once a second real
organization actually needs to share a deployment.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import text

from models import db, AuditLog, User
from services.kofc_form_1295 import (
    get_audit_period, schedule_a, schedule_b, schedule_c,
    get_submission, save_submission_explanations, attest_submission,
)

audit_bp = Blueprint('audit', __name__, url_prefix='/audit')

# Human-ordered subset of audit_schema.AUDITED_TABLES worth offering in the
# filter dropdown. (All of AUDITED_TABLES is still searchable by picking
# "All tables" -- this list just controls dropdown order/grouping.)
FILTERABLE_TABLES = [
    'journal_entries', 'journal_entry_lines', 'invoices', 'invoice_payments',
    'receivables', 'receivable_payments', 'members', 'member_dues_payments',
    'donors', 'donations', 'vendors', 'projects', 'project_assignments',
    'chart_of_accounts', 'users', 'organizations',
]

# Trustees auditing under Section 145 work in roughly six-month windows;
# default the report to the most recent one so the common case needs no
# form interaction at all.
_DEFAULT_WINDOW_DAYS = 182

# Rows shown on screen and listed on the PDF before truncating.
_ROW_LIMIT = 500


def _require_admin():
    if current_user.role != 'Admin':
        flash('Permission denied', 'error')
        return False
    return True


def _parse_date(value, default):
    if not value:
        return default
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return default


def _diff_fields(old_data, new_data):
    """For an UPDATE row, return [(field, old_value, new_value), ...] for
    only the fields that actually changed -- old_data/new_data both
    contain every column, and most of them didn't change."""
    if old_data is None or new_data is None:
        return []
    changes = []
    for field in sorted(set(old_data) | set(new_data)):
        old_value = old_data.get(field)
        new_value = new_data.get(field)
        if old_value != new_value:
            changes.append((field, old_value, new_value))
    return changes


def collect_log_rows(start_date, end_date, table_filter, limit):
    """The rows behind both the screen and the PDF.

    Extracted so the printed Trustee Audit Report cannot drift from what
    /audit/log shows -- a signed document and the screen it came from
    disagreeing would be worse than having no PDF at all.
    """
    query = AuditLog.query.filter(
        AuditLog.changed_at >= start_date,
        # Inclusive of the whole end day, not just midnight.
        AuditLog.changed_at < end_date + timedelta(days=1),
    )
    if table_filter:
        query = query.filter(AuditLog.table_name == table_filter)
    entries = query.order_by(AuditLog.changed_at.desc()).limit(limit).all()

    # changed_by_user_id deliberately has no ForeignKey (see models.py) --
    # a user row can be changed or removed later and the audit trail must
    # keep whatever it captured at the time regardless -- so this is a
    # plain lookup, not a relationship/join.
    actor_ids = {e.changed_by_user_id for e in entries if e.changed_by_user_id is not None}
    actors = {u.id: u.username for u in User.query.filter(User.id.in_(actor_ids)).all()} if actor_ids else {}

    return [{
        'entry': e,
        'actor_name': actors.get(e.changed_by_user_id, 'System / Unknown'),
        'diff': _diff_fields(e.old_data, e.new_data) if e.operation == 'UPDATE' else [],
    } for e in entries]


def verify_chain():
    """Recompute every row's hash and confirm every link, returning the
    result rather than flashing it.

    Two independent checks, because neither subsumes the other: editing a
    row's contents and recomputing that row's hash passes the first and
    fails the second at the following row; deleting a row leaves every
    surviving row internally consistent and still breaks the second at the
    deletion point. Run over the whole table, not the report's date range
    -- a break anywhere invalidates everything after it.
    """
    self_consistency_failures = db.session.execute(text("""
        SELECT id, table_name, operation, changed_at
        FROM audit_log
        WHERE row_hash <> encode(digest(
            coalesce(prev_hash, '<genesis>') || '|' || table_name || '|' || operation || '|' ||
            coalesce(old_data::text, '') || '|' || coalesce(new_data::text, '') || '|' ||
            coalesce(changed_by_user_id::text, '<unknown>') || '|' || changed_at::text,
            'sha256'), 'hex')
        ORDER BY id
    """)).fetchall()

    chain_breaks = db.session.execute(text("""
        WITH ordered AS (
            SELECT id, table_name, operation, changed_at, prev_hash,
                   lag(row_hash) OVER (ORDER BY id) AS expected_prev_hash
            FROM audit_log
        )
        SELECT id, table_name, operation, changed_at
        FROM ordered
        WHERE prev_hash IS DISTINCT FROM expected_prev_hash
        ORDER BY id
    """)).fetchall()

    total_rows = db.session.execute(text("SELECT count(*) FROM audit_log")).scalar() or 0
    return {
        'self_failures': len(self_consistency_failures),
        'chain_breaks': len(chain_breaks),
        'total_rows': total_rows,
        'intact': not self_consistency_failures and not chain_breaks,
    }


@audit_bp.route('/log')
@login_required
def log():
    if not _require_admin():
        return redirect(url_for('index'))

    default_end = datetime.utcnow()
    default_start = default_end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    start_date = _parse_date(request.args.get('start_date'), default_start)
    end_date = _parse_date(request.args.get('end_date'), default_end)
    table_filter = request.args.get('table_name') or ''

    rows = collect_log_rows(start_date, end_date, table_filter, _ROW_LIMIT)

    return render_template(
        'audit_log.html',
        rows=rows,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        table_filter=table_filter,
        filterable_tables=FILTERABLE_TABLES,
        truncated=len(rows) == _ROW_LIMIT,
    )


@audit_bp.route('/verify', methods=['POST'])
@login_required
def verify():
    """
    Independently recompute every row's hash from its own stored columns,
    and separately confirm every row's prev_hash matches the row actually
    before it. Run over the whole table, not just whatever date range the
    report happens to be showing -- a row tampered with or deleted
    anywhere breaks the chain for everything after it, including ranges
    that otherwise look untouched.
    """
    if not _require_admin():
        return redirect(url_for('index'))

    result = verify_chain()
    if result['intact']:
        flash(f"Verified {result['total_rows']} audit log entries. The chain is intact -- "
              f"no row has been altered or removed since it was written.", 'success')
    else:
        flash(f"INTEGRITY FAILURE: {result['self_failures']} row(s) with contents that no "
              f"longer match their own hash, {result['chain_breaks']} break(s) in the chain "
              f"linkage (out of {result['total_rows']} total rows). This means the database "
              f"was modified outside the trigger that writes this table -- treat this as "
              f"evidence, not a bug report.", 'error')

    return redirect(url_for('audit.log'))


def _resolve_period():
    """Parse ?period_start=&period_end= (YYYY-MM-DD) from the request, or
    fall back to the most recently completed Knights of Columbus
    semi-annual audit period. Malformed input falls back the same way,
    rather than 500ing on a hand-edited URL."""
    default_start, default_end, _ = get_audit_period()
    start = _parse_date(request.args.get('period_start'), default_start)
    end = _parse_date(request.args.get('period_end'), default_end)
    return start.date() if hasattr(start, 'date') else start, end.date() if hasattr(end, 'date') else end


@audit_bp.route('/form-1295')
@login_required
def form_1295():
    """
    Form 1295 Schedules A, B, and C, computed directly from the ledger for
    a chosen semi-annual audit period -- see services/kofc_form_1295.py
    for exactly how each figure is derived and what this system can't yet
    distinguish. This is the document a council actually files with
    Supreme and the state office; the change-log report above is the
    tamper-evident evidence underneath it, not a replacement for it.

    Also loads (or creates a blank placeholder for) this period's
    Form1295Submission -- the narrative explanation/attestation wizard
    below the schedules -- so the page can show what's already been
    filled in and flag any non-zero miscellaneous line still missing one.
    """
    if not _require_admin():
        return redirect(url_for('index'))

    period_start, period_end = _resolve_period()
    org_id = current_user.organization_id

    sched_b = schedule_b(org_id, period_start, period_end)
    sched_c = schedule_c(org_id, period_end)
    submission = get_submission(org_id, period_start, period_end)

    return render_template(
        'audit_form_1295.html',
        period_start=period_start.strftime('%Y-%m-%d'),
        period_end=period_end.strftime('%Y-%m-%d'),
        schedule_a=schedule_a(org_id, period_start, period_end),
        schedule_b=sched_b,
        schedule_c=sched_c,
        submission=submission,
        misc_income_explanation_needed=(sched_b['financial_secretary']['misc_income'] > 0
                                         and not (submission and submission.misc_income_explanation)),
        misc_liabilities_explanation_needed=(sched_c['liabilities']['misc_liabilities'] > 0
                                              and not (submission and submission.misc_liabilities_explanation)),
    )


@audit_bp.route('/form-1295/submission', methods=['POST'])
@login_required
def form_1295_save_submission():
    """Save the narrative explanations for this period's non-zero
    miscellaneous lines. Never touches a calculated figure -- see
    Form1295Submission in models.py."""
    if not _require_admin():
        return redirect(url_for('index'))

    period_start, period_end = _resolve_period()
    save_submission_explanations(
        current_user.organization_id, period_start, period_end,
        request.form.get('misc_income_explanation'),
        request.form.get('misc_liabilities_explanation'),
    )
    flash('Explanations saved.', 'success')
    return redirect(url_for('audit.form_1295',
                             period_start=period_start.strftime('%Y-%m-%d'),
                             period_end=period_end.strftime('%Y-%m-%d')))


@audit_bp.route('/form-1295/attest', methods=['POST'])
@login_required
def form_1295_attest():
    """Record that a specific logged-in user reviewed and finalized this
    period's schedules. This attestation itself lands on the
    tamper-evident audit trail (form_1295_submissions is in
    audit_schema.AUDITED_TABLES) -- a stronger signature record than a
    wet signature on paper, though it does NOT replace the Grand
    Knight's/trustees' physical signatures required on the actual Form
    1295 filed with Supreme."""
    if not _require_admin():
        return redirect(url_for('index'))

    period_start, period_end = _resolve_period()
    attest_submission(current_user.organization_id, period_start, period_end, current_user.id)
    flash('Schedules attested.', 'success')
    return redirect(url_for('audit.form_1295',
                             period_start=period_start.strftime('%Y-%m-%d'),
                             period_end=period_end.strftime('%Y-%m-%d')))


@audit_bp.route('/log.pdf')
@login_required
def log_pdf():
    """The Trustee Audit Report as a document, not a print of the page."""
    if not _require_admin():
        return redirect(url_for('index'))
    from flask import Response
    from services.audit_report_pdf import build_audit_report_pdf

    default_end = datetime.utcnow()
    default_start = default_end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    start_date = _parse_date(request.args.get('start_date'), default_start)
    end_date = _parse_date(request.args.get('end_date'), default_end)
    table_filter = request.args.get('table_name') or ''

    rows = collect_log_rows(start_date, end_date, table_filter, _ROW_LIMIT)
    buffer = build_audit_report_pdf(
        org=current_user.organization,
        rows=rows,
        period_start=start_date,
        period_end=end_date,
        table_filter=table_filter,
        verification=verify_chain(),
        generated_by=current_user.username,
        truncated=len(rows) == _ROW_LIMIT,
        row_limit=_ROW_LIMIT,
    )
    filename = f'trustee-audit-report-{end_date.strftime("%Y-%m-%d")}.pdf'
    response = Response(buffer.getvalue(), mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@audit_bp.route('/form-1295.pdf')
@login_required
def form_1295_pdf():
    """All three schedules as one document -- what the page's PDF button
    produces, replacing a browser print of the screen."""
    if not _require_admin():
        return redirect(url_for('index'))
    from services.kofc_form_1295_pdf import build_all_schedules_pdf
    period_start, period_end = _resolve_period()
    org_id = current_user.organization_id
    return _schedule_pdf_response(
        f'form-1295-{period_end.strftime("%Y-%m-%d")}.pdf',
        lambda: build_all_schedules_pdf(
            current_user.organization,
            schedule_a(org_id, period_start, period_end),
            schedule_b(org_id, period_start, period_end),
            schedule_c(org_id, period_end),
            get_submission(org_id, period_start, period_end),
        ),
    )


def _schedule_pdf_response(filename, build_pdf):
    from flask import Response
    buffer = build_pdf()
    response = Response(buffer.getvalue(), mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@audit_bp.route('/form-1295/schedule-a.pdf')
@login_required
def form_1295_schedule_a_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    from services.kofc_form_1295_pdf import build_schedule_a_pdf
    period_start, period_end = _resolve_period()
    org_id = current_user.organization_id
    data = schedule_a(org_id, period_start, period_end)
    org = current_user.organization
    submission = get_submission(org_id, period_start, period_end)
    return _schedule_pdf_response(
        f'form-1295-schedule-a-{period_end.strftime("%Y-%m-%d")}.pdf',
        lambda: build_schedule_a_pdf(org, data, submission),
    )


@audit_bp.route('/form-1295/schedule-b.pdf')
@login_required
def form_1295_schedule_b_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    from services.kofc_form_1295_pdf import build_schedule_b_pdf
    period_start, period_end = _resolve_period()
    org_id = current_user.organization_id
    data = schedule_b(org_id, period_start, period_end)
    org = current_user.organization
    submission = get_submission(org_id, period_start, period_end)
    return _schedule_pdf_response(
        f'form-1295-schedule-b-{period_end.strftime("%Y-%m-%d")}.pdf',
        lambda: build_schedule_b_pdf(org, data, submission),
    )


@audit_bp.route('/form-1295/schedule-c.pdf')
@login_required
def form_1295_schedule_c_pdf():
    if not _require_admin():
        return redirect(url_for('index'))
    from services.kofc_form_1295_pdf import build_schedule_c_pdf
    period_start, period_end = _resolve_period()
    org_id = current_user.organization_id
    data = schedule_c(org_id, period_end)
    org = current_user.organization
    submission = get_submission(org_id, period_start, period_end)
    return _schedule_pdf_response(
        f'form-1295-schedule-c-{period_end.strftime("%Y-%m-%d")}.pdf',
        lambda: build_schedule_c_pdf(org, data, submission),
    )

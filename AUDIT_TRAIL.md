# Audit Trail

## Why this exists

CARES holds a chapter's financial books. If someone with legitimate
access -- a treasurer, a compromised admin account -- ever tried to move
money and then edit or delete the records to cover it up, the software
needs to make that both hard to do and easy to prove happened. Separately,
Knights of Columbus council bylaws (Section 145 of the Laws of the Knights
of Columbus) already require the council's trustees to audit the
financial secretary's and treasurer's books at least every six months,
with reports due in January and July, and require that neither the
financial secretary nor the treasurer prepare their own audit. This
feature exists to make that legally-required audit fast and complete
instead of a week of pulling paper -- see the in-app Trustee Audit Report
at `/audit/log`.

## What's captured

Every INSERT, UPDATE, and DELETE on every table listed in
`audit_schema.py::AUDITED_TABLES` (organizations, users, members, dues
payments, project assignments, projects, chart of accounts, journal
entries and lines, donors, donations, currencies, vendors, invoices and
payments, receivables and payments) is recorded in the `audit_log` table
(`models.py::AuditLog`), with the full before/after state of the row, who
made the change, and exactly when.

Deliberately **not** audited: `translation_cache` (a cache, not user
data), `usage_events` (itself a log -- see `services/usage_service.py`),
and `audit_log` itself.

## Why a database trigger instead of application code

An application-level hook (a SQLAlchemy event listener, a decorator on a
Flask route) only fires when a change goes through that specific code
path. Anyone with direct database access -- which a treasurer or a
compromised app credential may well have -- can bypass it entirely with a
raw `UPDATE`/`DELETE` statement. The trigger function in `audit_schema.py`
is attached directly to each audited table, so it fires no matter how the
row was changed, including from a bare `psql` prompt.

## Why every row is hash-chained

Grants alone (see below) stop the application's own database role from
running `UPDATE`/`DELETE`/`TRUNCATE` against `audit_log`. But grants are a
property of the *current* schema; they don't prove after the fact that
nothing has changed -- someone with superuser access to the database
server itself is not something any application-level control can stop.
Every row's `row_hash` is a SHA-256 of its own contents (table, operation,
before/after JSON, actor, exact timestamp) chained to the previous row's
`row_hash`. Editing or deleting even one row breaks the chain from that
point forward, and that break is independently verifiable by anyone with
`SELECT` on `audit_log` -- they don't have to trust the database's word
for its own integrity. Concurrent writes are serialized behind a single
Postgres advisory lock (`pg_advisory_xact_lock`) so the chain can't be
forked by a race between two transactions.

Use the **Verify Chain Integrity** button on the Trustee Audit Report
(`/audit/log`), or run this directly:

```sql
-- Rows whose own content no longer matches their own hash:
SELECT id, table_name, operation, changed_at FROM audit_log
WHERE row_hash <> encode(digest(
    coalesce(prev_hash, '<genesis>') || '|' || table_name || '|' || operation || '|' ||
    coalesce(old_data::text, '') || '|' || coalesce(new_data::text, '') || '|' ||
    coalesce(changed_by_user_id::text, '<unknown>') || '|' || changed_at::text,
    'sha256'), 'hex');

-- Breaks in the chain linkage itself (a row removed entirely):
WITH ordered AS (
    SELECT id, table_name, operation, changed_at, prev_hash,
           lag(row_hash) OVER (ORDER BY id) AS expected_prev_hash
    FROM audit_log
)
SELECT id, table_name, operation, changed_at FROM ordered
WHERE prev_hash IS DISTINCT FROM expected_prev_hash;
```

Both queries returning zero rows means the audit trail is intact.

## Who a change is attributed to

`services/audit_context.py` tells Postgres who's acting, once per
transaction, via `SET LOCAL app.current_user_id`, which the trigger reads
back. `app.py` sets this from the logged-in user at the start of every
request and clears it at the end (threads are reused across requests, so
without clearing this one user's actions could bleed into the next
request served by the same worker). A background script run outside
Flask (`init_db.py`, `load_comprehensive_data.py`,
`create_vendor_account.py`) never sets it, so its changes are recorded
with a **NULL actor** -- which is correct: nobody was logged in. A real
trustee audit should treat a NULL actor on a production system as a
change worth asking about, not as noise to ignore, since it can also mean
a change that bypassed the application entirely.

## Required production setup: the restricted runtime role

This is the part that makes the tamper-resistance real instead of
aspirational, and it is a **manual, one-time step an operator runs against
each real deployment** -- it is deliberately not automated into app
startup, because if the app could grant itself these permissions it could
also revoke the restriction on itself.

1. Run schema setup / migrations (`init_db.py`, or
   `blueprints.auth_routes.init_database`, whichever your deployment
   uses) with a database role that **owns** the tables -- able to
   `CREATE EXTENSION` / `CREATE FUNCTION` / `CREATE TRIGGER`. This
   installs the trigger via `audit_schema.py::install_audit_triggers`
   automatically as part of that existing bootstrap step.

2. Once, using that same owning role, create the role the *application*
   will actually connect as day to day, and lock it down:

   ```python
   from sqlalchemy import create_engine
   from audit_schema import grant_restricted_runtime_role

   engine = create_engine("postgresql://<owner-role>:<owner-password>@<host>/<db>")
   with engine.begin() as connection:
       grant_restricted_runtime_role(connection, "cares_app_runtime", "<a-real-generated-password>")
   ```

   This grants the new role full `SELECT`/`INSERT`/`UPDATE`/`DELETE` on
   every business table (the app needs to do its normal job), and
   `SELECT`+`INSERT` **only** on `audit_log` -- explicitly revoking
   `UPDATE`, `DELETE`, and `TRUNCATE`. This is what stops a SQL-injection
   bug, or a treasurer who has the app's own database credentials, from
   editing or deleting audit history, even though that same role is what
   the trigger uses to write new rows in the first place.

3. Point the running application's `DATABASE_URL` at `cares_app_runtime`
   (not the owning role) for normal operation. Re-run schema
   setup/migrations as the owning role whenever the schema changes.

Local dev and the pytest suite intentionally skip step 2 and run
everything as the database superuser (`postgres`), the same as every
other piece of schema setup in this codebase (`db.create_all()`, chart of
accounts seeding, etc.) -- the security property step 2 provides only
matters once a real deployment exists to protect.
`tests/integration/test_audit_trail.py::TestRestrictedRuntimeRole`
exercises `grant_restricted_runtime_role` directly against the test
container to prove the property holds, without changing what role the
rest of the test suite connects as.

## Trustee Audit Report

`/audit/log` -- Admin-gated for now, matching every other admin-only
screen in this app (see the V2 backlog for giving a council's actual
trustees read-only access without full Admin rights). Defaults to the
last six months (matching the Section 145 semi-annual cadence), filterable
by date range and table, shows who changed what and exactly which fields
changed on an edit. The **Verify Chain Integrity** button runs the two
queries above over the whole table and reports whether anything has been
altered or removed.

Deliberately not organization-scoped: V1 is single-chapter scope (see
`kofc-v2-backlog.md`), so there's only one real chapter's data in a given
deployment. Per-organization filtering of `audit_log` belongs with the
rest of the multi-tenancy work in V2.

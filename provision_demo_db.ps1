<#
.SYNOPSIS
    Provision a complete CARES / REGALIA demo database from nothing.

.DESCRIPTION
    Rebuilds an entire demo deployment against a PostgreSQL database:
    schema dropped and recreated, migrations applied, chart of accounts and
    council demo data loaded, admin password set to a non-default value,
    and the restricted runtime role created.

    This is the remote counterpart of demo_kofc.ps1. That script rebuilds a
    local Docker database and uses `docker exec psql`; this one targets a
    managed database reachable only over the network, so every step runs
    through Python and psycopg2 instead. The SEQUENCE is deliberately the
    same as demo_kofc.ps1's, because that sequence is the one that works:

        drop schema -> migrate_production.py -> init_db.py

    init_db.py is not optional and not interchangeable with calling the
    demo loader directly. It seeds DEFAULT_CHART_OF_ACCOUNTS and installs
    the audit triggers, THEN dispatches to the loader named by
    DEMO_DATASET. Calling load_kofc_form1295_demo_data.py on its own leaves
    the base accounts (1010, 3100, 4010, 5010, 5810) missing and the loader
    dies partway through posting opening balances.

    Written for Render's free Postgres, which is DELETED 30 days after
    creation rather than suspended. When that happens the recovery is:
    create a new database, run this against it, update two environment
    variables on the web service. The demo loader anchors open-invoice due
    dates to date.today(), so a rebuilt book is correctly aged on whatever
    day it is rebuilt.

    TWO THINGS THIS SCRIPT WORKS AROUND
    -----------------------------------
    1. load_kofc_form1295_demo_data.py catches every exception in main(),
       prints a traceback, and returns normally -- so the process exits 0
       even when the load failed completely. Exit codes cannot be trusted
       here, so step 4 asks the database whether the book actually exists.

    2. migrate_production.py seeds admin/admin123, and the loader then
       CLEARS that account's forced password change (get_admin_user ->
       clear_demo_password_change_prompt). Both credentials are published
       in a public repository, so the admin password is set AFTER the load,
       and this whole script is meant to run BEFORE the web service that
       exposes this database to the internet exists.

.PARAMETER DatabaseUrl
    The database's EXTERNAL connection string with owner credentials.
    Render shows this on the database's own page. The Internal URL is only
    reachable from inside Render and will not work from a workstation.

.PARAMETER AdminPassword
    Interim password for the 'admin' account. The account keeps
    must_change_password = True, so the first real login has to choose its
    own; this value only needs to survive until then.

.PARAMETER RuntimeRolePassword
    Password for the restricted role the web service connects as. Put this
    somewhere you can retrieve it -- it goes into RUNTIME_DATABASE_URL on
    Render, and the only way to recover it is to rerun setup_runtime_role.py
    with a new one.

.PARAMETER KeepSchema
    Skip the drop/recreate and migrate in place. Against the standing
    convention that a demo database is rebuilt from nothing, hence a flag.

.EXAMPLE
    .\provision_demo_db.ps1 `
        -DatabaseUrl $env:RENDER_DB `
        -AdminPassword "<interim>" `
        -RuntimeRolePassword "<long-lived>"
#>
param(
    [Parameter(Mandatory = $true)][string] $DatabaseUrl,
    [Parameter(Mandatory = $true)][string] $AdminPassword,
    [Parameter(Mandatory = $true)][string] $RuntimeRolePassword,
    [string] $RuntimeRole = 'cares_app',
    [switch] $KeepSchema,
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Section {
    param([string] $Text)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Assert-LastExitCode {
    param([string] $Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE. Nothing after this point was run."
    }
}

function Invoke-PythonSnippet {
    <# Run a Python snippet with the repo root on sys.path.

       The snippet goes to a temp file rather than being piped to `python -`,
       because piping to a native command's stdin from PowerShell is not
       something to rely on. PYTHONPATH is set because a script executed from
       %TEMP% gets %TEMP% as sys.path[0], so `from app import app` would fail
       with ModuleNotFoundError. #>
    param([string] $Name, [string] $Code)
    $temp = Join-Path $env:TEMP "cares_$Name.py"
    Set-Content -Path $temp -Value $Code -Encoding ASCII
    try {
        python $temp
        Assert-LastExitCode $Name
    }
    finally {
        Remove-Item $temp -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------------
# Confirmation. Everything below destroys data. demo_guard.py exists
# because a destructive reset should never be one mistyped argument
# away from a council's real books, so show which host is about to be
# rebuilt before doing anything.
# ------------------------------------------------------------------
$redacted = $DatabaseUrl -replace '://([^:]+):[^@]+@', '://$1:********@'
Write-Section "CARES demo database provisioning"
Write-Host "Target: $redacted"
Write-Host ""
if ($KeepSchema) {
    Write-Host "Schema will be KEPT (-KeepSchema). Demo data is still replaced."
} else {
    Write-Host "This DESTROYS everything in that database:"
    Write-Host "  - DROP SCHEMA public CASCADE: tables, sequences, triggers, extensions"
    Write-Host "  - all data, including the entire audit log"
}
Write-Host ""
if (-not $Force) {
    $answer = Read-Host "Type REBUILD to continue"
    if ($answer -cne 'REBUILD') {
        Write-Host "Aborted. Nothing was changed."
        exit 1
    }
}

# ------------------------------------------------------------------
# Environment
#
# FLASK_ENV is cleared: demo_guard.py refuses destructive resets when
# FLASK_ENV=production and DEMO_MODE is not 'true', and every loader
# below is destructive by design.
#
# RUNTIME_DATABASE_URL is cleared so app.py resolves to DATABASE_URL.
# Every step here needs the OWNER connection: DDL for migrations, and
# TRUNCATE on audit_log for the loader -- which the restricted role is
# specifically denied.
#
# PYTHONIOENCODING is set because these scripts print check marks and
# Windows' cp1252 console encoding raises UnicodeEncodeError on them.
#
# PYTHONPATH lets a script in %TEMP% import this repository's modules.
# ------------------------------------------------------------------
$env:DATABASE_URL     = $DatabaseUrl
$env:DEMO_MODE        = 'true'
$env:DEMO_DATASET     = 'kofc'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH       = $PSScriptRoot
Remove-Item Env:\FLASK_ENV            -ErrorAction SilentlyContinue
Remove-Item Env:\RUNTIME_DATABASE_URL -ErrorAction SilentlyContinue

# ------------------------------------------------------------------
# 1. Reset the schema
#
# DROP SCHEMA rather than deleting rows, for demo_kofc.ps1's reason:
# DELETE leaves sequences, triggers, extensions and any table a loader
# does not know about. pgcrypto and the audit triggers are reinstalled
# on the way back up by audit_schema.install_audit_triggers().
#
# PostgreSQL 15+ no longer grants CREATE on a fresh public schema to
# PUBLIC, so the grants are restored explicitly.
# ------------------------------------------------------------------
if ($KeepSchema) {
    Write-Section "Step 1 of 6: Schema reset SKIPPED (-KeepSchema)"
} else {
    Write-Section "Step 1 of 6: Dropping and recreating the public schema"
    Invoke-PythonSnippet -Name 'reset_schema' -Code @'
import os
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute('DROP SCHEMA public CASCADE')
    cur.execute('CREATE SCHEMA public')
    cur.execute('GRANT ALL ON SCHEMA public TO CURRENT_USER')
    cur.execute('GRANT ALL ON SCHEMA public TO PUBLIC')
    cur.execute('SELECT current_user')
    print('  schema public recreated, owned by %s' % cur.fetchone()[0])
conn.close()
'@
}

# ------------------------------------------------------------------
# 2. Tables, columns, organization, admin, RLS policies
# ------------------------------------------------------------------
Write-Section "Step 2 of 6: migrate_production.py"
Write-Host "Expect a warning that RLS policies are bypassed because this"
Write-Host "connection owns the tables. True right now; step 6 is the fix."
python migrate_production.py
Assert-LastExitCode "migrate_production.py"

# ------------------------------------------------------------------
# 3. Chart of accounts, audit triggers, and the council book
#
# NOT the loader directly. init_db.py seeds DEFAULT_CHART_OF_ACCOUNTS
# and installs the audit triggers before dispatching to the loader named
# by DEMO_DATASET. Skipping it leaves accounts 1010/3100/4010/5010/5810
# missing and the loader fails posting opening balances.
# ------------------------------------------------------------------
Write-Section "Step 3 of 6: init_db.py (chart of accounts + DEMO_DATASET=kofc)"
python init_db.py
Assert-LastExitCode "init_db.py"

# ------------------------------------------------------------------
# 4. Verify the load actually happened
#
# The loader swallows every exception in main() and returns normally, so
# the process exits 0 whether it succeeded or died halfway through
# posting opening balances. Ask the database instead.
# ------------------------------------------------------------------
Write-Section "Step 4 of 6: Verifying the demo book"
Invoke-PythonSnippet -Name 'verify_load' -Code @'
import os
import sys

import psycopg2

CHECKS = [
    ('base chart of accounts',
     "SELECT count(*) FROM chart_of_accounts "
     "WHERE account_number IN ('1010','3100','4010','5010','5810')", 5),
    ('chart of accounts total', 'SELECT count(*) FROM chart_of_accounts', 40),
    ('members',                 'SELECT count(*) FROM members', 30),
    ('projects',                'SELECT count(*) FROM projects', 5),
    ('journal entries',         'SELECT count(*) FROM journal_entries', 100),
    ('invoices',                'SELECT count(*) FROM invoices', 20),
    ('audit log rows',          'SELECT count(*) FROM audit_log', 100),
]

conn = psycopg2.connect(os.environ['DATABASE_URL'])
failed = []
with conn.cursor() as cur:
    for label, sql, minimum in CHECKS:
        try:
            cur.execute(sql)
            actual = cur.fetchone()[0]
        except Exception as exc:
            conn.rollback()
            print('  FAIL  %-24s query failed: %s' % (label, exc))
            failed.append(label)
            continue
        status = 'ok  ' if actual >= minimum else 'FAIL'
        print('  %s  %-24s %6d  (expected at least %d)' % (status, label, actual, minimum))
        if actual < minimum:
            failed.append(label)

    # A row with organization_id IS NULL belongs to nobody, and RLS omits it
    # from every query the application makes -- permanently, and without an
    # error. Reports that join through such a row silently report zero, so
    # counts look right while amounts are wrong. Checked here because it is
    # invisible from the application and obvious from the database.
    print('')
    for table in ('chart_of_accounts', 'journal_entries', 'journal_entry_lines',
                  'members', 'projects', 'invoices', 'membership_events',
                  'member_dues_payments'):
        try:
            cur.execute('SELECT count(*) FROM ' + table + ' WHERE organization_id IS NULL')
            orphans = cur.fetchone()[0]
        except Exception as exc:
            conn.rollback()
            print('  ....  %-24s org check skipped: %s' % (table, exc))
            continue
        if orphans:
            print('  FAIL  %-24s %6d row(s) with NULL organization_id' % (table, orphans))
            failed.append(table + ' (NULL organization_id)')
        else:
            print('  ok    %-24s all rows belong to an organization' % table)
conn.close()

if failed:
    print('')
    print('The demo load did not complete. Failing checks: %s' % ', '.join(failed))
    print('Scroll up to step 3 -- the loader prints its traceback but still')
    print('exits 0, so its own exit code did not report this.')
    sys.exit(1)

print('')
print('  Demo book verified.')
'@

# ------------------------------------------------------------------
# 5. Admin password
#
# After the load, never before: get_admin_user() clears
# must_change_password on whatever admin it finds, so a password set
# earlier would be left unprotected by the seed step.
# ------------------------------------------------------------------
Write-Section "Step 5 of 6: Admin password"
$env:CARES_NEW_ADMIN_PASSWORD = $AdminPassword
try {
    Invoke-PythonSnippet -Name 'set_admin_password' -Code @'
import os
import re
import sys

from app import app
from models import db, User

# Name the target before changing anything. DATABASE_URL falls back to a
# localhost dev default when it is unset or empty, so a mistyped or cleared
# variable silently edits a local database instead of the remote one, and
# the output otherwise looks identical either way.
print('  TARGET: %s' % re.sub(r'://([^:]+):[^@]+@', r'://\1:***@',
                              app.config['SQLALCHEMY_DATABASE_URI']))

password = os.environ['CARES_NEW_ADMIN_PASSWORD']

with app.app_context():
    admins = User.query.filter_by(role='Admin').all()
    if not admins:
        print('ERROR: no Admin user exists. Did migrate_production.py run?')
        sys.exit(1)
    for user in admins:
        user.set_password(password)
        # Kept True deliberately. The interim password exists only to keep
        # a publicly documented default off a public URL; the first real
        # login still has to choose its own.
        user.must_change_password = True
        print('  reset: %s (must_change_password = True)' % user.username)
    db.session.commit()
    print('  %d admin account(s) updated' % len(admins))
'@
}
finally {
    Remove-Item Env:\CARES_NEW_ADMIN_PASSWORD -ErrorAction SilentlyContinue
}

# ------------------------------------------------------------------
# 6. Restricted runtime role
#
# Last, so GRANT ON ALL TABLES covers the finished schema. The script
# verifies the role owns nothing and holds neither SUPERUSER nor
# BYPASSRLS before exiting. If that verdict is not clean, do not point a
# FLASK_ENV=production web service at this database -- app.py will
# refuse to serve and return 503 on every request.
# ------------------------------------------------------------------
Write-Section "Step 6 of 6: Restricted runtime role '$RuntimeRole'"
python setup_runtime_role.py --role $RuntimeRole --password $RuntimeRolePassword
Assert-LastExitCode "setup_runtime_role.py"

# ------------------------------------------------------------------
Write-Section "Provisioning complete"
Write-Host "Set exactly these four on the Render web service. No quotes around"
Write-Host "the values, and watch for trailing spaces -- both break silently."
Write-Host ""
Write-Host "  DATABASE_URL          <INTERNAL url, owner credentials>"
Write-Host "  RUNTIME_DATABASE_URL  <INTERNAL url, but user '$RuntimeRole' and"
Write-Host "                         the runtime role password>"
Write-Host "  SECRET_KEY            a 64-char hex value"
Write-Host "  FLASK_ENV             production"
Write-Host ""
Write-Host "Use the INTERNAL url on Render, not the external one used here, and"
Write-Host "make sure the scheme is postgresql:// -- SQLAlchemy 2.x rejects the"
Write-Host "shorter postgres:// form."
Write-Host ""
Write-Host "Do NOT set DEMO_MODE on the web service. Nothing in a serving"
Write-Host "process reads it, so it buys nothing -- but if the start command is"
Write-Host "ever changed to migrate_and_start.sh, DEMO_MODE=true is exactly what"
Write-Host "makes that script wipe and reseed the database on every boot. On a"
Write-Host "free instance that sleeps after 15 minutes, that is every boot."
Write-Host "Leaving it unset makes demo_guard.py refuse instead."
Write-Host ""
Write-Host "Translation is off unless ENABLE_TRANSLATION=true and GROQ_API_KEY"
Write-Host "are both set. Before enabling it, confirm DEFAULT_MODEL still exists"
Write-Host "-- GET https://api.groq.com/openai/v1/models. Providers retire models,"
Write-Host "and this one fails silently: the page just renders untranslated."
Write-Host ""
Write-Host "First login is 'admin' with the interim password. It forces a"
Write-Host "password change before anything else is reachable, so do that once"
Write-Host "now rather than in front of an audience."

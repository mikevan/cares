<#
.SYNOPSIS
    Provision a complete CARES / REGALIA demo database from an empty one.

.DESCRIPTION
    Rebuilds an entire demo deployment against a fresh PostgreSQL database:
    schema, row-level security, audit triggers, the Knights of Columbus
    council book, the restricted runtime role, and a non-default admin
    password.

    Written for Render's free Postgres, which expires 30 days after creation
    and is then DELETED rather than suspended. When that happens the recovery
    procedure is: create a new database, run this script against it, update
    two environment variables on the web service. That is all. The demo loader
    anchors open-invoice due dates to date.today(), so a rebuilt book is
    correctly aged on whatever day it is rebuilt -- a re-seed produces a
    fresher demo, not a staler one.

    THE ORDERING IS DELIBERATE, NOT INCIDENTAL
    ------------------------------------------
    migrate_production.py seeds admin/admin123 (published in a public repo),
    and load_kofc_form1295_demo_data.py then CLEARS that account's forced
    password change -- get_admin_user() calls clear_demo_password_change_prompt()
    on any admin it finds. So a database that has been migrated and seeded is
    sitting on a publicly documented credential with no forced rotation.

    The admin password is therefore set LAST, after the loader, and this whole
    script is meant to run BEFORE the web service that exposes the database to
    the internet exists. admin123 should never be reachable from a public URL,
    not even briefly.

.PARAMETER DatabaseUrl
    The database's EXTERNAL connection string, with owner credentials. Render
    shows this on the database's own page. The Internal URL is only reachable
    from inside Render and will not work from a workstation.

.PARAMETER AdminPassword
    Interim password for the 'admin' account. The account keeps
    must_change_password = True, so the first real login must choose its own
    password; this value only needs to survive until then.

.PARAMETER RuntimeRolePassword
    Password for the restricted role the web service connects as. Long-lived:
    it goes into RUNTIME_DATABASE_URL on Render. This role owns no tables and
    holds no SUPERUSER or BYPASSRLS, which is what makes the row-level security
    policies and the audit_log REVOKE actually apply.

.EXAMPLE
    .\provision_demo_db.ps1 `
        -DatabaseUrl "postgresql://cares_owner:PW@dpg-xxxx.virginia-postgres.render.com/cares" `
        -AdminPassword "<interim>" `
        -RuntimeRolePassword "<long-lived>"
#>
param(
    [Parameter(Mandatory = $true)][string] $DatabaseUrl,
    [Parameter(Mandatory = $true)][string] $AdminPassword,
    [Parameter(Mandatory = $true)][string] $RuntimeRolePassword,
    [string] $RuntimeRole = 'cares_app',
    [switch] $Force
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Section {
    param([string] $Text)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Text
    Write-Host "============================================================"
}

function Assert-LastExitCode {
    param([string] $Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE. Nothing after this point was run."
    }
}

# ------------------------------------------------------------------
# Confirmation. This script DESTROYS data -- the demo loader wipes
# before it seeds and truncates audit_log. The whole point of
# demo_guard.py is that a destructive reset should never be one
# mistyped argument away from a council's real books, so show the
# operator exactly which host is about to be rebuilt.
# ------------------------------------------------------------------
$redacted = $DatabaseUrl -replace '://([^:]+):[^@]+@', '://$1:********@'
Write-Section "CARES demo database provisioning"
Write-Host "Target: $redacted"
Write-Host ""
Write-Host "This DESTROYS all existing data in that database:"
Write-Host "  - transactional data is wiped and reseeded by the demo loader"
Write-Host "  - audit_log is TRUNCATEd, discarding all existing history"
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
# FLASK_ENV is deliberately cleared: demo_guard.py refuses destructive
# resets when FLASK_ENV=production and DEMO_MODE is not 'true', and the
# loaders are destructive by design.
#
# RUNTIME_DATABASE_URL is cleared so app.py resolves to DATABASE_URL --
# every step here needs the OWNER connection. Migrations need it for DDL,
# and the loader needs TRUNCATE on audit_log, which the restricted role
# is specifically denied.
#
# PYTHONIOENCODING is set because migrate_production.py and the loaders
# print check marks, and Windows' cp1252 console encoding raises
# UnicodeEncodeError on them -- a known, previously-hit failure in this
# repository.
# ------------------------------------------------------------------
$env:DATABASE_URL     = $DatabaseUrl
$env:DEMO_MODE        = 'true'
$env:DEMO_DATASET     = 'kofc'
$env:PYTHONIOENCODING = 'utf-8'
Remove-Item Env:\FLASK_ENV            -ErrorAction SilentlyContinue
Remove-Item Env:\RUNTIME_DATABASE_URL -ErrorAction SilentlyContinue

# ------------------------------------------------------------------
# 1. Schema, row-level security, audit triggers
# ------------------------------------------------------------------
Write-Section "Step 1 of 4: Schema, RLS and audit triggers"
python migrate_production.py
Assert-LastExitCode "migrate_production.py"

# ------------------------------------------------------------------
# 2. The council book
# ------------------------------------------------------------------
Write-Section "Step 2 of 4: Knights of Columbus demo data"
python load_kofc_form1295_demo_data.py
Assert-LastExitCode "load_kofc_form1295_demo_data.py"

# ------------------------------------------------------------------
# 3. Admin password
#
# After the loader, never before: get_admin_user() clears
# must_change_password on whatever admin it finds, so a password set
# earlier would be left unprotected by the seed step.
# ------------------------------------------------------------------
Write-Section "Step 3 of 4: Admin password"
$setAdminPassword = @'
import os
import sys

from app import app
from models import db, User

password = os.environ['CARES_NEW_ADMIN_PASSWORD']

with app.app_context():
    admins = User.query.filter_by(role='Admin').all()
    if not admins:
        print('ERROR: no Admin user exists. Did migrate_production.py run?')
        sys.exit(1)
    for user in admins:
        user.set_password(password)
        # Kept True on purpose. The interim password above exists only to
        # keep a publicly documented default off a public URL; the first
        # real login still has to choose its own.
        user.must_change_password = True
        print('  reset: %s (must_change_password = True)' % user.username)
    db.session.commit()
    print('OK   %d admin account(s) updated' % len(admins))
'@
$env:CARES_NEW_ADMIN_PASSWORD = $AdminPassword
$tempScript = Join-Path $env:TEMP 'cares_set_admin_password.py'
Set-Content -Path $tempScript -Value $setAdminPassword -Encoding ASCII
try {
    python $tempScript
    Assert-LastExitCode "admin password reset"
}
finally {
    Remove-Item $tempScript                      -ErrorAction SilentlyContinue
    Remove-Item Env:\CARES_NEW_ADMIN_PASSWORD    -ErrorAction SilentlyContinue
}

# ------------------------------------------------------------------
# 4. Restricted runtime role
#
# Last, so its GRANT ON ALL TABLES covers the finished schema. The script
# verifies the role owns nothing and holds neither SUPERUSER nor BYPASSRLS
# before it exits -- if that check fails, the web service must not be
# pointed at this database in production, because app.py will refuse to
# serve and return 503 on every request.
# ------------------------------------------------------------------
Write-Section "Step 4 of 4: Restricted runtime role '$RuntimeRole'"
python setup_runtime_role.py --role $RuntimeRole --password $RuntimeRolePassword
Assert-LastExitCode "setup_runtime_role.py"

# ------------------------------------------------------------------
# What to do next
# ------------------------------------------------------------------
Write-Section "Provisioning complete"
Write-Host "Set these on the Render web service, then deploy:"
Write-Host ""
Write-Host "  DATABASE_URL          <INTERNAL url from Render, owner credentials>"
Write-Host "  RUNTIME_DATABASE_URL  <same INTERNAL url, but user '$RuntimeRole'"
Write-Host "                         and the runtime role password>"
Write-Host "  SECRET_KEY            python -c `"import secrets; print(secrets.token_hex(32))`""
Write-Host "  FLASK_ENV             production"
Write-Host "  DEMO_MODE             true"
Write-Host "  ENABLE_TRANSLATION    true"
Write-Host "  GROQ_API_KEY          <key>"
Write-Host ""
Write-Host "Use the INTERNAL url on Render, not the external one used here."
Write-Host "First login is 'admin' with the interim password; it will require"
Write-Host "a new password before anything else can be reached."

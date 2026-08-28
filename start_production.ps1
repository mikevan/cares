#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Start REGALIA for a real chapter. Never loads or deletes data.

.DESCRIPTION
    The production startup path. It applies schema migrations and starts
    the application. That is all it does.

    This script shares no code path with demo_kofc.ps1. It does not call
    init_db.py, load_comprehensive_data.py, or load_kofc_form1295_demo_data.py,
    and it sets no DEMO_MODE or DEMO_DATASET variable. There is no flag on
    this script that loads demo data, because the separation is the point:
    a chapter's books should not be one mistyped switch away from being
    replaced with fiction.

    Standing policy: a production update never reloads data.

.PARAMETER Initialize
    FIRST RUN ONLY, when onboarding a new chapter. Runs init_chapter.py to
    create the organization, its first administrator, the chart of
    accounts, and the audit triggers -- an empty set of books. Requires
    -CouncilName, -AdminUsername and -AdminEmail.

    init_chapter.py refuses to run if an organization already exists, so
    passing this by accident on a live deployment is safe: it stops.

.PARAMETER CouncilName
    The chapter or council name. Required with -Initialize.

.PARAMETER CouncilNumber
    Knights of Columbus council number, printed on Form 1295.

.PARAMETER AdminUsername
    Username for the first administrator. Required with -Initialize.

.PARAMETER AdminEmail
    Email for the first administrator. Required with -Initialize.

.PARAMETER DuesAmount
    Annual dues per member. Can also be set later in Settings, but the
    Annual Dues Roster refuses to post while it is unset.

.PARAMETER SkipMigrate
    Start the app without running migrations. Use when you have already
    migrated and just want the server back up.

.PARAMETER Port
    Port to serve on. Default 5000.

.EXAMPLE
    .\start_production.ps1
    Apply any pending schema changes and start the app. The routine case.

.EXAMPLE
    .\start_production.ps1 -Initialize -CouncilName "Bishop Kelley Council" `
        -CouncilNumber 14203 -AdminUsername jsmith -AdminEmail jsmith@example.org
    Onboard a brand new chapter, then start.
#>
[CmdletBinding()]
param(
    [switch]$Initialize,
    [string]$CouncilName,
    [string]$CouncilNumber,
    [string]$AdminUsername,
    [string]$AdminEmail,
    [decimal]$DuesAmount,
    [switch]$SkipMigrate,
    [int]$Port = 5000
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host '============================================' -ForegroundColor Cyan
}
function Write-Ok   { param([string]$T) Write-Host "  OK   $T" -ForegroundColor Green }
function Write-Info { param([string]$T) Write-Host "       $T" -ForegroundColor Gray }

function Invoke-Step {
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host "ERROR: $FailureMessage (exit code $LASTEXITCODE)" -ForegroundColor Red
        Write-Host 'Stopping. The application will not be started.' -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Step 'REGALIA - production startup'
Write-Host '  This script never loads demo data and never deletes data.' -ForegroundColor Gray

# ------------------------------------------------------------
# Environment
# ------------------------------------------------------------
if (-not $env:DATABASE_URL) {
    Write-Host 'ERROR: DATABASE_URL is not set.' -ForegroundColor Red
    Write-Host 'A production deployment must point at its own database explicitly' -ForegroundColor Red
    Write-Host 'rather than falling back to the local development default.' -ForegroundColor Red
    exit 1
}
if (-not $env:SECRET_KEY) {
    Write-Host 'ERROR: SECRET_KEY is not set.' -ForegroundColor Red
    Write-Host 'Running with the built-in development key breaks session signing.' -ForegroundColor Red
    exit 1
}
Write-Ok 'DATABASE_URL and SECRET_KEY are set.'

# Deliberately NOT set here: DEMO_MODE and DEMO_DATASET. Their absence is
# what makes demo_guard.py refuse a destructive reset if any demo code is
# ever reached from a production box by another route.
$env:FLASK_ENV = 'production'
if ($env:DEMO_MODE) {
    Write-Host ''
    Write-Host "WARNING: DEMO_MODE is set to '$($env:DEMO_MODE)' in this environment." -ForegroundColor Yellow
    Write-Host 'On a real chapter deployment it should be unset. While it is set,' -ForegroundColor Yellow
    Write-Host 'demo loaders run by any other route would be permitted to wipe data.' -ForegroundColor Yellow
    Write-Host ''
}

$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path $VenvPython) { $VenvPython } else { 'python' }

# ------------------------------------------------------------
# First-run chapter initialization
# ------------------------------------------------------------
if ($Initialize) {
    Write-Step 'Initializing a new chapter (first run only)'

    $missing = @()
    if (-not $CouncilName)   { $missing += '-CouncilName' }
    if (-not $AdminUsername) { $missing += '-AdminUsername' }
    if (-not $AdminEmail)    { $missing += '-AdminEmail' }
    if ($missing.Count -gt 0) {
        Write-Host "ERROR: -Initialize requires $($missing -join ', ')." -ForegroundColor Red
        exit 1
    }

    $initArgs = @(
        'init_chapter.py',
        '--council-name',   $CouncilName,
        '--admin-username', $AdminUsername,
        '--admin-email',    $AdminEmail
    )
    if ($CouncilNumber) { $initArgs += @('--council-number', $CouncilNumber) }
    if ($PSBoundParameters.ContainsKey('DuesAmount')) {
        $initArgs += @('--dues-amount', $DuesAmount.ToString())
    }

    Invoke-Step -Command { & $Python @initArgs } `
        -FailureMessage 'Chapter initialization failed (or was refused because a chapter already exists).'
    Write-Ok 'Chapter initialized with empty books.'
}

# ------------------------------------------------------------
# Migrations
# ------------------------------------------------------------
if ($SkipMigrate) {
    Write-Step 'Migrations - SKIPPED (-SkipMigrate)'
} else {
    Write-Step 'Applying schema migrations'
    Write-Info 'Structural only. migrate_production.py will not reset the admin'
    Write-Info 'password or reload data while FLASK_ENV=production.'
    Invoke-Step -Command { & $Python migrate_production.py } `
        -FailureMessage 'migrate_production.py failed.'
    Write-Ok 'Schema is up to date. No data was modified.'
}

# ------------------------------------------------------------
# Serve
# ------------------------------------------------------------
Write-Step 'Starting REGALIA'
Write-Host ''
Write-Host "  http://localhost:$Port" -ForegroundColor White
Write-Host ''

$gunicorn = Join-Path $PSScriptRoot '.venv\Scripts\gunicorn.exe'
if (Test-Path $gunicorn) {
    & $gunicorn 'app:app' --bind "0.0.0.0:$Port" --workers 2 --timeout 120
} else {
    Write-Info 'gunicorn not available on Windows - using the Flask server.'
    Write-Info 'For a real deployment, serve behind a production WSGI server.'
    $env:FLASK_APP = 'app.py'
    & $Python -m flask run --host=0.0.0.0 --port=$Port
}

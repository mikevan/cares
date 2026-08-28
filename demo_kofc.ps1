#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One command to build the Knights of Columbus (REGALIA) demo from scratch.

.DESCRIPTION
    This database is a DEMO database. It is treated as disposable and
    rebuilt from nothing on every run -- schema dropped, schema recreated,
    migrations applied, demo data loaded, audit trail rebuilt from
    genesis. Nothing in it is expected to survive, and nothing in it
    should ever be the only copy of anything.

    That is deliberate, and it is the same reason a CI pipeline builds
    from a clean checkout: a demo you can only reproduce by remembering
    which scripts you ran in which order is not reproducible. Every run of
    this script produces byte-for-byte the same book.

    Default run:
      1. Ensure the PostgreSQL container exists and accepts connections
      2. DROP SCHEMA public CASCADE / CREATE SCHEMA public
      3. migrate_production.py   -- tables, columns, org, admin
      4. init_db.py              -- full chart of accounts, audit triggers,
                                    and (DEMO_DATASET=kofc) the council
                                    demo loader
      5. Start Flask

    Why dropping the schema rather than deleting rows: DELETE leaves
    behind sequences, triggers, extensions, and any table a loader does
    not know about. DROP SCHEMA leaves nothing, so a stale column or an
    orphaned trigger from an older revision cannot quietly survive into
    the demo. pgcrypto and the audit triggers are reinstalled on the way
    back up.

.PARAMETER Recreate
    Also destroy and recreate the Docker container itself, not just the
    schema. Slower. Use when you suspect the Postgres instance rather than
    the data -- wrong version, corrupt volume, changed roles.

.PARAMETER SkipReset
    Do NOT wipe. Leave the database exactly as it is and just start the
    app. This is the escape hatch for when you have been entering data by
    hand and want to keep it -- against the standing convention, so it is
    a flag rather than the default.

.PARAMETER SkipStart
    Build the database but do not start Flask.

.PARAMETER Backup
    pg_dump into .\backups\ before wiping. The demo database is disposable
    by policy, so this is off by default; use it when you have entered
    something you have not yet reproduced in the loader.

.PARAMETER Port
    Port for the Flask dev server. Default 5000.

.EXAMPLE
    .\demo_kofc.ps1
    Full rebuild from nothing, then start the app.

.EXAMPLE
    .\demo_kofc.ps1 -SkipReset
    Start the app against the database as it currently stands.

.EXAMPLE
    .\demo_kofc.ps1 -Recreate -SkipStart
    Brand new container and database, no app.
#>
[CmdletBinding()]
param(
    [switch]$Recreate,
    [switch]$SkipReset,
    [switch]$SkipStart,
    [switch]$Backup,
    [int]$Port = 5000
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$ContainerName = 'kofc-postgres'
$DbUser        = 'postgres'
$DbName        = 'kofc_accounting'
$DbPassword    = 'dev123'

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host '============================================' -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host '============================================' -ForegroundColor Cyan
}

function Write-Ok   { param([string]$T) Write-Host "  OK   $T" -ForegroundColor Green }
function Write-Info { param([string]$T) Write-Host "       $T" -ForegroundColor Gray }
function Write-Warn { param([string]$T) Write-Host "  WARN $T" -ForegroundColor Yellow }

function Invoke-Step {
    <# Run a native command and stop the script if it fails. PowerShell
       does not do this on its own for native executables -- it carries on
       past a non-zero exit code, which is how you end up starting Flask
       against a database whose migration failed. #>
    param([scriptblock]$Command, [string]$FailureMessage)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host "ERROR: $FailureMessage (exit code $LASTEXITCODE)" -ForegroundColor Red
        Write-Host 'Stopping rather than continuing against a broken database.' -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Wait-ForPostgres {
    Write-Info 'Waiting for PostgreSQL to accept connections...'
    for ($i = 1; $i -le 30; $i++) {
        docker exec $ContainerName pg_isready -U $DbUser *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok 'PostgreSQL is accepting connections.'
            return
        }
        Start-Sleep -Seconds 1
    }
    Write-Host 'ERROR: PostgreSQL did not become ready within 30 seconds.' -ForegroundColor Red
    Write-Host "Check: docker logs $ContainerName" -ForegroundColor Red
    exit 1
}

function New-DatabaseContainer {
    Invoke-Step -Command {
        docker run --name $ContainerName `
            -e POSTGRES_PASSWORD=$DbPassword `
            -e POSTGRES_DB=$DbName `
            -p 5432:5432 `
            -d postgres:15-alpine
    } -FailureMessage 'Could not create the PostgreSQL container. Is port 5432 in use?'
}

# ============================================================
# Step 1: Prerequisites
# ============================================================
Write-Step 'Step 1: Prerequisites'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: docker was not found on PATH. Install Docker Desktop.' -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: Docker is installed but not running. Start Docker Desktop.' -ForegroundColor Red
    exit 1
}
Write-Ok 'Docker is running.'

$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Ok 'Using the repo virtual environment (.venv).'
} else {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host 'ERROR: no .venv and no python on PATH.' -ForegroundColor Red
        exit 1
    }
    $Python = 'python'
    Write-Warn 'No .venv found -- falling back to the python on PATH.'
}

# ============================================================
# Step 2: Container
# ============================================================
Write-Step 'Step 2: PostgreSQL container'

$exists = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch $ContainerName

if ($Recreate -and $exists) {
    Write-Info 'Destroying the existing container (-Recreate).'
    docker stop $ContainerName *> $null
    docker rm $ContainerName *> $null
    $exists = $null
}

if (-not $exists) {
    Write-Info "Creating '$ContainerName'."
    New-DatabaseContainer
    Write-Ok 'Container created.'
} else {
    $running = docker ps --format '{{.Names}}' | Select-String -SimpleMatch $ContainerName
    if ($running) { Write-Ok 'Container is already running.' }
    else { docker start $ContainerName | Out-Null; Write-Ok 'Container started.' }
}

Wait-ForPostgres

# ============================================================
# Step 3: Optional backup
# ============================================================
Write-Step 'Step 3: Backup'

if ($Backup -and -not $SkipReset) {
    $backupDir = Join-Path $PSScriptRoot 'backups'
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir | Out-Null }
    $stamp      = Get-Date -Format 'yyyy-MM-dd_HHmmss'
    $backupFile = Join-Path $backupDir "kofc_$stamp.sql"

    # Dump inside the container and copy the file out, rather than
    # redirecting pg_dump's stdout with '>'. Windows PowerShell 5.1 writes
    # UTF-16 on redirection, which silently corrupts a SQL dump -- the same
    # encoding trap that produced the UTF-16 errors.log already in this repo.
    Invoke-Step -Command {
        docker exec $ContainerName pg_dump -U $DbUser -d $DbName -f /tmp/kofc_backup.sql
    } -FailureMessage 'pg_dump failed.'
    Invoke-Step -Command {
        docker cp "${ContainerName}:/tmp/kofc_backup.sql" $backupFile
    } -FailureMessage 'Could not copy the dump out of the container.'

    $sizeKb = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
    Write-Ok "Backed up to backups\kofc_$stamp.sql ($sizeKb KB)"
    Write-Info 'Restore with:'
    Write-Info "  docker cp `"backups\kofc_$stamp.sql`" ${ContainerName}:/tmp/restore.sql"
    Write-Info "  docker exec $ContainerName psql -U $DbUser -d $DbName -f /tmp/restore.sql"
} elseif ($SkipReset) {
    Write-Info 'Not wiping (-SkipReset), so there is nothing to back up.'
} else {
    Write-Info 'Skipped. This demo database is disposable by policy -- it is'
    Write-Info 'rebuilt from the loader every run. Pass -Backup if you have'
    Write-Info 'entered something you have not reproduced in the loader yet.'
}

# ============================================================
# Step 4: Wipe
# ============================================================
if ($SkipReset) {
    Write-Step 'Step 4: Wipe -- SKIPPED (-SkipReset)'
    Write-Warn 'Leaving the existing database in place. This is against the'
    Write-Warn 'standing convention that the demo is rebuilt from scratch.'
} else {
    Write-Step 'Step 4: Dropping the schema'
    Write-Info 'DROP SCHEMA public CASCADE -- tables, sequences, triggers,'
    Write-Info 'extensions, and the audit log. Nothing is preserved.'

    # PostgreSQL 15 no longer grants CREATE on a fresh public schema to
    # PUBLIC, so the grants are restored explicitly rather than assumed.
    $sql = @'
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
'@
    Invoke-Step -Command {
        docker exec $ContainerName psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1 -c $sql
    } -FailureMessage 'Could not drop and recreate the public schema.'
    Write-Ok 'Schema is empty.'
}

# ============================================================
# Step 5: Rebuild
# ============================================================
if ($SkipReset) {
    Write-Step 'Step 5: Rebuild -- SKIPPED (-SkipReset)'
} else {
    Write-Step 'Step 5: Rebuilding the database'

    Write-Info 'migrate_production.py -- tables, columns, organization, admin.'
    Invoke-Step -Command { & $Python migrate_production.py } `
        -FailureMessage 'migrate_production.py failed.'

    Write-Info 'init_db.py -- full chart of accounts, audit triggers, demo data.'
    Write-Info 'DEMO_DATASET=kofc selects the council loader over the generic one.'
    # DEMO_MODE declares this a demo instance to demo_guard.py, which is
    # what permits a destructive reset. Set explicitly so this script still
    # works on a machine whose FLASK_ENV happens to say production -- and,
    # more to the point, so that NOT setting it is what protects a real
    # deployment.
    $env:DEMO_MODE    = 'true'
    $env:DEMO_DATASET = 'kofc'
    Invoke-Step -Command { & $Python init_db.py } `
        -FailureMessage 'init_db.py failed.'

    Write-Ok 'Database rebuilt and demo data loaded.'
}

# ============================================================
# Step 6: Start
# ============================================================
if ($SkipStart) {
    Write-Step 'Done -- not starting Flask (-SkipStart)'
    Write-Info 'Start it with:'
    Write-Info "  `$env:FLASK_APP = 'app.py'; `$env:FLASK_ENV = 'development'"
    Write-Info "  $Python -m flask run --host=0.0.0.0 --port=$Port"
    exit 0
}

Write-Step 'Step 6: Starting REGALIA'
Write-Host ''
Write-Host "  http://localhost:$Port" -ForegroundColor White
Write-Host ''
Write-Host '  Login:            admin / admin123' -ForegroundColor Gray
Write-Host "  Form 1295:        http://localhost:$Port/audit/form-1295" -ForegroundColor Gray
Write-Host "  Trustee audit:    http://localhost:$Port/audit/log" -ForegroundColor Gray
Write-Host ''
Write-Host '  Ctrl+C to stop. The container keeps running; stop it with:' -ForegroundColor Gray
Write-Host "    docker stop $ContainerName" -ForegroundColor Gray
Write-Host ''

$env:FLASK_APP = 'app.py'
$env:FLASK_ENV = 'development'
& $Python -m flask run --host=0.0.0.0 --port=$Port

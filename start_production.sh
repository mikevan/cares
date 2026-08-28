#!/bin/bash
# REGALIA -- production startup (Linux / Render)
# =============================================
#
# Applies schema migrations and starts the application. That is all.
#
# This script shares no code path with the demo startup. It does not call
# init_db.py, load_comprehensive_data.py, or load_kofc_form1295_demo_data.py,
# and it sets no DEMO_MODE or DEMO_DATASET. There is no flag here that
# loads demo data, because the separation is the point: a chapter's books
# should not be one mistyped switch away from being replaced with fiction.
#
# Standing policy: a production update never reloads data.
#
# Usage:
#   ./start_production.sh
#       Routine deploy. Migrate, then serve.
#
#   ./start_production.sh --initialize \
#       --council-name "Bishop Kelley Council" \
#       --council-number 14203 \
#       --admin-username jsmith \
#       --admin-email jsmith@example.org
#       FIRST RUN ONLY, onboarding a new chapter. Creates the organization,
#       its first administrator, the chart of accounts, and the audit
#       triggers -- an empty set of books -- then migrates and serves.
#
#       init_chapter.py refuses to run if an organization already exists,
#       so passing this by accident on a live deployment is safe.
#
# Render: set this as the start command. Leave DEMO_MODE unset.

set -euo pipefail

cd "$(dirname "$0")"

INITIALIZE=false
INIT_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --initialize)
            INITIALIZE=true
            shift
            ;;
        --council-name|--council-number|--district-deputy|--admin-username|\
        --admin-email|--dues-amount|--ein|--city|--state|--email|--fiscal-year-start)
            INIT_ARGS+=("$1" "${2:-}")
            shift 2
            ;;
        --port)
            PORT="${2:-}"
            shift 2
            ;;
        --skip-migrate)
            SKIP_MIGRATE=true
            shift
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "See the comments at the top of this script for usage." >&2
            exit 1
            ;;
    esac
done

PORT="${PORT:-5000}"
SKIP_MIGRATE="${SKIP_MIGRATE:-false}"

echo "============================================"
echo "REGALIA - production startup"
echo "============================================"
echo "This script never loads demo data and never deletes data."
echo ""

# ------------------------------------------------------------
# Environment
# ------------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set." >&2
    echo "A production deployment must point at its own database explicitly" >&2
    echo "rather than falling back to the local development default." >&2
    exit 1
fi
if [ -z "${SECRET_KEY:-}" ]; then
    echo "ERROR: SECRET_KEY is not set." >&2
    echo "Running with the built-in development key breaks session signing." >&2
    exit 1
fi
echo "OK   DATABASE_URL and SECRET_KEY are set."

# Deliberately NOT set here: DEMO_MODE and DEMO_DATASET. Their absence is
# what makes demo_guard.py refuse a destructive reset if any demo code is
# ever reached from a production box by another route.
export FLASK_ENV=production

if [ "${DEMO_MODE:-}" = "true" ]; then
    echo ""
    echo "WARNING: DEMO_MODE=true is set in this environment."
    echo "On a real chapter deployment it should be unset. While it is set,"
    echo "demo loaders run by any other route would be permitted to wipe data."
    echo ""
fi

PYTHON_CMD="python3"
command -v python3 >/dev/null 2>&1 || PYTHON_CMD="python"

# ------------------------------------------------------------
# First-run chapter initialization
# ------------------------------------------------------------
if [ "$INITIALIZE" = true ]; then
    echo ""
    echo "Step 1: Initializing a new chapter (first run only)"
    echo "----------------------------------------"
    if ! $PYTHON_CMD init_chapter.py "${INIT_ARGS[@]}"; then
        echo ""
        echo "ERROR: chapter initialization failed, or was refused because a" >&2
        echo "chapter already exists in this database." >&2
        exit 1
    fi
    echo "OK   Chapter initialized with empty books."
fi

# ------------------------------------------------------------
# Migrations
# ------------------------------------------------------------
if [ "$SKIP_MIGRATE" = true ]; then
    echo ""
    echo "Migrations SKIPPED (--skip-migrate)."
else
    echo ""
    echo "Step 2: Applying schema migrations"
    echo "----------------------------------------"
    echo "Structural only. migrate_production.py will not reset the admin"
    echo "password or reload data while FLASK_ENV=production."
    if ! $PYTHON_CMD migrate_production.py; then
        echo "" >&2
        echo "ERROR: migrate_production.py failed. Not starting the app." >&2
        exit 1
    fi
    echo "OK   Schema is up to date. No data was modified."
fi

# ------------------------------------------------------------
# Serve
# ------------------------------------------------------------
echo ""
echo "Step 3: Starting the application on port ${PORT}"
echo "----------------------------------------"

if command -v gunicorn >/dev/null 2>&1; then
    exec gunicorn app:app --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
else
    echo "WARNING: gunicorn not found; falling back to the Flask dev server." >&2
    echo "Install gunicorn for a real deployment." >&2
    export FLASK_APP=app.py
    exec $PYTHON_CMD -m flask run --host=0.0.0.0 --port="${PORT}"
fi

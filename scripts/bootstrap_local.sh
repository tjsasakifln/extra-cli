#!/bin/bash
# ==============================================================================
# bootstrap_local.sh — Bootstrap Local Development Database
# ==============================================================================
#
# Usage:
#   ./scripts/bootstrap_local.sh              # Normal execution (idempotent)
#   ./scripts/bootstrap_local.sh --reset      # Re-run all steps from scratch
#   ./scripts/bootstrap_local.sh --dry-run    # Show what would be done
#
# Description:
#   4-step idempotent bootstrap for the Extra Consultoria local dev database:
#     1. create_db   — Start PostgreSQL container and verify database
#     2. run_migrations — Apply pending SQL migrations
#     3. load_seed   — Load seed data (sc_public_entities + canonical universe)
#     4. verify_fingerprint — Validate QW-01 schema fingerprint
#
#   Safe to run multiple times. Second execution is a no-op.
#
# Prerequisites:
#   - Docker (compose plugin)
#   - psql (PostgreSQL client)
#   - Python 3.12 (for seed and verify steps)
# ==============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.local.yml"
MIGRATIONS_DIR="${PROJECT_ROOT}/supabase/migrations"
LOG_DIR="${PROJECT_ROOT}/output/bootstrap"

DB_HOST="localhost"
DB_PORT="5433"
DB_USER="test"
DB_PASSWORD="test"
DB_NAME="extra_test"
DB_MAINT_DB="postgres"

PSQL_BASE="${PSQL_BASE:-psql -h ${DB_HOST} -p ${DB_PORT} -U ${DB_USER}}"
export PGPASSWORD="${DB_PASSWORD}"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
RESET=false
DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --reset) RESET=true ;;
        --dry-run) DRY_RUN=true ;;
    esac
done

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/bootstrap-$(date +%Y%m%d-%H%M%S).log"

# Tee all output to both terminal and log file
exec > >(tee -a "${LOG_FILE}") 2>&1

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
info()    { echo -e "[BOOTSTRAP] $1"; }
ok()      { echo -e "${GREEN}[OK]${NC}      $1"; }
done_msg(){ echo -e "${GREEN}[DONE]${NC}    $1"; }
skip()    { echo -e "${YELLOW}[SKIP]${NC}   $1"; }
fail()    { echo -e "${RED}[FAIL]${NC}    $1"; }

# Run a psql command; returns exit code
psql_run() {
    ${PSQL_BASE} -d "$1" -c "$2" 2>/dev/null
}

psql_file() {
    ${PSQL_BASE} -d "$1" -f "$2" 2>&1
}

# ---------------------------------------------------------------------------
# Guard: check if database is accessible
# ---------------------------------------------------------------------------
db_is_accessible() {
    ${PSQL_BASE} -d "${DB_NAME}" -c "SELECT 1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Guard: check if table exists in public schema
# ---------------------------------------------------------------------------
table_exists() {
    local table="$1"
    local result
    result=$(${PSQL_BASE} -d "${DB_NAME}" -t -A -c \
        "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public' AND tablename='${table}'" 2>/dev/null)
    [ "${result}" = "1" ] 2>/dev/null
}

# ---------------------------------------------------------------------------
# Guard: get row count of a table
# ---------------------------------------------------------------------------
table_row_count() {
    local table="$1"
    if table_exists "${table}"; then
        ${PSQL_BASE} -d "${DB_NAME}" -t -A -c "SELECT COUNT(*) FROM public.${table}" 2>/dev/null || echo "0"
    else
        echo "-1"
    fi
}

# ---------------------------------------------------------------------------
# Dry-run helper
# ---------------------------------------------------------------------------
dry() {
    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] $*"
        return 0
    fi
    return 1
}

# ============================================================================
# STEP 1: create_db — Start PostgreSQL container and verify database
# ============================================================================
step_create_db() {
    echo ""
    info "STEP 1/4: create_db — Starting PostgreSQL container..."

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] docker compose -f ${COMPOSE_FILE} up -d test-db"
        echo "  [DRY-RUN] Wait for healthcheck (pg_isready)"
        echo "  [DRY-RUN] Verify database '${DB_NAME}' exists"
        return 0
    fi

    # Guard: check if container is already healthy and DB exists
    if docker compose -f "${COMPOSE_FILE}" ps test-db --format json 2>/dev/null | \
       grep -q '"Health": "healthy"' 2>/dev/null; then
        if ${PSQL_BASE} -d "${DB_MAINT_DB}" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
            ok "PostgreSQL is already running and database '${DB_NAME}' exists"
            return 0
        fi
    fi

    # --reset: destroy and recreate container (tmpfs guarantees clean state)
    if [ "$RESET" = true ]; then
        echo "  [--reset] Stopping and removing test-db container..."
        docker compose -f "${COMPOSE_FILE}" down test-db 2>/dev/null || true
        # Small pause to ensure clean state
        sleep 2
    fi

    # Start the database container (with healthcheck)
    echo "  Starting test-db container..."
    if ! docker compose -f "${COMPOSE_FILE}" up -d test-db; then
        fail "Failed to start test-db container"
        return 1
    fi

    # Wait for Docker healthcheck to pass (max 60s)
    echo "  Waiting for PostgreSQL healthcheck..."
    local attempts=0
    until docker compose -f "${COMPOSE_FILE}" exec -T test-db pg_isready -U "${DB_USER}" -d "${DB_NAME}" 2>/dev/null; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 30 ]; then
            fail "PostgreSQL did not become ready after 30 attempts (60s)"
            docker compose -f "${COMPOSE_FILE}" logs test-db --tail 20
            return 1
        fi
        sleep 2
    done
    echo "  PostgreSQL healthcheck PASSED"

    # Verify the database exists (or create it)
    if ! ${PSQL_BASE} -d "${DB_MAINT_DB}" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
        echo "  Creating database '${DB_NAME}'..."
        ${PSQL_BASE} -d "${DB_MAINT_DB}" -c "CREATE DATABASE ${DB_NAME};"
    fi

    done_msg "PostgreSQL is running and database '${DB_NAME}' is ready"
}

# ============================================================================
# STEP 2: run_migrations — Apply pending SQL migrations
# ============================================================================
step_run_migrations() {
    echo ""
    info "STEP 2/4: run_migrations — Applying pending migrations..."

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] Would apply migrations from: ${MIGRATIONS_DIR}"
        echo "  [DRY-RUN] Migrations found:"
        for f in "${MIGRATIONS_DIR}"/*.sql; do
            local basename
            basename=$(basename "$f")
            echo "    - ${basename}"
        done
        return 0
    fi

    # Guard: check if sc_public_entities table exists (quick indicator)
    if table_exists "sc_public_entities"; then
        # Check _migrations table for full tracking
        if table_exists "_migrations"; then
            local applied_count
            applied_count=$(${PSQL_BASE} -d "${DB_NAME}" -t -A -c \
                "SELECT COUNT(*) FROM public._migrations" 2>/dev/null || echo "0")
            local total_migrations
            # Count non-_migrations SQL files (the _migrations.sql tracks itself separately)
            total_migrations=$(find "${MIGRATIONS_DIR}" -name '*.sql' ! -name '_migrations.sql' | wc -l)
            total_migrations=$((total_migrations + 1))  # +1 for _migrations.sql itself
            if [ "${applied_count}" -ge "${total_migrations}" ] 2>/dev/null; then
                ok "All ${applied_count} migrations already applied (tracked by _migrations table)"
                return 0
            fi
        fi
    fi

    echo "  Checking migration status..."

    # Collect all SQL files, sorted naturally
    local sql_files=()
    # _migrations.sql first, then numbered migrations
    if [ -f "${MIGRATIONS_DIR}/_migrations.sql" ]; then
        sql_files+=("${MIGRATIONS_DIR}/_migrations.sql")
    fi
    # Add numbered SQL files in order
    while IFS= read -r -d '' f; do
        sql_files+=("$f")
    done < <(find "${MIGRATIONS_DIR}" -maxdepth 1 -name '[0-9]*.sql' -print0 | sort -z)

    local applied=0
    local skipped=0
    local failed=0

    for sql_file in "${sql_files[@]}"; do
        local basename
        basename=$(basename "${sql_file}")

        # Extract version from filename (remove .sql extension)
        local version="${basename%.sql}"

        # Check if this migration is already applied
        if table_exists "_migrations"; then
            local already_applied
            already_applied=$(${PSQL_BASE} -d "${DB_NAME}" -t -A -c \
                "SELECT COUNT(*) FROM public._migrations WHERE version='${version}'" 2>/dev/null || echo "0")
            if [ "${already_applied}" != "0" ] 2>/dev/null; then
                skipped=$((skipped + 1))
                continue
            fi
        elif table_exists "sc_public_entities"; then
            # Fallback guard: if sc_public_entities exists and this is a numbered migration, skip
            local is_numbered
            is_numbered=$(echo "${basename}" | grep -c '^[0-9]' || true)
            if [ "${is_numbered}" != "0" ]; then
                skipped=$((skipped + 1))
                continue
            fi
        fi

        # Apply the migration
        echo "  Applying: ${basename}..."
        local output
        output=$(psql_file "${DB_NAME}" "${sql_file}" 2>&1) || {
            fail "Migration '${basename}' failed"
            echo "  Error output:"
            echo "${output}" | tail -10
            failed=$((failed + 1))
            return 1
        }

        # Register in _migrations if the migration didn't self-register
        # and the _migrations table exists
        if table_exists "_migrations"; then
            local self_registered
            self_registered=$(${PSQL_BASE} -d "${DB_NAME}" -t -A -c \
                "SELECT COUNT(*) FROM public._migrations WHERE version='${version}'" 2>/dev/null || echo "0")
            if [ "${self_registered}" = "0" ] 2>/dev/null; then
                ${PSQL_BASE} -d "${DB_NAME}" -c \
                    "INSERT INTO public._migrations (version, name, applied_at) VALUES ('${version}', '${basename}', NOW()) ON CONFLICT (version) DO NOTHING" >/dev/null 2>&1 || true
            fi
        fi

        applied=$((applied + 1))
        echo "    [OK] ${basename}"
    done

    if [ "${failed}" -gt 0 ]; then
        fail "${failed} migration(s) failed"
        return 1
    fi

    if [ "${applied}" -eq 0 ] && [ "${skipped}" -gt 0 ]; then
        ok "All ${skipped} migrations already applied (${applied} new, ${skipped} skipped)"
    else
        done_msg "${applied} migration(s) applied, ${skipped} already applied"
    fi
}

# ============================================================================
# STEP 3: load_seed — Load seed data
# ============================================================================
step_load_seed() {
    echo ""
    info "STEP 3/4: load_seed — Loading seed data..."

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] Would run: seed_sc_entities.py (if sc_public_entities has 0 rows)"
        echo "  [DRY-RUN] Would run: load_canonical_universe() (if canonical_universe has 0 rows)"
        return 0
    fi

    local seed_script="${PROJECT_ROOT}/scripts/db/seed_sc_entities.py"

    # -----------------------------------------------------------------------
    # Substeps 3a: seed_sc_entities
    # -----------------------------------------------------------------------
    if [ -f "${seed_script}" ]; then
        local sc_count
        sc_count=$(table_row_count "sc_public_entities")

        if [ "${sc_count}" = "0" ]; then
            echo "  Running seed_sc_entities.py (sc_public_entities is empty)..."
            local output
            output=$(cd "${PROJECT_ROOT}" && python scripts/db/seed_sc_entities.py 2>&1) || {
                fail "seed_sc_entities.py failed"
                echo "  Error: ${output}"
                return 1
            }
            echo "  ${output}"
            done_msg "seed_sc_entities.py completed"
        elif [ "${sc_count}" = "-1" ]; then
            skip "Table sc_public_entities does not exist — skipping seed"
        else
            ok "sc_public_entities already has ${sc_count} row(s) — skipping seed"
        fi
    else
        skip "Script scripts/db/seed_sc_entities.py not found — skipping seed"
    fi

    # -----------------------------------------------------------------------
    # Substeps 3b: load_canonical_universe (seed_file validation)
    # -----------------------------------------------------------------------
    # Check if canonical_universe table exists (or use an alternative indicator)
    local uni_count
    uni_count=$(table_row_count "canonical_universe")

    if [ "${uni_count}" = "0" ]; then
        echo "  Running load_canonical_universe() to validate canonical seed..."
        local output
        output=$(cd "${PROJECT_ROOT}" && python -c "
from scripts.lib.universe import load_canonical_universe
universe = load_canonical_universe()
print(f'Canonical universe loaded: {len(universe.entities)} total rows')
print(f'  Included (within radius): {len(universe.included)}')
print(f'  Excluded (outside radius): {len(universe.excluded)}')
print(f'  Unresolved: {len(universe.unresolved)}')
print(f'  Canonical denominator: {universe.summary()[\"conservative_monitoring_denominator\"]}')
" 2>&1) || {
            fail "load_canonical_universe() failed"
            echo "  Error: ${output}"
            return 1
        }
        echo "  ${output}"
        done_msg "Canonical universe validation completed"
    elif [ "${uni_count}" = "-1" ]; then
        skip "Table canonical_universe does not exist — skipping (in-memory validation only)"
        # Run load_canonical_universe anyway for validation since there's no DB table to skip
        echo "  Running load_canonical_universe() for validation only..."
        local output
        output=$(cd "${PROJECT_ROOT}" && python -c "
from scripts.lib.universe import load_canonical_universe
universe = load_canonical_universe()
print(f'Canonical universe validated: {len(universe.entities)} total rows')
" 2>&1) || {
            fail "load_canonical_universe() validation failed"
            echo "  Error: ${output}"
            return 1
        }
        echo "  ${output}"
        done_msg "Canonical universe validated (in-memory, no DB persist)"
    else
        ok "canonical_universe already has ${uni_count} row(s) — skipping"
    fi
}

# ============================================================================
# STEP 4: verify_fingerprint — Validate QW-01 schema fingerprint
# ============================================================================
step_verify_fingerprint() {
    echo ""
    info "STEP 4/4: verify_fingerprint — Validating QW-01 schema..."

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] Would run: validate_qw01_schema against ${DB_NAME}"
        echo "  [DRY-RUN] Would run: schema_fingerprint for reproducibility"
        return 0
    fi

    local dsn="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

    echo "  Running validate_qw01_schema..."
    local output
    output=$(cd "${PROJECT_ROOT}" && python -c "
import sys
from scripts.opportunity_intel.schema import connect_postgres, validate_qw01_schema, schema_fingerprint
conn = connect_postgres('${dsn}')
result = validate_qw01_schema(conn)
print(f'Schema backend: {result[\"backend\"]}')
print(f'PostgreSQL version: {result[\"postgres_version\"]}')
print(f'Required tables: {result[\"required_tables\"]}')
print(f'Migration 029 ready: {result[\"migration_029_ready\"]}')

fingerprint = schema_fingerprint(conn)
print(f'Schema fingerprint: {fingerprint}')
conn.close()
print('QW-01 schema validation PASSED')
sys.exit(0)
" 2>&1) || {
        fail "QW-01 schema validation FAILED"
        echo "  Error: ${output}"
        return 1
    }

    echo "  ${output}"
    done_msg "QW-01 schema fingerprint validated successfully"
}

# ============================================================================
# Main Execution
# ============================================================================
main() {
    echo ""
    echo "======================================================================"
    echo "  Extra Consultoria — Local Database Bootstrap"
    echo "  Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  Log:  ${LOG_FILE}"
    echo "======================================================================"
    echo ""

    if [ "$RESET" = true ]; then
        echo "  [--reset] Mode: forcing re-execution of all steps"
        echo ""
    fi
    if [ "$DRY_RUN" = true ]; then
        echo "  [--dry-run] Mode: showing what would be done without executing"
        echo ""
    fi

    local all_pass=true

    step_create_db      || { fail "Step 1 (create_db) failed"; all_pass=false; }
    step_run_migrations || { fail "Step 2 (run_migrations) failed"; all_pass=false; }
    step_load_seed      || { fail "Step 3 (load_seed) failed"; all_pass=false; }
    step_verify_fingerprint || { fail "Step 4 (verify_fingerprint) failed"; all_pass=false; }

    echo ""
    echo "======================================================================"
    if [ "$DRY_RUN" = true ]; then
        echo "  Bootstrap DRY-RUN completed (no changes made)"
        echo "  Log: ${LOG_FILE}"
        echo "======================================================================"
        exit 0
    fi

    if [ "$all_pass" = true ]; then
        echo -e "  ${GREEN}Bootstrap completed successfully${NC}"
        echo "  Log: ${LOG_FILE}"
        echo "======================================================================"
        exit 0
    else
        echo -e "  ${RED}Bootstrap completed with errors${NC}"
        echo "  Log: ${LOG_FILE}"
        echo "======================================================================"
        exit 1
    fi
}

main "$@"

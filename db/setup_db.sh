#!/bin/bash
# setup_db.sh — Apply all migrations with ledger tracking and seed the database
#
# Usage:
#   LOCAL_DATALAKE_DSN="postgresql://postgres:pass@host:port/db" bash db/setup_db.sh
#   bash db/setup_db.sh "postgresql://postgres:pass@host:port/db"
#
# Requirements:
#   - PostgreSQL 16 (canonical target for Ubuntu 24.04 LTS)
#   - Extensions: pg_trgm, uuid-ossp, vector (pgvector)
#   - psql client in PATH
#
# Exit codes:
#   0 — All migrations applied successfully
#   1 — Migration failure or checksum mismatch
#   2 — Configuration error (missing DSN, missing psql)

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DSN="${1:-${LOCAL_DATALAKE_DSN:?Erro: LOCAL_DATALAKE_DSN nao definida. Passe como argumento ou defina a env var.}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/migrations"
LOG_DIR="${SCRIPT_DIR}/log"
mkdir -p "$LOG_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/migration-${TIMESTAMP}.log"
ERROR_LOG="$LOG_DIR/migration-${TIMESTAMP}-errors.log"

# Advisory lock ID — prevents concurrent migration runs
LOCK_ID=75319

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
if ! command -v psql &> /dev/null; then
    echo "[FAIL] psql not found in PATH. Install postgresql-client."
    exit 2
fi

echo "================================================================" | tee "$LOG_FILE"
echo "Extra Consultoria — Migration Setup" | tee -a "$LOG_FILE"
echo "Started: $(date -Iseconds)" | tee -a "$LOG_FILE"
echo "Migrations dir: $MIGRATIONS_DIR" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "================================================================$(printf '\n')" | tee -a "$LOG_FILE"

# Test connection
if ! psql "$DSN" -c "SELECT 1" > /dev/null 2>> "$ERROR_LOG"; then
    echo "[FAIL] Cannot connect to database. Check DSN and PostgreSQL status." | tee -a "$LOG_FILE"
    echo "DSN used: ${DSN%%@*}@***" | tee -a "$LOG_FILE"
    exit 2
fi

# ---------------------------------------------------------------------------
# Acquire advisory lock
# ---------------------------------------------------------------------------
echo "[INFO] Acquiring advisory lock (id=$LOCK_ID)..." | tee -a "$LOG_FILE"
LOCK_RESULT=$(psql "$DSN" -v ON_ERROR_STOP=1 -t -c "SELECT pg_try_advisory_lock($LOCK_ID);" 2>> "$ERROR_LOG" || echo "ERROR")
if [ "$LOCK_RESULT" = "ERROR" ] || [ "$LOCK_RESULT" != " t" ]; then
    echo "[FAIL] Another migration process is already running (lock id=$LOCK_ID)." | tee -a "$LOG_FILE"
    exit 1
fi
echo "[INFO] Lock acquired." | tee -a "$LOG_FILE"

# Cleanup: release advisory lock on exit
cleanup() {
    local exit_code=$?
    echo "[INFO] Releasing advisory lock..." | tee -a "$LOG_FILE"
    psql "$DSN" -v ON_ERROR_STOP=1 -c "SELECT pg_advisory_unlock($LOCK_ID);" > /dev/null 2>> "$ERROR_LOG" || true
    echo "Finished: $(date -Iseconds) — Exit code: $exit_code" | tee -a "$LOG_FILE"
    exit $exit_code
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Ensure _migrations ledger table exists
# ---------------------------------------------------------------------------
echo "[INFO] Ensuring _migrations ledger table..." | tee -a "$LOG_FILE"
psql "$DSN" -v ON_ERROR_STOP=1 << 'SQL' >> "$LOG_FILE" 2>> "$ERROR_LOG"
CREATE TABLE IF NOT EXISTS _migrations (
    version     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status      TEXT NOT NULL DEFAULT 'applied',
    error_msg   TEXT,
    rollback_sql TEXT
);
COMMENT ON TABLE _migrations IS 'Migration ledger — tracks every applied migration with checksums';
SQL

# ---------------------------------------------------------------------------
# Collect and order migrations
# ---------------------------------------------------------------------------
echo "[INFO] Collecting migrations from $MIGRATIONS_DIR..." | tee -a "$LOG_FILE"

# Build ordered list with explicit a/b/c suffix support
# Lexicographic ordering handles: 001, 002, ..., 021a, 021b, 021c, 021d, ..., 041a, 041b
mapfile -t MIGRATIONS < <(find "$MIGRATIONS_DIR" -maxdepth 1 -name '*.sql' -type f | sort)

if [ ${#MIGRATIONS[@]} -eq 0 ]; then
    echo "[FAIL] No migration files found in $MIGRATIONS_DIR" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[INFO] Found ${#MIGRATIONS[@]} migrations" | tee -a "$LOG_FILE"
for m in "${MIGRATIONS[@]}"; do
    echo "  $(basename "$m")" >> "$LOG_FILE"
done

# Save migration order for evidence
for m in "${MIGRATIONS[@]}"; do
    basename "$m"
done > "$LOG_DIR/migration-order-${TIMESTAMP}.txt"

# ---------------------------------------------------------------------------
# Apply migrations with checksum verification
# ---------------------------------------------------------------------------
FAILED=0
APPLIED=0
SKIPPED=0

for migration in "${MIGRATIONS[@]}"; do
    name="$(basename "$migration" .sql)"
    version="${name%%_*}"  # Extract numeric prefix (e.g., "041a" from "041a_fix_fk_constraints")

    echo "[MIGRATION] $name..." | tee -a "$LOG_FILE"

    # Compute checksum (SHA-256 of normalized content)
    checksum=$(sha256sum "$migration" | awk '{print $1}')

    # Check if already applied
    existing=$(psql "$DSN" -v ON_ERROR_STOP=1 -t -c \
        "SELECT checksum FROM _migrations WHERE version = '$version';" 2>> "$ERROR_LOG" || echo "QUERY_ERROR")

    if [ "$existing" = "QUERY_ERROR" ]; then
        echo "[FAIL] Ledger query failed for $name. Aborting." | tee -a "$LOG_FILE"
        FAILED=1
        break
    fi

    if [ -n "$existing" ] && [ "$existing" != " " ]; then
        existing=$(echo "$existing" | xargs)  # trim whitespace
        if [ "$existing" = "$checksum" ]; then
            echo "[SKIP] $name already applied (checksum match)." | tee -a "$LOG_FILE"
            SKIPPED=$((SKIPPED + 1))
            continue
        else
            echo "[FAIL] $name checksum mismatch!" | tee -a "$LOG_FILE"
            echo "  Stored:  $existing" | tee -a "$LOG_FILE"
            echo "  Current: $checksum" | tee -a "$LOG_FILE"
            echo "  Migration file was modified after being applied. Manual review required." | tee -a "$LOG_FILE"
            FAILED=1
            break
        fi
    fi

    # Apply migration — stderr goes to error log, stdout suppressed
    # psql exits non-zero on SQL error thanks to ON_ERROR_STOP=1
    applied_at=$(date -Iseconds)
    if psql "$DSN" -v ON_ERROR_STOP=1 -f "$migration" >> "$LOG_FILE" 2>> "$ERROR_LOG"; then
        # Record successful application
        psql "$DSN" -v ON_ERROR_STOP=1 -c \
            "INSERT INTO _migrations (version, name, checksum, applied_at, status)
             VALUES ('$version', '$name', '$checksum', '$applied_at', 'applied')
             ON CONFLICT (version) DO UPDATE
             SET checksum = EXCLUDED.checksum,
                 applied_at = EXCLUDED.applied_at,
                 status = 'applied',
                 error_msg = NULL;" \
            >> "$LOG_FILE" 2>> "$ERROR_LOG"
        echo "[OK] $name applied." | tee -a "$LOG_FILE"
        APPLIED=$((APPLIED + 1))
    else
        echo "[FAIL] $name failed!" | tee -a "$LOG_FILE"
        echo "  Check error log: $ERROR_LOG" | tee -a "$LOG_FILE"
        echo "  Last 10 lines of error log:" | tee -a "$LOG_FILE"
        tail -10 "$ERROR_LOG" | while read -r line; do echo "    $line"; done | tee -a "$LOG_FILE"

        # Record failure — NEVER mark as applied
        psql "$DSN" -v ON_ERROR_STOP=1 -c \
            "INSERT INTO _migrations (version, name, checksum, applied_at, status, error_msg)
             VALUES ('$version', '$name', '$checksum', '$applied_at', 'failed',
                     'See error log: $ERROR_LOG')
             ON CONFLICT (version) DO UPDATE
             SET status = 'failed',
                 error_msg = EXCLUDED.error_msg;" \
            >> "$LOG_FILE" 2>> "$ERROR_LOG" || true
        FAILED=1
        break
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
echo "MIGRATION SUMMARY" | tee -a "$LOG_FILE"
echo "================================================================" | tee -a "$LOG_FILE"
echo "  Applied: $APPLIED" | tee -a "$LOG_FILE"
echo "  Skipped: $SKIPPED" | tee -a "$LOG_FILE"
echo "  Failed:  $FAILED" | tee -a "$LOG_FILE"
echo "  Total:   ${#MIGRATIONS[@]}" | tee -a "$LOG_FILE"
echo "  Log:     $LOG_FILE" | tee -a "$LOG_FILE"
echo "================================================================$(printf '\n')" | tee -a "$LOG_FILE"

if [ "$FAILED" -ne 0 ]; then
    echo "[RESULT] MIGRATION FAILED. Fix errors and re-run." | tee -a "$LOG_FILE"
    exit 1
fi

echo "[RESULT] ALL MIGRATIONS APPLIED SUCCESSFULLY." | tee -a "$LOG_FILE"

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
echo "" | tee -a "$LOG_FILE"
echo "[SEED] Seeding SC public entities..." | tee -a "$LOG_FILE"
if python3 "$SCRIPT_DIR/seed/001_sc_entities.py" --dsn "$DSN" --truncate >> "$LOG_FILE" 2>> "$ERROR_LOG"; then
    echo "[OK] Seed completed." | tee -a "$LOG_FILE"
else
    echo "[WARN] Seed script failed. Check error log. Migrations are applied but data may be incomplete." | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "Setup complete. Run diagnostics:" | tee -a "$LOG_FILE"
echo "  python scripts/schema/diagnostics.py --dsn '$DSN'" | tee -a "$LOG_FILE"
echo "  psql '$DSN' -c \"SELECT version, name, status FROM _migrations ORDER BY version;\"" | tee -a "$LOG_FILE"

exit 0

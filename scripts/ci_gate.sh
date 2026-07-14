#!/bin/bash
# ---------------------------------------------------------------------------
# CI Gate — 4-stage fail-closed pipeline with structured JSON logging.
# Exits 0 if all stages pass, 2 if any stage fails (ADR-014).
#
# Usage:
#   bash scripts/ci_gate.sh                  # Full pipeline
#   SKIP_COVERAGE=1 bash scripts/ci_gate.sh  # Skip coverage gate
#
# Output:
#   - Terminal: colored status per stage
#   - Log:      output/ci/ci-gate-<timestamp>.log
#   - JSON:     per-stage lines + final aggregated JSON
#
# Principles: fail-closed (ADR-014), structured JSON (ADR-010), KISS.
# ---------------------------------------------------------------------------
set -euo pipefail

# ---- Colors ---------------------------------------------------------------
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ---- Log setup ------------------------------------------------------------
LOG_DIR="output/ci"
LOG_FILE="$LOG_DIR/ci-gate-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$LOG_DIR"

# ---- Global state ---------------------------------------------------------
overall_status="pass"
stage_results=""
stage_count=0
LAST_STATUS=""

# ---- Stage runner ---------------------------------------------------------
# Usage: run_stage "stage_name" command [args...]
#   - Measures wall-clock duration via date +%s%3N
#   - Prints colored [PASS]/[FAIL] banner to stdout
#   - Emits JSON line: {"stage":"<name>","status":"pass|fail","duration_ms":<int>,"errors":[]}
#   - Accumulates stage into final aggregated JSON
run_stage() {
    local stage_name="$1"
    shift
    local start_ms end_ms duration_ms status errors_json exit_code

    start_ms=$(date +%s%3N)

    set +e
    "$@" 2>&1
    exit_code=$?
    set -e

    end_ms=$(date +%s%3N)
    duration_ms=$((end_ms - start_ms))

    if [ "$exit_code" -eq 0 ]; then
        status="pass"
        errors_json="[]"
        printf "%b[PASS]%b %s (%dms)\n" "$GREEN" "$NC" "$stage_name" "$duration_ms"
    else
        status="fail"
        overall_status="fail"
        errors_json="[]"
        printf "%b[FAIL]%b %s (%dms)\n" "$RED" "$NC" "$stage_name" "$duration_ms"
    fi

    LAST_STATUS="$status"

    # Emit per-stage JSON line
    printf '{"stage":"%s","status":"%s","duration_ms":%d,"errors":%s}\n' \
        "$stage_name" "$status" "$duration_ms" "$errors_json"

    # Accumulate into final aggregate
    if [ "$stage_count" -gt 0 ]; then
        stage_results="$stage_results,"
    fi
    stage_results="${stage_results}$(printf '{"stage":"%s","status":"%s","duration_ms":%d,"errors":%s}' \
        "$stage_name" "$status" "$duration_ms" "$errors_json")"
    stage_count=$((stage_count + 1))
}

# ---- Main pipeline --------------------------------------------------------
# Wrapped in { } | tee  so all output goes to terminal AND log file
{
    echo "=== CI Gate ==="
    printf "Started: %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Log: $LOG_FILE"
    echo ""

    # -----------------------------------------------------------------------
    # Stage 1 — Lint (ruff)
    # -----------------------------------------------------------------------
    run_stage "ruff" ruff check scripts/

    # -----------------------------------------------------------------------
    # Stage 2 — Type check (pyright)
    # -----------------------------------------------------------------------
    run_stage "pyright" pyright scripts/

    # -----------------------------------------------------------------------
    # Stage 3 — Security scan (bandit)
    # -----------------------------------------------------------------------
    run_stage "bandit" bandit -r scripts/ -ll

    # -----------------------------------------------------------------------
    # Stage 4 — Tests (pytest, non-slow)
    # -----------------------------------------------------------------------
    run_stage "pytest" pytest -m "not slow" --cov=scripts --cov-report=term-missing

    # -----------------------------------------------------------------------
    # Stage 5 — Coverage gate (conditional)
    # -----------------------------------------------------------------------
    if [ "${SKIP_COVERAGE:-0}" != "1" ]; then
        if [ "$LAST_STATUS" = "pass" ]; then
            run_stage "coverage_gate" python scripts/coverage_gate.py
        else
            printf "%b[SKIP]%b coverage_gate (pytest failed — coverage data unreliable)\n" "$YELLOW" "$NC"
        fi
    else
        printf "%b[SKIP]%b coverage_gate (SKIP_COVERAGE=1)\n" "$YELLOW" "$NC"
    fi

    # -----------------------------------------------------------------------
    # Final aggregated JSON
    # -----------------------------------------------------------------------
    echo ""
    final_json=$(printf '{"result":"%s","stages":[%s]}' "$overall_status" "$stage_results")
    printf "=== Result: %s ===\n" "$overall_status"
    echo "$final_json"

    if [ "$overall_status" = "fail" ]; then
        exit 2
    fi
    exit 0
} 2>&1 | tee "$LOG_FILE"

# Propagate the pipeline exit code from the { } block
exit "${PIPESTATUS[0]}"

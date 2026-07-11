#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Local CI Check — runs the same pipeline as GitHub Actions locally.
#
# Usage:
#   bash scripts/ci-check.sh              # Full pipeline
#   bash scripts/ci-check.sh --quick      # Skip security scan
#   bash scripts/ci-check.sh --lint-only  # Only lint
#
# Story TD-4.2: Setup CI/CD Pipeline
# ---------------------------------------------------------------------------
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
PASS=0
FAIL=0

log_pass() { echo -e "  ${GREEN}[PASS]${NC} $1"; ((PASS++)); }
log_fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ((FAIL++)); }
log_skip() { echo -e "  ${YELLOW}[SKIP]${NC} $1"; }

echo "=========================================="
echo " Extra Consultoria — Local CI Check"
echo " Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "=========================================="
echo ""

# ---------------------------------------------------------------------------
# 1. LINT — ruff
# ---------------------------------------------------------------------------
echo "--- Lint (ruff) ---"
if command -v ruff &>/dev/null; then
    if ruff check .; then
        log_pass "ruff check passed"
    else
        log_fail "ruff check found issues"
    fi
else
    log_skip "ruff not installed (run: pip install ruff)"
fi
echo ""

# ---------------------------------------------------------------------------
# 2. TYPE CHECK — mypy
# ---------------------------------------------------------------------------
echo "--- Type Check (mypy) ---"
if command -v mypy &>/dev/null; then
    if mypy .; then
        log_pass "mypy check passed"
    else
        log_fail "mypy found type errors"
    fi
else
    log_skip "mypy not installed (run: pip install mypy)"
fi
echo ""

# ---------------------------------------------------------------------------
# 3. TESTS — pytest with coverage
# ---------------------------------------------------------------------------
echo "--- Tests (pytest) ---"
if command -v pytest &>/dev/null; then
    if python -m pytest tests/ --cov --cov-report=term-missing -x; then
        log_pass "All tests passed"
    else
        log_fail "Tests failed"
    fi
else
    log_skip "pytest not installed (run: pip install pytest pytest-cov)"
fi
echo ""

# ---------------------------------------------------------------------------
# 4. SECURITY — bandit
# ---------------------------------------------------------------------------
if [ "${1:-}" != "--quick" ]; then
    echo "--- Security (bandit) ---"
    if command -v bandit &>/dev/null; then
        if bandit -r scripts/ -f json --quiet; then
            log_pass "bandit security scan passed"
        else
            log_fail "bandit found security issues"
        fi
    else
        log_skip "bandit not installed (run: pip install bandit)"
    fi
else
    log_skip "Security scan skipped (--quick)"
fi
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "=========================================="
echo " Results: $PASS passed, $FAIL failed"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0

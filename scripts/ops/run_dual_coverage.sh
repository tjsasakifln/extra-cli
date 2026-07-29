#!/usr/bin/env bash
# Canonical dual capability coverage measurement (VPS + local).
# Ensures PYTHONPATH and venv so module invocation never fails with
# "No module named scripts".
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
OUT="${DUAL_OUTPUT_DIR:-$ROOT/output/coverage/dual-latest}"
mkdir -p "$OUT"
exec "$PY" -m scripts.coverage.dual_capability_coverage \
  --capability both \
  --output-dir "$OUT" \
  --expected-denominator "${EXPECTED_DENOMINATOR:-1093}" \
  "$@"

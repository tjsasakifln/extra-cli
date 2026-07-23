#!/usr/bin/env bash
# Wait for local 3y backfill completion then prepare cutover package.
# Does NOT auto-restore on VPS unless --execute-cutover is passed.
# Single-writer: stops local pilot before final export when cutting over.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
CKPT="${CKPT:-data/contracts_checkpoints/hc_closure_3y/contracts_full.json}"
PLANNED="${PLANNED:-37}"
EXECUTE=0
for a in "$@"; do
  [[ "$a" == "--execute-cutover" ]] && EXECUTE=1
done

while true; do
  python3 - <<PY
import json, sys
from pathlib import Path
p = Path("$CKPT")
if not p.is_file():
    print("no_checkpoint")
    sys.exit(2)
d = json.loads(p.read_text())
n = len(d.get("completed_windows") or [])
print(f"completed={n}/{int('$PLANNED')} current={d.get('current_window_start')} updated={d.get('updated_at')}")
sys.exit(0 if n >= int("$PLANNED") else 1)
PY
  st=$?
  if [[ $st -eq 0 ]]; then
    echo "[INFO] backfill windows complete"
    break
  fi
  sleep 180
done

export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"

if [[ "$EXECUTE" -eq 1 ]]; then
  echo "[INFO] stopping local pilot (single writer cutover)"
  pkill -f 'run_contracts_90d_pilot' || true
  sleep 5
  bash scripts/ops/export_backfill_for_vps.sh --upload
  echo "[INFO] on VPS run restore_backfill_on_vps.sh for latest pkg"
else
  echo "[INFO] windows complete — re-run with --execute-cutover to stop pilot + export+upload"
fi

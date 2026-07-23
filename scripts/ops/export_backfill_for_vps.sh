#!/usr/bin/env bash
# export_backfill_for_vps.sh — Export local historical-contracts backfill for VPS restore
#
# Safe to run while crawl is active (snapshot of current table state).
# For FINAL cutover: stop local pilot first, re-run this script, then restore.
#
# Usage:
#   export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
#   bash scripts/ops/export_backfill_for_vps.sh
#   bash scripts/ops/export_backfill_for_vps.sh --upload   # scp package to ec-prod
#
# Env:
#   LOCAL_DATALAKE_DSN   (required)
#   EXPORT_DIR           default: artifacts/migration/backfill-vps
#   VPS_HOST             default: ec-prod  (ssh config)
#   VPS_INCOMING         default: /var/lib/extra-consultoria/incoming
#
# Fail-closed: missing DSN, failed dump, empty SHA256SUMS → non-zero exit.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DSN="${LOCAL_DATALAKE_DSN:-}"
if [[ -z "$DSN" ]]; then
  echo "ERROR: LOCAL_DATALAKE_DSN is required" >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EXPORT_DIR="${EXPORT_DIR:-$ROOT/artifacts/migration/backfill-vps}"
PKG_DIR="$EXPORT_DIR/pkg-$STAMP"
VPS_HOST="${VPS_HOST:-ec-prod}"
VPS_INCOMING="${VPS_INCOMING:-/var/lib/extra-consultoria/incoming}"
UPLOAD=0
for arg in "$@"; do
  case "$arg" in
    --upload) UPLOAD=1 ;;
    --help|-h)
      sed -n '2,25p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$PKG_DIR"/{db,checkpoints,meta}
echo "[INFO] package: $PKG_DIR"

# ── meta ────────────────────────────────────────────────────────────────────
{
  echo "exported_at_utc=$STAMP"
  echo "source_dsn_host=$(LOCAL_DATALAKE_DSN="$DSN" python3 - <<'PY'
import os, urllib.parse
u=urllib.parse.urlparse(os.environ['LOCAL_DATALAKE_DSN'])
print(u.hostname or '', u.port or '')
PY
)"
  echo "hostname=$(hostname)"
  echo "git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "git_commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  psql "$DSN" -Atc "SELECT 'pg_version='||version();" | head -1
  CONTRACTS_COUNT="$(psql "$DSN" -Atc "SELECT count(*) FROM pncp_supplier_contracts;")"
  echo "contracts_count=${CONTRACTS_COUNT}"
  if [[ -z "${CONTRACTS_COUNT}" || "${CONTRACTS_COUNT}" == "0" ]]; then
    echo "ERROR: contracts_count is empty or zero — refusing empty export" >&2
    exit 1
  fi
  psql "$DSN" -Atc "SELECT 'contracts_size='||pg_size_pretty(pg_total_relation_size('pncp_supplier_contracts'));"
  if [[ -f data/contracts_checkpoints/hc_closure_3y/contracts_full.json ]]; then
    python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('data/contracts_checkpoints/hc_closure_3y/contracts_full.json').read_text())
print('checkpoint_completed_windows='+str(len(d.get('completed_windows',[]))))
print('checkpoint_current='+str(d.get('current_window_start')))
print('checkpoint_fetched='+str(d.get('total_contracts_fetched')))
print('checkpoint_failed_windows='+str(d.get('total_windows_failed')))
PY
  fi
  if pgrep -af 'run_contracts_90d_pilot' >/dev/null 2>&1; then
    pgrep -af 'run_contracts_90d_pilot' || true
    echo 'local_pilot=running'
  else
    echo 'local_pilot=not_running'
  fi
} | tee "$PKG_DIR/meta/export-manifest.txt"

# ── checkpoints + campaign artifacts (small) ────────────────────────────────
if [[ -d data/contracts_checkpoints/hc_closure_3y ]]; then
  cp -a data/contracts_checkpoints/hc_closure_3y "$PKG_DIR/checkpoints/"
fi
if [[ -d artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill ]]; then
  mkdir -p "$PKG_DIR/meta/campaign-backfill"
  find artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/backfill \
    -maxdepth 1 \( -name '*.json' -o -name '*.pid' -o -name 'STATUS*' \) \
    -exec cp -a {} "$PKG_DIR/meta/campaign-backfill/" \;
fi

# ── table dumps (custom format, compressed) ─────────────────────────────────
TABLES=(
  pncp_supplier_contracts
  pncp_backfill_runs
  pncp_backfill_pages
  pncp_backfill_records
  pipeline_watermarks
  pipeline_runs
)

DUMPED=0
for t in "${TABLES[@]}"; do
  exists=$(psql "$DSN" -Atc "SELECT to_regclass('public.$t') IS NOT NULL;")
  if [[ "$exists" != "t" ]]; then
    echo "[WARN] skip missing table: $t"
    continue
  fi
  out="$PKG_DIR/db/${t}.dump"
  echo "[INFO] pg_dump -t $t -> $out"
  pg_dump "$DSN" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-acl \
    --table="public.$t" \
    --file="$out"
  if [[ ! -s "$out" ]]; then
    echo "ERROR: dump empty or missing for $t" >&2
    exit 1
  fi
  ls -lh "$out"
  DUMPED=$((DUMPED + 1))
done

if [[ "$DUMPED" -lt 1 ]]; then
  echo "ERROR: no tables dumped" >&2
  exit 1
fi
if [[ ! -s "$PKG_DIR/db/pncp_supplier_contracts.dump" ]]; then
  echo "ERROR: pncp_supplier_contracts.dump required" >&2
  exit 1
fi

# ── checksums (mandatory) ───────────────────────────────────────────────────
( cd "$PKG_DIR" && find . -type f ! -path './meta/SHA256SUMS' -print0 | sort -z | xargs -0 sha256sum ) \
  > "$PKG_DIR/meta/SHA256SUMS"
if [[ ! -s "$PKG_DIR/meta/SHA256SUMS" ]]; then
  echo "ERROR: SHA256SUMS empty" >&2
  exit 1
fi
# self-verify immediately
(
  cd "$PKG_DIR"
  sha256sum -c meta/SHA256SUMS
)
echo "[INFO] wrote and verified SHA256SUMS"

# machine-readable gate summary (no secrets)
python3 - <<PY
import json
from pathlib import Path
pkg = Path("$PKG_DIR")
manifest = (pkg / "meta/export-manifest.txt").read_text(encoding="utf-8", errors="replace")
counts = {}
for line in manifest.splitlines():
    if "=" in line:
        k, _, v = line.partition("=")
        counts[k.strip()] = v.strip()
payload = {
    "package": str(pkg),
    "exported_at_utc": "$STAMP",
    "contracts_count": int(counts.get("contracts_count") or 0),
    "sha256sums": str(pkg / "meta/SHA256SUMS"),
    "status": "ok",
}
(pkg / "meta/export-result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY

if [[ "$UPLOAD" -eq 1 ]]; then
  echo "[INFO] upload to $VPS_HOST:$VPS_INCOMING/"
  ssh "$VPS_HOST" "mkdir -p '$VPS_INCOMING' && chown extra-consultoria:extra-consultoria '$VPS_INCOMING'"
  if command -v rsync >/dev/null; then
    rsync -avP --info=progress2 -e "ssh" "$PKG_DIR" "$VPS_HOST:$VPS_INCOMING/"
  else
    scp -r "$PKG_DIR" "$VPS_HOST:$VPS_INCOMING/"
  fi
  echo "[INFO] uploaded. On VPS run:"
  echo "  sudo bash /opt/extra-consultoria/scripts/ops/restore_backfill_on_vps.sh $VPS_INCOMING/$(basename "$PKG_DIR")"
fi

echo
echo "DONE package=$PKG_DIR"
echo "Next: bash scripts/ops/export_backfill_for_vps.sh --upload"
echo "Or: rsync -avP $PKG_DIR ec-prod:$VPS_INCOMING/"

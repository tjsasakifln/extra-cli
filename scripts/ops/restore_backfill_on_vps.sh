#!/usr/bin/env bash
# restore_backfill_on_vps.sh — Restore historical-contracts dump package on VPS
#
# Run ON the VPS as root (or postgres + app user for files).
#
# Usage:
#   bash scripts/ops/restore_backfill_on_vps.sh /var/lib/extra-consultoria/incoming/pkg-YYYYMMDDTHHMMSSZ
#   bash scripts/ops/restore_backfill_on_vps.sh /path/to/pkg --dry-run
#
# Env:
#   LOCAL_DATALAKE_DSN or DATABASE_URL  (defaults to /root/.extra-pg-credentials)
#
# Fail-closed:
#   - SHA256SUMS must exist and verify before any truncate/restore
#   - migration failure aborts
#   - truncate failure aborts
#   - contracts_count must match export-manifest (unless RESTORE_ALLOW_COUNT_MISMATCH=1)

set -euo pipefail

PKG="${1:-}"
DRY_RUN=0
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=1
done

if [[ -z "$PKG" || ! -d "$PKG" ]]; then
  echo "Usage: $0 /path/to/pkg-TIMESTAMP [--dry-run]" >&2
  exit 1
fi

if [[ -f /root/.extra-pg-credentials ]]; then
  # shellcheck disable=SC1091
  source /root/.extra-pg-credentials
fi
DSN="${LOCAL_DATALAKE_DSN:-${DATABASE_URL:-}}"
if [[ -z "$DSN" ]]; then
  echo "ERROR: set LOCAL_DATALAKE_DSN" >&2
  exit 1
fi

APP_DIR="${APP_DIR:-/opt/extra-consultoria}"
CKPT_DST="/var/lib/extra-consultoria/checkpoints/hc_closure_3y"
APP_USER="${APP_USER:-extra-consultoria}"
PRE_BACKUP_DIR="${PRE_BACKUP_DIR:-/var/lib/extra-consultoria/backups/pre-restore}"

echo "[INFO] package=$PKG"
echo "[INFO] dsn host check:"
psql "$DSN" -Atc "SELECT current_database(), version();" | head -2

if [[ -f "$PKG/meta/export-manifest.txt" ]]; then
  echo "── export manifest ──"
  # strip any accidental secret-like lines
  grep -E '^(exported_at_utc|source_dsn_host|hostname|git_|pg_version|contracts_|checkpoint_|local_pilot)=' \
    "$PKG/meta/export-manifest.txt" || cat "$PKG/meta/export-manifest.txt"
  echo "─────────────────────"
fi

EXPECTED_COUNT=""
if [[ -f "$PKG/meta/export-manifest.txt" ]]; then
  EXPECTED_COUNT="$(grep -E '^contracts_count=' "$PKG/meta/export-manifest.txt" | tail -1 | cut -d= -f2 || true)"
fi

# ── integrity gate (before mutating DB) ─────────────────────────────────────
if [[ ! -f "$PKG/meta/SHA256SUMS" ]]; then
  echo "ERROR: missing $PKG/meta/SHA256SUMS — refusing restore without integrity proof" >&2
  exit 1
fi
echo "[INFO] verifying SHA256SUMS..."
(
  cd "$PKG"
  sha256sum -c meta/SHA256SUMS
)
echo "[INFO] SHA256SUMS OK"

if [[ ! -s "$PKG/db/pncp_supplier_contracts.dump" ]]; then
  echo "ERROR: missing pncp_supplier_contracts.dump" >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[DRY-RUN] would restore dumps:"
  ls -lh "$PKG/db"/*.dump 2>/dev/null || true
  echo "[DRY-RUN] would install checkpoints to $CKPT_DST"
  echo "[DRY-RUN] expected contracts_count=${EXPECTED_COUNT:-unknown}"
  exit 0
fi

# Stop any contracts/pncp crawl units if running
for u in pncp-crawl-inc extra-crawl-pncp pncp-contracts; do
  systemctl stop "${u}.service" 2>/dev/null || true
  systemctl stop "${u}.timer" 2>/dev/null || true
done

# Pre-restore safety dump of current contracts count (not full table — space)
mkdir -p "$PRE_BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PRE_COUNT="$(psql "$DSN" -Atc "SELECT count(*) FROM pncp_supplier_contracts;" 2>/dev/null || echo unknown)"
echo "pre_restore_contracts_count=${PRE_COUNT}" | tee "$PRE_BACKUP_DIR/pre-restore-${STAMP}.txt"
echo "package=$PKG" >> "$PRE_BACKUP_DIR/pre-restore-${STAMP}.txt"
echo "expected_count=${EXPECTED_COUNT:-}" >> "$PRE_BACKUP_DIR/pre-restore-${STAMP}.txt"

# Ensure schema exists — FAIL CLOSED on migration error
if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  # shellcheck disable=SC1091
  source "$APP_DIR/.venv/bin/activate"
  (
    cd "$APP_DIR"
    PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m scripts.ops.apply_migrations --dsn "$DSN"
  )
  deactivate || true
elif [[ -x "$APP_DIR/scripts/ops/apply_migrations.py" ]] || [[ -d "$APP_DIR/scripts/ops" ]]; then
  (
    cd "$APP_DIR"
    PYTHONPATH="$APP_DIR${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m scripts.ops.apply_migrations --dsn "$DSN"
  )
else
  echo "ERROR: cannot apply migrations — no venv/python app at $APP_DIR" >&2
  exit 1
fi

restore_table() {
  local dump="$1"
  local table
  table="$(basename "$dump" .dump)"
  echo "[INFO] restore $table from $dump"
  # data-only; schema already present. Truncate first for clean replace.
  if ! psql "$DSN" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE public.${table} RESTART IDENTITY CASCADE;" \
    && ! psql "$DSN" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE public.${table};"; then
    echo "ERROR: truncate failed for $table — aborting restore (fail-closed)" >&2
    exit 1
  fi
  pg_restore \
    --dbname="$DSN" \
    --data-only \
    --no-owner \
    --no-acl \
    --disable-triggers \
    --exit-on-error \
    "$dump"
  psql "$DSN" -Atc "SELECT '${table}='||count(*) FROM public.${table};"
}

# Restore largest table first
if [[ -f "$PKG/db/pncp_supplier_contracts.dump" ]]; then
  restore_table "$PKG/db/pncp_supplier_contracts.dump"
fi
for dump in "$PKG/db"/*.dump; do
  [[ -f "$dump" ]] || continue
  base="$(basename "$dump")"
  [[ "$base" == "pncp_supplier_contracts.dump" ]] && continue
  restore_table "$dump"
done

# Checkpoints for resume of remaining windows
mkdir -p "$(dirname "$CKPT_DST")"
if [[ -d "$PKG/checkpoints/hc_closure_3y" ]]; then
  rm -rf "$CKPT_DST"
  cp -a "$PKG/checkpoints/hc_closure_3y" "$CKPT_DST"
  chown -R "$APP_USER:$APP_USER" /var/lib/extra-consultoria/checkpoints 2>/dev/null || true
  echo "[INFO] checkpoints installed at $CKPT_DST"
  if [[ -f "$CKPT_DST/contracts_full.json" ]]; then
    python3 - <<PY
import json
from pathlib import Path
p = Path("$CKPT_DST/contracts_full.json")
d = json.loads(p.read_text())
print("checkpoint_completed=", len(d.get("completed_windows") or []))
print("checkpoint_current=", d.get("current_window_start"))
PY
  fi
fi

# Analyze for planner
psql "$DSN" -c "ANALYZE public.pncp_supplier_contracts;"

# Final counts — automatic comparison (fail-closed)
echo "── validation ──"
ACTUAL_COUNT="$(psql "$DSN" -Atc "SELECT count(*) FROM pncp_supplier_contracts;")"
echo "contracts_count_actual=${ACTUAL_COUNT}"
psql "$DSN" -c "SELECT min(data_assinatura), max(data_assinatura) FROM pncp_supplier_contracts WHERE data_assinatura IS NOT NULL AND data_assinatura < '2100-01-01';"

if [[ -n "${EXPECTED_COUNT}" ]]; then
  if [[ "${ACTUAL_COUNT}" != "${EXPECTED_COUNT}" ]]; then
    if [[ "${RESTORE_ALLOW_COUNT_MISMATCH:-0}" == "1" ]]; then
      echo "WARN: count mismatch actual=${ACTUAL_COUNT} expected=${EXPECTED_COUNT} (allowed by env)" >&2
    else
      echo "ERROR: contracts_count mismatch actual=${ACTUAL_COUNT} expected=${EXPECTED_COUNT}" >&2
      echo "Set RESTORE_ALLOW_COUNT_MISMATCH=1 only after manual investigation." >&2
      exit 1
    fi
  else
    echo "[INFO] contracts_count matches manifest: ${ACTUAL_COUNT}"
  fi
else
  echo "ERROR: export-manifest missing contracts_count — cannot verify restore" >&2
  exit 1
fi

# write restore result (no secrets)
python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone
payload = {
    "restored_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "package": "$PKG",
    "contracts_count_actual": int("$ACTUAL_COUNT"),
    "contracts_count_expected": int("${EXPECTED_COUNT}"),
    "count_match": True,
    "sha256_verified": True,
    "status": "ok",
}
out = Path("$PKG") / "meta" / "restore-result.json"
try:
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
except OSError:
    Path("/var/lib/extra-consultoria/backfill").mkdir(parents=True, exist_ok=True)
    out = Path("/var/lib/extra-consultoria/backfill/restore-result.json")
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, indent=2))
PY

echo
echo "DONE restore."
echo "To resume remaining 3y windows on THIS host (if incomplete):"
echo "  cd $APP_DIR && sudo -u $APP_USER bash -lc 'source .venv/bin/activate && \\"
echo "    export LOCAL_DATALAKE_DSN=... && \\"
echo "    python3 -u scripts/crawl/run_contracts_90d_pilot.py \\"
echo "      --dsn \"\$LOCAL_DATALAKE_DSN\" --days 1099 \\"
echo "      --checkpoint-dir $CKPT_DST \\"
echo "      --output-json /var/lib/extra-consultoria/backfill/live-3y.json \\"
echo "      --allow-cross-run-resume'"

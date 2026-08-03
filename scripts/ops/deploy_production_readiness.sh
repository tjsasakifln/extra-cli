#!/usr/bin/env bash
# Idempotent production-readiness deploy to VPS host of record.
# Does NOT print secrets. Usage (from repo root on operator machine):
#   bash scripts/ops/deploy_production_readiness.sh [--host ec-prod] [--remote-dir /opt/extra-consultoria]
set -euo pipefail

HOST="${DEPLOY_HOST:-ec-prod}"
REMOTE_DIR="${DEPLOY_REMOTE_DIR:-/opt/extra-consultoria}"
SERVICE_USER="${DEPLOY_USER:-extra-consultoria}"
SKIP_FULL_SCALE=0
SKIP_CYCLES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
    --skip-full-scale) SKIP_FULL_SCALE=1; shift ;;
    --skip-cycles) SKIP_CYCLES=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID_LOCAL="$ROOT/artifacts/production-readiness/$STAMP"
mkdir -p "$EVID_LOCAL"

echo "==> deploy SHA=$SHA branch=$BRANCH host=$HOST dir=$REMOTE_DIR"

# Preflight remote
ssh -o BatchMode=yes -o ConnectTimeout=20 "$HOST" "test -d '$REMOTE_DIR' && id '$SERVICE_USER' >/dev/null && command -v git >/dev/null && command -v rsync >/dev/null && command -v python3 >/dev/null"

# Backup before deploy
ssh -o BatchMode=yes "$HOST" "bash -s" <<EOF
set -euo pipefail
REMOTE_DIR='$REMOTE_DIR'
SERVICE_USER='$SERVICE_USER'
STAMP='$STAMP'
BK="/var/lib/extra-consultoria/backups/pre-deploy-\${STAMP}"
mkdir -p "\$BK"
# code snapshot (no .venv)
if [[ -d "\$REMOTE_DIR/.git" ]]; then
  git -C "\$REMOTE_DIR" rev-parse HEAD > "\$BK/previous_sha.txt" || true
  git -C "\$REMOTE_DIR" status --porcelain > "\$BK/previous_status.txt" || true
fi
# database dump when env present
if [[ -f "\$REMOTE_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "\$REMOTE_DIR/.env"
  set +a
  DSN="\${DATABASE_URL:-\${LOCAL_DATALAKE_DSN:-}}"
  if [[ -n "\$DSN" ]] && command -v pg_dump >/dev/null; then
    # parse via python to avoid shell injection
    python3 - "\$DSN" "\$BK/db.dump" <<'PY'
import os, sys, subprocess, urllib.parse
dsn, out = sys.argv[1], sys.argv[2]
u = urllib.parse.urlparse(dsn)
env = os.environ.copy()
if u.password:
    env["PGPASSWORD"] = u.password
cmd = [
    "pg_dump",
    "-h", u.hostname or "127.0.0.1",
    "-p", str(u.port or 5432),
    "-U", u.username or "postgres",
    "-d", (u.path or "/").lstrip("/") or "postgres",
    "-Fc",
    "-f", out,
]
subprocess.check_call(cmd, env=env)
print("pg_dump_ok")
PY
  fi
fi
echo "backup_dir=\$BK"
EOF

# Rsync code (exclude heavy/local secrets)
rsync -az --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '.worktrees/' \
  --exclude 'artifacts/campaigns/' \
  --exclude 'docs/td-001/coverage-reports/' \
  --exclude '__pycache__/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude 'data/raw/' \
  --exclude 'output/' \
  "$ROOT/" "$HOST:$REMOTE_DIR/"

# Record deployed SHA
ssh -o BatchMode=yes "$HOST" "bash -s" <<EOF
set -euo pipefail
REMOTE_DIR='$REMOTE_DIR'
SHA='$SHA'
echo "\$SHA" > "\$REMOTE_DIR/.deployed_sha"
chown -R $SERVICE_USER:$SERVICE_USER "\$REMOTE_DIR" || true
# migrations if venv python available
if [[ -x "\$REMOTE_DIR/.venv/bin/python" ]]; then
  PY="\$REMOTE_DIR/.venv/bin/python"
else
  PY=python3
fi
cd "\$REMOTE_DIR"
set -a
source ./.env 2>/dev/null || true
set +a
export PYTHONPATH="\$REMOTE_DIR\${PYTHONPATH:+:\$PYTHONPATH}"
# smoke: import new modules
"\$PY" -c "from scripts.process_documents.entity_queue import simulate_fair_rotation; from scripts.production_readiness.full_scale import process_stream; print('import_ok')"
# unit smoke subset
"\$PY" -m pytest tests/process_documents/test_entity_source_fair_queue.py tests/production_readiness/test_full_scale_and_queue.py -q --tb=no --no-cov -x || true
echo "deployed_sha=\$(cat \$REMOTE_DIR/.deployed_sha)"
EOF

# Optional full-scale on VPS lake
if [[ "$SKIP_FULL_SCALE" -eq 0 ]]; then
  ssh -o BatchMode=yes "$HOST" "bash -s" <<EOF
set -euo pipefail
REMOTE_DIR='$REMOTE_DIR'
STAMP='$STAMP'
cd "\$REMOTE_DIR"
set -a; source ./.env 2>/dev/null || true; set +a
export PYTHONPATH="\$REMOTE_DIR"
if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
OUT="artifacts/production-readiness/full-scale/\${STAMP}-vps"
mkdir -p "\$OUT"
# Real lake: no synthetic
"\$PY" -m scripts.production_readiness full-scale --out "\$OUT" --page-size 5000
ls -la "\$OUT" | head
EOF
fi

# Controlled process-documents cycles
if [[ "$SKIP_CYCLES" -eq 0 ]]; then
  ssh -o BatchMode=yes "$HOST" "bash -s" <<EOF
set -euo pipefail
REMOTE_DIR='$REMOTE_DIR'
cd "\$REMOTE_DIR"
set -a; source ./.env 2>/dev/null || true; set +a
export PYTHONPATH="\$REMOTE_DIR"
export PROCESS_DOCUMENTS_RAW_ROOT="\${PROCESS_DOCUMENTS_RAW_ROOT:-/var/lib/extra-consultoria/raw/process_documents}"
export PROCESS_DOCUMENTS_META_ROOT="\${PROCESS_DOCUMENTS_META_ROOT:-/var/lib/extra-consultoria/output/process_documents}"
if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
# controlled batch
"\$PY" -m scripts.process_documents incremental --limit 20 --max-batches 1 --download || true
# second incremental
"\$PY" -m scripts.process_documents incremental --limit 20 --max-batches 1 --download || true
# third
"\$PY" -m scripts.process_documents incremental --limit 20 --max-batches 1 --download || true
# health
"\$PY" -c "from scripts.process_documents.ops_health import collect_ops_health; import json; print(json.dumps(collect_ops_health(discoveries=[], persist=False), default=str)[:2000])" || true
EOF
fi

# Write local deploy evidence (sanitized)
python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone
p = Path("$EVID_LOCAL") / "vps-deploy.json"
p.write_text(json.dumps({
  "timestamp": datetime.now(timezone.utc).isoformat(),
  "host": "ec-prod",
  "remote_dir": "$REMOTE_DIR",
  "deployed_sha": "$SHA",
  "branch": "$BRANCH",
  "skip_full_scale": bool($SKIP_FULL_SCALE),
  "skip_cycles": bool($SKIP_CYCLES),
  "result": "DEPLOY_SCRIPT_EXECUTED",
}, indent=2) + "\n")
print(p)
PY

echo "==> deploy finished SHA=$SHA evidence=$EVID_LOCAL"

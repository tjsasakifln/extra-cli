#!/usr/bin/env bash
# Roll back to the previously recorded digest pair, or stop the stack.
# Usage:
#   deploy/searxng/rollback.sh            # restore PINNED.prev.env if present
#   deploy/searxng/rollback.sh stop       # compose down
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

cmd="${1:-restore}"
if [[ "$cmd" == "stop" ]]; then
  docker compose --env-file .env down
  echo "stopped confenge-searxng"
  exit 0
fi

if [[ ! -f PINNED.prev.env ]]; then
  echo "no PINNED.prev.env; refusing to guess a previous digest" >&2
  echo "to stop: $0 stop" >&2
  exit 1
fi
cp PINNED.env "PINNED.rollback-$(date -u +%Y%m%dT%H%M%SZ).env"
cp PINNED.prev.env PINNED.env
exec "$ROOT/launch.sh"

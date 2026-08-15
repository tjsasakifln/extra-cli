#!/usr/bin/env bash
# Deploy entry point for the CONFENGE private SearXNG instance.
# Usage: deploy/searxng/launch.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f PINNED.env ]]; then
  echo "missing PINNED.env with image digests" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$ROOT/PINNED.env"

if [[ ! -f .env ]]; then
  if [[ ! -f .env.example ]]; then
    echo "missing .env.example" >&2
    exit 1
  fi
  cp .env.example .env
  if command -v openssl >/dev/null 2>&1; then
    secret="$(openssl rand -hex 32)"
    if grep -q '^SEARXNG_SECRET=' .env; then
      tmp="$(mktemp)"
      sed "s|^SEARXNG_SECRET=.*|SEARXNG_SECRET=${secret}|" .env >"$tmp"
      mv "$tmp" .env
    else
      echo "SEARXNG_SECRET=${secret}" >>.env
    fi
  fi
  echo "wrote $ROOT/.env (not committed)"
fi

if grep -q 'replace-with-openssl-rand-hex-32' .env; then
  echo "SEARXNG_SECRET still has the example placeholder" >&2
  exit 1
fi

export SEARXNG_IMAGE VALKEY_IMAGE
# shellcheck disable=SC1091
set -a
source "$ROOT/.env"
set +a

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not available" >&2
  exit 2
fi

echo "launching pinned SearXNG ${SEARXNG_IMAGE}"
echo "launching pinned Valkey ${VALKEY_IMAGE}"
docker compose --env-file .env up -d --remove-orphans

host="${SEARXNG_BIND_HOST:-127.0.0.1}"
port="${SEARXNG_HOST_PORT:-18888}"
base="http://${host}:${port}"
query="${SEARXNG_HEALTH_QUERY:-CONFENGE healthcheck empresa engenharia}"

echo "waiting for health at ${base}"
ok=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 5 "${base}/healthz" >/dev/null 2>&1 \
    || curl -fsS --max-time 5 "${base}/" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [[ "$ok" -ne 1 ]]; then
  echo "instance failed health check" >&2
  docker compose ps >&2 || true
  docker compose logs --tail 80 >&2 || true
  exit 3
fi

probe="${base}/search?q=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$query")&format=json"
echo "probing JSON search ${probe}"
body="$(mktemp)"
status="$(curl -sS --max-time 20 -o "$body" -w '%{http_code}' "$probe" || true)"
if [[ "$status" != "200" ]]; then
  echo "JSON search returned HTTP ${status}" >&2
  head -c 400 "$body" >&2 || true
  rm -f "$body"
  exit 4
fi
python3 - "$body" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
    raise SystemExit("JSON search did not return an object with a results array")
print(f"json_ok results={len(payload['results'])}")
PY
rm -f "$body"
echo "CONFENGE SearXNG ready at ${base}"

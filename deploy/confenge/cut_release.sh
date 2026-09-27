#!/usr/bin/env bash
# Materialise an immutable extra-cli release on the host and pin the CONFENGE
# outbound chain to it.
#
# Releases used to be cut by hand, which is how three different SHAs ended up
# running in one chain. This script is the versioned replacement:
#
#   * the tree comes from `git archive` at the exact SHA, so the live working
#     checkout at /opt/extra-consultoria is never touched and no local
#     modification can leak into a release;
#   * the interpreter is copied from the release currently in use, so a deploy
#     never depends on the network to rebuild an environment, and the copy is
#     rejected if requirements.txt changed;
#   * publication is an atomic rename of a fully-built staging directory;
#   * schema migrations from the staged release complete before a unit can be
#     pinned to that release; a migration failure therefore leaves the current
#     running code and timer schedule untouched;
#   * the chain is pinned and verified through deploy/confenge/pin_release.py.
#
# Usage (as root on the host):
#   cut_release.sh <full-40-char-sha> [--preserve-timer-state]
set -euo pipefail

CUT_RELEASE_LOCK="${EXTRA_CUT_RELEASE_LOCK:-/run/lock/extra-cut-release.lock}"
exec 9>"$CUT_RELEASE_LOCK"
if ! flock --nonblock 9; then
  echo "CUT_RELEASE_ERROR: another release cut owns $CUT_RELEASE_LOCK" >&2
  exit 75
fi

SHA="${1:?full 40-character release SHA required}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "CUT_RELEASE_ERROR: not a full SHA: $SHA" >&2; exit 1; }
PIN_ARGS=("$SHA")
PRESERVE_TIMER_STATE=0
if [ "${2:-}" = "--preserve-timer-state" ] && [ "$#" -eq 2 ]; then
  PIN_ARGS+=("--preserve-timer-state")
  PRESERVE_TIMER_STATE=1
elif [ "$#" -ne 1 ]; then
  echo "CUT_RELEASE_ERROR: usage: cut_release.sh <full-40-char-sha> [--preserve-timer-state]" >&2
  exit 1
fi

APP=/opt/extra-consultoria
RELEASES=/opt/extra-consultoria-releases
TARGET="$RELEASES/$SHA"
STAGING="$RELEASES/.staging-$SHA.$$"

if [ -d "$TARGET" ]; then
  echo "CUT_RELEASE_SKIP: $SHA is already materialised"
else
  git -C "$APP" fetch --quiet origin
  git -C "$APP" cat-file -e "$SHA^{commit}" 2>/dev/null || {
    echo "CUT_RELEASE_ERROR: $SHA is not an object in $APP" >&2; exit 1; }

  # The previous release supplies the interpreter. Refuse the copy if the
  # dependency set moved: a stale venv is a silently wrong deploy.
  [ -d "$RELEASES" ] || { echo "CUT_RELEASE_ERROR: release root is missing: $RELEASES" >&2; exit 1; }
  PREV="$(
    find "$RELEASES" -regextype posix-extended -mindepth 1 -maxdepth 1 -type d \
      -regex "$RELEASES/[0-9a-f]{40}" -printf '%T@ %p\n' \
      | sort -nr | sed -n '1{s/^[^ ]* //;p;}'
  )"
  [ -x "$PREV/.venv/bin/python" ] || { echo "CUT_RELEASE_ERROR: no usable previous venv" >&2; exit 1; }
  PREV_SHA="$(basename "$PREV")"
  if ! git -C "$APP" diff --quiet "$PREV_SHA" "$SHA" -- requirements.txt 2>/dev/null; then
    echo "CUT_RELEASE_ERROR: requirements.txt changed between $PREV_SHA and $SHA; rebuild the venv explicitly" >&2
    exit 1
  fi

  trap 'rm -rf "$STAGING"' EXIT
  mkdir -p "$STAGING"
  git -C "$APP" archive "$SHA" | tar -x -C "$STAGING"
  cp -a "$PREV/.venv" "$STAGING/.venv"
  # The venv records an absolute path; keep it pointing at a real interpreter.
  PYTHONDONTWRITEBYTECODE=1 "$STAGING/.venv/bin/python" -P -c "import sys; sys.exit(0)" || {
    echo "CUT_RELEASE_ERROR: copied interpreter does not run" >&2; exit 1; }
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$STAGING" "$STAGING/.venv/bin/python" -P -c "
import scripts.ops.confenge_feed_cycle as m
import scripts.confenge_activation.publish as p
import scripts.decision_unit_intelligence.batch_population as b
assert hasattr(b, '_population_freshness'), 'release predates the population freshness fix'
assert hasattr(p, 'producer_identity'), 'release predates the producer identity fix'
print('CUT_RELEASE_IMPORT_OK')
" || { echo "CUT_RELEASE_ERROR: staged release failed its import check" >&2; exit 1; }

  chown -R root:root "$STAGING"
  chmod -R a-w "$STAGING"
  mv -T "$STAGING" "$TARGET"
  trap - EXIT
  echo "CUT_RELEASE_PUBLISHED: $TARGET"
fi

# Existing targets are never trusted merely because their directory name is a
# SHA. Refuse writable or non-root-owned material and re-bind the critical
# release/publisher files to the exact Git objects before pinning systemd.
if find "$TARGET" -xdev \( -type f -o -type d \) -perm /222 -print -quit | grep -q .; then
  echo "CUT_RELEASE_ERROR: release is writable: $TARGET" >&2
  exit 1
fi
if find "$TARGET" -xdev \( ! -user root -o ! -group root \) -print -quit | grep -q .; then
  echo "CUT_RELEASE_ERROR: release is not root-owned: $TARGET" >&2
  exit 1
fi
for CRITICAL_PATH in \
  deploy/confenge/cut_release.sh \
  deploy/confenge/pin_release.py \
  scripts/ops/apply_migrations.py \
  scripts/confenge_activation/publish.py \
  scripts/decision_unit_intelligence/batch_population.py \
  scripts/ops/confenge_feed_cycle.py \
  scripts/warmbly_bridge/export.py
do
  [ -f "$TARGET/$CRITICAL_PATH" ] || {
    echo "CUT_RELEASE_ERROR: release is missing $CRITICAL_PATH" >&2; exit 1; }
  git -C "$APP" show "$SHA:$CRITICAL_PATH" | cmp -s - "$TARGET/$CRITICAL_PATH" || {
    echo "CUT_RELEASE_ERROR: release file does not match $SHA: $CRITICAL_PATH" >&2; exit 1; }
done

# Migrations must use the code that is about to be pinned, but must finish
# before pin_release can enable/start the canonical timers.  The host .env is
# deliberately outside the immutable release and parsed by python-dotenv rather
# than sourced by root as shell code.  A missing DSN is an explicit deploy
# failure: proceeding would allow code that depends on a newer schema to run.
MIGRATION_ENV_FILE="${EXTRA_MIGRATION_ENV_FILE:-$APP/.env}"
[ -r "$MIGRATION_ENV_FILE" ] || {
  echo "CUT_RELEASE_ERROR: migration environment file is unreadable: $MIGRATION_ENV_FILE" >&2
  exit 1
}
MIGRATION_DSN="$(
  "$TARGET/.venv/bin/python" - "$MIGRATION_ENV_FILE" <<'PY'
import sys
from dotenv import dotenv_values

values = dotenv_values(sys.argv[1])
print(values.get("LOCAL_DATALAKE_DSN") or values.get("DATABASE_URL") or "")
PY
)"
[ -n "$MIGRATION_DSN" ] || {
  echo "CUT_RELEASE_ERROR: LOCAL_DATALAKE_DSN or DATABASE_URL is required in $MIGRATION_ENV_FILE" >&2
  exit 1
}

# Quiesce every known PNCP contracts writer before schema changes.  Merely
# disabling a timer is not enough: a oneshot it already started keeps running.
# On migration failure, restore the pre-deploy active schedule/run set.  Once
# pinning begins, a pin failure deliberately leaves writers stopped rather than
# risking a mixed-release dual-writer state.
CONTRACT_WRITER_TIMERS=(
  pncp-contracts.timer
  pncp-crawl-full.timer
  pncp-crawl-inc.timer
  extra-crawl-pncp.timer
)
CONTRACT_WRITER_SERVICES=(
  pncp-contracts.service
  pncp-crawl-full.service
  pncp-crawl-inc.service
  extra-crawl-pncp.service
)
CHAIN_TIMERS=(
  pncp-contracts.timer
  extra-confenge-target-fit-refresh.timer
  extra-confenge-target-fit-reconcile.timer
  extra-confenge-contact-cycle.timer
  extra-confenge-feed-cycle.timer
  extra-confenge-feed-monitor.timer
)
CHAIN_SERVICES=(
  pncp-contracts.service
  extra-confenge-source-freshness-gate.service
  extra-confenge-target-fit-refresh.service
  extra-confenge-target-fit-reconcile.service
  extra-confenge-target-fit-worker.service
  extra-confenge-contact-cycle.service
  extra-confenge-feed-cycle.service
  extra-confenge-feed-monitor.service
)
ACTIVE_WRITER_TIMERS=()
ACTIVE_WRITER_SERVICES=()
ACTIVE_CHAIN_TIMERS=()
ACTIVE_CHAIN_SERVICES=()
ACTIVE_CONTACT_DISCOVERY_INSTANCES=()
LEGACY_WRITER_TIMERS=(pncp-crawl-full.timer pncp-crawl-inc.timer extra-crawl-pncp.timer)
LEGACY_WRITER_SERVICES=(pncp-crawl-full.service pncp-crawl-inc.service extra-crawl-pncp.service)
if [ "$PRESERVE_TIMER_STATE" -eq 1 ]; then
  for unit in "${LEGACY_WRITER_TIMERS[@]}"; do
    if systemctl is-active --quiet "$unit" || systemctl is-enabled --quiet "$unit"; then
      echo "CUT_RELEASE_ERROR: cannot preserve unsafe legacy writer state: $unit" >&2
      exit 1
    fi
  done
  for unit in "${LEGACY_WRITER_SERVICES[@]}"; do
    if systemctl is-active --quiet "$unit"; then
      echo "CUT_RELEASE_ERROR: cannot preserve active legacy writer: $unit" >&2
      exit 1
    fi
  done
fi
for unit in "${CHAIN_TIMERS[@]}"; do
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  if [ "$PRESERVE_TIMER_STATE" -eq 1 ] && { [ "$state" = "active" ] || [ "$state" = "activating" ]; }; then ACTIVE_CHAIN_TIMERS+=("$unit"); fi
done
for unit in "${CHAIN_SERVICES[@]}"; do
  state="$(systemctl is-active "$unit" 2>/dev/null || true)"
  if [ "$PRESERVE_TIMER_STATE" -eq 1 ] && { [ "$state" = "active" ] || [ "$state" = "activating" ]; }; then ACTIVE_CHAIN_SERVICES+=("$unit"); fi
done
CONTACT_DISCOVERY_LIST="$(systemctl list-units 'extra-contact-discovery-worker@*.service' --state=active,activating --no-legend --plain)" || {
  echo "CUT_RELEASE_ERROR: cannot enumerate active contact-discovery workers" >&2
  exit 1
}
while read -r unit _; do
  [ -n "$unit" ] && ACTIVE_CONTACT_DISCOVERY_INSTANCES+=("$unit")
done <<< "$CONTACT_DISCOVERY_LIST"
if [ "$PRESERVE_TIMER_STATE" -eq 1 ]; then
  :
fi
for unit in "${CONTRACT_WRITER_TIMERS[@]}"; do
  if systemctl is-active --quiet "$unit"; then
    ACTIVE_WRITER_TIMERS+=("$unit")
  fi
done
for unit in "${CONTRACT_WRITER_SERVICES[@]}"; do
  if systemctl is-active --quiet "$unit"; then
    ACTIVE_WRITER_SERVICES+=("$unit")
  fi
done
restore_preserved_chain_state() {
  local unit failed=0
  if [ "$PRESERVE_TIMER_STATE" -ne 1 ]; then
    # A migration failure happens before the chain pin.  Restore only the
    # canonical contracts writer that this script stopped for the migration;
    # legacy writers never re-enter service.
    for unit in "${ACTIVE_WRITER_TIMERS[@]}"; do
      if [ "$unit" = "pncp-contracts.timer" ]; then systemctl start "$unit"; fi
    done
    for unit in "${ACTIVE_WRITER_SERVICES[@]}"; do
      if [ "$unit" = "pncp-contracts.service" ]; then systemctl start --no-block "$unit"; fi
    done
    return
  fi
  # Arrays contain only canonical chain units.  Legacy writers are validated
  # above and never enter a restore path.
  for unit in "${ACTIVE_CHAIN_TIMERS[@]}"; do systemctl start "$unit" || failed=1; done
  for unit in "${ACTIVE_CHAIN_SERVICES[@]}" "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do systemctl start "$unit" || failed=1; done
  for unit in "${ACTIVE_CHAIN_TIMERS[@]}" "${ACTIVE_CHAIN_SERVICES[@]}" "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ "$state" != "active" ] && [ "$state" != "activating" ]; then failed=1; fi
  done
  if [ "$failed" -ne 0 ]; then
    # A partial preserve restore is worse than a clean pause.  Do not revive
    # legacy writers while rolling back this failure.
    for unit in "${CHAIN_TIMERS[@]}" "${CHAIN_SERVICES[@]}" "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do
      if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit" || true; fi
    done
    echo "CUT_RELEASE_ERROR: preserve-state restore failed; canonical chain quiesced" >&2
    return 1
  fi
}
trap restore_preserved_chain_state EXIT
systemctl stop "${CONTRACT_WRITER_TIMERS[@]}"
systemctl stop "${CONTRACT_WRITER_SERVICES[@]}"
for unit in "${CONTRACT_WRITER_SERVICES[@]}"; do
  if systemctl is-active --quiet "$unit"; then
    echo "CUT_RELEASE_ERROR: writer did not quiesce: $unit" >&2
    exit 1
  fi
done
(
  cd "$TARGET"
  # Keep the DSN out of argv and allowlist the environment inherited from
  # root.  The trusted wrapper reads only the DSN from stdin, injects it into
  # its own environment, and invokes the immutable release module.
  printf '%s' "$MIGRATION_DSN" | runuser -u extra-consultoria -- \
    env -i \
      HOME=/var/lib/extra-consultoria \
      USER=extra-consultoria \
      LOGNAME=extra-consultoria \
      PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      PYTHONDONTWRITEBYTECODE=1 \
      PYTHONPATH="$TARGET" \
      "$TARGET/.venv/bin/python" -P -c '
import os
import sys

dsn = sys.stdin.read()
if not dsn:
    raise SystemExit("migration DSN missing on stdin")
os.environ["LOCAL_DATALAKE_DSN"] = dsn
os.environ["DATABASE_URL"] = dsn
from scripts.ops.apply_migrations import main
raise SystemExit(main(["--mode", "upgrade"]))
'
) || {
  echo "CUT_RELEASE_ERROR: migrations failed; release was not pinned" >&2
  exit 1
}
echo "CUT_RELEASE_MIGRATIONS_OK: $SHA"

# Do not let a service retain old release code while its timer/drop-in is being
# replaced.  One-shot commercial stages are not restarted here: the successful
# pin restores their canonical timers, and a failed pin leaves all of them
# quiesced for an explicit, verified recovery.
quiesce_release_chain() {
  local unit state instance instances
  for unit in "${CHAIN_TIMERS[@]}" "${CONTRACT_WRITER_TIMERS[@]}"; do
    if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
  done
  for unit in "${CHAIN_SERVICES[@]}" "${CONTRACT_WRITER_SERVICES[@]}"; do
    if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
  done
  instances="$(systemctl list-units 'extra-contact-discovery-worker@*.service' --state=active,activating --no-legend --plain)" || {
    echo "CUT_RELEASE_ERROR: cannot enumerate active contact-discovery workers" >&2
    return 1
  }
  while read -r instance _; do
    [ -n "$instance" ] || continue
    systemctl stop "$instance"
  done <<< "$instances"
  for unit in "${CHAIN_TIMERS[@]}" "${CHAIN_SERVICES[@]}" "${CONTRACT_WRITER_TIMERS[@]}" "${CONTRACT_WRITER_SERVICES[@]}"; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ -n "$state" ] && [ "$state" != "inactive" ] && [ "$state" != "failed" ] && [ "$state" != "unknown" ]; then
      echo "CUT_RELEASE_ERROR: release chain did not quiesce: $unit=$state" >&2
      return 1
    fi
  done
  instances="$(systemctl list-units 'extra-contact-discovery-worker@*.service' --state=active,activating --no-legend --plain)" || {
    echo "CUT_RELEASE_ERROR: cannot read back contact-discovery workers" >&2
    return 1
  }
  if [ -n "$instances" ]; then
    echo "CUT_RELEASE_ERROR: active contact-discovery worker instance survived quiesce" >&2
    return 1
  fi
}
quiesce_release_chain

# A failure after pinning begins leaves every chain unit stopped; this is safer
# than restoring a legacy timer alongside a partially enabled canonical schedule.
trap - EXIT
PYTHONDONTWRITEBYTECODE=1 python3 -P "$TARGET/deploy/confenge/pin_release.py" "${PIN_ARGS[@]}" || {
  quiesce_release_chain || echo "CUT_RELEASE_ERROR: failed to confirm release-chain quiesce" >&2
  echo "CUT_RELEASE_ERROR: release pin failed; release chain remains stopped" >&2
  exit 1
}
if [ "$PRESERVE_TIMER_STATE" -eq 1 ]; then
  restore_preserved_chain_state
else
  # These long-running instances were stopped for the immutable swap.  Restart
  # exactly the instances observed before quiesce, then prove each came back.
  for unit in "${ACTIVE_CONTACT_DISCOVERY_INSTANCES[@]}"; do
    systemctl start "$unit"
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ "$state" != "active" ] && [ "$state" != "activating" ]; then
      echo "CUT_RELEASE_ERROR: contact-discovery worker did not restart: $unit=$state" >&2
      quiesce_release_chain
      exit 1
    fi
  done
fi

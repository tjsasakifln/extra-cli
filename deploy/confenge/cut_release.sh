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
#   * the chain is pinned and verified through deploy/confenge/pin_release.py.
#
# Usage (as root on the host):
#   cut_release.sh <full-40-char-sha> [--preserve-timer-state]
set -euo pipefail

SHA="${1:?full 40-character release SHA required}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "CUT_RELEASE_ERROR: not a full SHA: $SHA" >&2; exit 1; }
PIN_ARGS=("$SHA")
if [ "${2:-}" = "--preserve-timer-state" ] && [ "$#" -eq 2 ]; then
  PIN_ARGS+=("--preserve-timer-state")
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

PYTHONDONTWRITEBYTECODE=1 python3 -P "$TARGET/deploy/confenge/pin_release.py" "${PIN_ARGS[@]}"

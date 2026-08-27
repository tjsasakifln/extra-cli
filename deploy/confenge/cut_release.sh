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
# Usage (as root on the host):  cut_release.sh <full-40-char-sha>
set -euo pipefail

SHA="${1:?full 40-character release SHA required}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "CUT_RELEASE_ERROR: not a full SHA: $SHA" >&2; exit 1; }

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
  PREV="$(ls -1dt "$RELEASES"/*/ 2>/dev/null | head -1 | sed 's:/*$::')"
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
  "$STAGING/.venv/bin/python" -c "import sys; sys.exit(0)" || {
    echo "CUT_RELEASE_ERROR: copied interpreter does not run" >&2; exit 1; }
  PYTHONPATH="$STAGING" "$STAGING/.venv/bin/python" -c "
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

python3 "$TARGET/deploy/confenge/pin_release.py" "$SHA"

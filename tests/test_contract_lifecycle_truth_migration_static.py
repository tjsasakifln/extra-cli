"""AC1 — additivity of migration 103, proven statically.

Story: contract-lifecycle-truth-v1.

Two independent checks:

1. The migration text itself contains no ``ALTER`` and no ``DROP``, and uses
   ``CREATE OR REPLACE`` only for the four object names it creates.
2. The files changed by this story's commits are a subset of ``scope_files``
   in ``.aiox/state/stories/contract-lifecycle-truth-v1.json``. This is what
   actually proves migrations 077/091/101 and ``commercial_authority_v2.py``
   were not edited — a clean-looking migration text alone does not.

No database connection is used, so ``@pytest.mark.real_db`` does not apply.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "db" / "migrations" / "103_contract_lifecycle_truth.sql"
STATE_FILE = REPO_ROOT / ".aiox" / "state" / "stories" / "contract-lifecycle-truth-v1.json"

# The only names this migration is permitted to declare with CREATE OR REPLACE.
# None of them existed before it, so re-declaring them is additive, never a
# mutation of a pre-existing object.
CREATE_OR_REPLACE_ALLOW_LIST = {
    "public.contract_contracting_date_v1",
    "public.contract_contracting_date_field_v1",
    "public.contract_window_floor_v1",
    "public.v_contract_lifecycle_truth_v1",
}

# Trunk refs tried in order. The worktree's local ``main`` can legitimately lag
# behind ``origin/main``; the base AC1 asks for is the branch point of this
# story's commits, which ``origin/main`` resolves correctly in both a worktree
# and a fresh CI clone (where the two refs agree).
TRUNK_REFS = ("origin/main", "main")


def _migration_text() -> str:
    assert MIGRATION.exists(), f"migration not found: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _diff_base() -> str:
    for ref in TRUNK_REFS:
        result = _git("merge-base", ref, "HEAD")
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    pytest.fail("no trunk ref resolvable for the AC1 diff base")
    raise AssertionError("unreachable")


def test_migration_contains_no_alter_statement():
    assert not re.search(r"\balter\b", _migration_text(), re.IGNORECASE)


def test_migration_contains_no_drop_statement():
    assert not re.search(r"\bdrop\b", _migration_text(), re.IGNORECASE)


def test_create_or_replace_targets_only_objects_this_migration_creates():
    targets = re.findall(
        r"CREATE\s+OR\s+REPLACE\s+(?:\w+\s+)*?(?:FUNCTION|VIEW|PROCEDURE|TRIGGER|RULE)\s+"
        r"([A-Za-z_][\w.]*)",
        _migration_text(),
        re.IGNORECASE,
    )
    assert targets, "expected the migration to declare its own objects"
    outside = {name for name in targets if name not in CREATE_OR_REPLACE_ALLOW_LIST}
    assert not outside, f"CREATE OR REPLACE on objects outside the allow-list: {sorted(outside)}"


def test_migration_declares_all_four_new_objects():
    targets = set(
        re.findall(
            r"CREATE\s+OR\s+REPLACE\s+(?:\w+\s+)*?(?:FUNCTION|VIEW)\s+([A-Za-z_][\w.]*)",
            _migration_text(),
            re.IGNORECASE,
        )
    )
    assert targets == CREATE_OR_REPLACE_ALLOW_LIST


def test_changed_files_are_a_subset_of_scope_files():
    """Every file this story's commits touched is inside ``scope_files``."""
    scope_files = set(json.loads(STATE_FILE.read_text(encoding="utf-8"))["scope_files"])
    assert str(STATE_FILE.relative_to(REPO_ROOT)) in scope_files

    base = _diff_base()
    result = _git("diff", "--name-only", f"{base}..HEAD")
    assert result.returncode == 0, result.stderr
    changed = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    outside = changed - scope_files
    assert not outside, f"files changed outside scope_files (base {base}): {sorted(outside)}"


@pytest.mark.parametrize(
    "protected",
    [
        "db/migrations/077_contract_roles_canonical_v2.sql",
        "db/migrations/091_contract_truth_durability.sql",
        "db/migrations/101_contract_reference_scope_truth.sql",
        "scripts/confenge_activation/commercial_authority_v2.py",
        "scripts/confenge_activation/rebuild_commercial_qualification.py",
        "scripts/contracts_truth.py",
        "scripts/testing/connection_policy.py",
    ],
)
def test_protected_files_were_not_touched(protected):
    """Named restatement of the subset check for the files that matter most."""
    base = _diff_base()
    result = _git("diff", "--name-only", f"{base}..HEAD", "--", protected)
    assert result.returncode == 0, result.stderr
    assert not result.stdout.strip(), f"{protected} was modified by this story"

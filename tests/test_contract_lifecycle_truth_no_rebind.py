"""AC18 — nothing was rebound to the objects added by migration 103.

Story: contract-lifecycle-truth-v1.

The ICP membership invariant ("this migration cannot change who qualifies") is
carried structurally, not statistically. This module asserts by name that:

(a) ``scripts/confenge_activation/commercial_authority_v2.py`` contains no
    reference to the new view or to any of the three new SQL functions; and
(b) the ``QUALIFICATION_SQL`` constant in
    ``scripts/confenge_activation/rebuild_commercial_qualification.py``
    (consumed by ``iter_qualifications()``) contains no such reference either,
    and still reads ``FROM public.v_contracts_canonical_v2 c`` unchanged.

Until story 3 rebinds the rebuilder, its inline ``CASE`` precedence and the new
SQL functions are two independently-maintained copies of the same rule that can
drift. That is the registered, accepted risk of shipping story 1 alone.

No database connection is used, so ``@pytest.mark.real_db`` does not apply.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.confenge_activation.rebuild_commercial_qualification import QUALIFICATION_SQL

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMERCIAL_AUTHORITY = REPO_ROOT / "scripts" / "confenge_activation" / "commercial_authority_v2.py"
REBUILDER = REPO_ROOT / "scripts" / "confenge_activation" / "rebuild_commercial_qualification.py"

NEW_OBJECT_NAMES = (
    "v_contract_lifecycle_truth_v1",
    "contract_contracting_date_v1",
    "contract_contracting_date_field_v1",
    "contract_window_floor_v1",
)


@pytest.mark.parametrize("object_name", NEW_OBJECT_NAMES)
def test_commercial_authority_does_not_reference_new_objects(object_name):
    source = COMMERCIAL_AUTHORITY.read_text(encoding="utf-8")
    assert object_name not in source


@pytest.mark.parametrize("object_name", NEW_OBJECT_NAMES)
def test_rebuilder_source_does_not_reference_new_objects(object_name):
    source = REBUILDER.read_text(encoding="utf-8")
    assert object_name not in source


@pytest.mark.parametrize("object_name", NEW_OBJECT_NAMES)
def test_qualification_sql_does_not_reference_new_objects(object_name):
    assert object_name not in QUALIFICATION_SQL


def test_qualification_sql_still_reads_canonical_v2():
    assert "FROM public.v_contracts_canonical_v2 c" in QUALIFICATION_SQL


def test_commercial_authority_evidence_source_is_unchanged():
    """Warmbly consumes ``evidence_hash``; the evidence source must not drift."""
    from scripts.confenge_activation.commercial_authority_v2 import (
        CONTRACT_VERSION,
        EVIDENCE_SOURCE,
    )

    assert EVIDENCE_SOURCE == "extra-cli:v_contracts_canonical_v2"
    assert CONTRACT_VERSION == "COMMERCIAL_AUTHORITY/2.0"

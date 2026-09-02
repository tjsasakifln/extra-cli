"""AC 25(a) — parafiscal suppressions must travel as declared revocations.

The parafiscal gate removes ~68 roots from TARGET_CONFIRMED. `publish.py`'s
`_assert_membership_deactivation_delta` is NOT a numeric ceiling: it requires
`declared == expected`, raising ValueError → PUBLICATION_REFUSED when a root
leaves the published membership without an explicit revocation carrying
`MEMBERSHIP_DROP_REASON`.

This is the CI-verifiable half of AC 25. The other half (a real publication
build completing without PUBLICATION_REFUSED) is @devops, post-deploy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.confenge_activation.publish import (
    MEMBERSHIP_DROP_REASON,
    _assert_membership_deactivation_delta,
)

# Real Sistema S roots suppressed by the parafiscal gate (AC 21).
SUPPRESSED_ROOTS = ["03575238", "03709814", "03776284", "16589137"]
SURVIVING_ROOT = "11222333"


def _lead(root: str) -> dict[str, object]:
    return {
        "target_fit_class": "TARGET_CONFIRMED",
        "company": {"cnpj14": f"{root}000199"},
    }


def _write_build(directory: Path, roots: list[str]) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "chunk-0001.json").write_text(
        json.dumps({"leads": [_lead(r) for r in roots]}), encoding="utf-8"
    )
    return {"chunks": [{"file": "chunk-0001.json"}]}


def _revocation(root: str) -> dict[str, object]:
    return {"cnpj14": f"{root}000199", "reason_codes": [MEMBERSHIP_DROP_REASON]}


def test_declared_revocations_close_the_parafiscal_delta(tmp_path: Path) -> None:
    prior_dir = tmp_path / "prior"
    next_dir = tmp_path / "next"
    prior_manifest = _write_build(prior_dir, [*SUPPRESSED_ROOTS, SURVIVING_ROOT])
    next_manifest = _write_build(next_dir, [SURVIVING_ROOT])
    next_manifest["deactivations"] = [_revocation(r) for r in SUPPRESSED_ROOTS]

    # Must not raise: every root leaving TARGET_CONFIRMED travels declared.
    _assert_membership_deactivation_delta(
        prior_dir, prior_manifest, next_dir, next_manifest
    )


def test_publication_is_refused_when_a_suppression_is_not_declared(
    tmp_path: Path,
) -> None:
    """The failure mode that would block @devops if the build stayed silent."""
    prior_dir = tmp_path / "prior"
    next_dir = tmp_path / "next"
    prior_manifest = _write_build(prior_dir, [*SUPPRESSED_ROOTS, SURVIVING_ROOT])
    next_manifest = _write_build(next_dir, [SURVIVING_ROOT])
    # One root suppressed by the gate but omitted from the revocations.
    next_manifest["deactivations"] = [_revocation(r) for r in SUPPRESSED_ROOTS[:-1]]

    with pytest.raises(ValueError, match="membership-drop deactivations"):
        _assert_membership_deactivation_delta(
            prior_dir, prior_manifest, next_dir, next_manifest
        )


def test_revocation_without_the_membership_drop_reason_does_not_count(
    tmp_path: Path,
) -> None:
    """`publish.py:249` keys on MEMBERSHIP_DROP_REASON specifically."""
    prior_dir = tmp_path / "prior"
    next_dir = tmp_path / "next"
    prior_manifest = _write_build(prior_dir, [SUPPRESSED_ROOTS[0], SURVIVING_ROOT])
    next_manifest = _write_build(next_dir, [SURVIVING_ROOT])
    next_manifest["deactivations"] = [
        {
            "cnpj14": f"{SUPPRESSED_ROOTS[0]}000199",
            "reason_codes": ["parafiscal_institutional_hard_out"],
        }
    ]

    with pytest.raises(ValueError, match="membership-drop deactivations"):
        _assert_membership_deactivation_delta(
            prior_dir, prior_manifest, next_dir, next_manifest
        )

"""AC 18 + Task 8.0 — rule versions bumped and classifier fingerprints drift.

The post-deploy reclassification mechanism (Task 8.0) is
`scripts/confenge_target_fit/reconcile.py:338`, which enqueues any materialized
row whose stored `classifier_sha` differs from the current one — with no filter
on `target_fit_class`, so rows already in TARGET_CONFIRMED are reprocessed.

These tests prove the trigger predicate: the fingerprints are pure functions of
the classifier module sources, so editing those modules necessarily changes them.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

from scripts.commercial_leads import contract_relevance as relevance_module
from scripts.commercial_leads import sector_fit as sector_fit_module
from scripts.commercial_leads.contract_relevance import RULE_VERSION
from scripts.confenge_sector import classification as classification_module
from scripts.confenge_sector.store import sector_classifier_sha256
from scripts.confenge_target_fit.compute import classifier_sha
from scripts.confenge_universe import parafiscal as parafiscal_module
from scripts.confenge_universe import target_fit as target_fit_module
from scripts.confenge_universe.target_fit import TARGET_FIT_VERSION


def test_rule_versions_are_bumped() -> None:
    assert RULE_VERSION != "contract-relevance-v2"
    assert TARGET_FIT_VERSION != "confenge-target-fit-v2"


def test_target_fit_classifier_sha_tracks_module_sources() -> None:
    """`compute.classifier_sha()` is recomputed from live source, not stored."""
    expected = "sha256:" + hashlib.sha256(
        "\n".join(
            (
                inspect.getsource(target_fit_module),
                inspect.getsource(relevance_module),
                inspect.getsource(parafiscal_module),
            )
        ).encode("utf-8")
    ).hexdigest()
    assert classifier_sha() == expected


def test_classifier_sha_includes_the_parafiscal_taxonomy_module() -> None:
    """AC 23b — `parafiscal.py` source is part of the hashed material."""
    assert inspect.getsource(parafiscal_module) in "\n".join(
        (
            inspect.getsource(target_fit_module),
            inspect.getsource(relevance_module),
            inspect.getsource(parafiscal_module),
        )
    )
    # And the sha would differ if it were omitted (the pre-iteration-2 formula).
    without_parafiscal = "sha256:" + hashlib.sha256(
        "\n".join(
            (
                inspect.getsource(target_fit_module),
                inspect.getsource(relevance_module),
            )
        ).encode("utf-8")
    ).hexdigest()
    assert classifier_sha() != without_parafiscal


def test_adding_a_parafiscal_marker_changes_classifier_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC 23c — a taxonomy edit makes `reconcile` re-enqueue again.

    Proven end-to-end through the real `classifier_sha()`, by swapping the
    imported module for one whose SOURCE FILE carries an extra marker.
    Monkeypatching the tuple in memory would NOT be a valid proof:
    `inspect.getsource` reads the file on disk and would never see it.
    """
    baseline = classifier_sha()

    original_src = inspect.getsource(parafiscal_module)
    edited_src = original_src.replace(
        '    "sebrae",\n',
        '    "sebrae",\n    "instituto parafiscal ficticio",\n',
        1,
    )
    assert edited_src != original_src, "fixture failed to inject the extra marker"

    edited_path = tmp_path / "parafiscal_edited.py"
    edited_path.write_text(edited_src, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "scripts.confenge_universe.parafiscal", edited_path
    )
    assert spec and spec.loader
    edited_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(edited_module)

    monkeypatch.setitem(
        sys.modules, "scripts.confenge_universe.parafiscal", edited_module
    )
    # `classifier_sha()` resolves the module via `from scripts.confenge_universe
    # import parafiscal`, which reads the package attribute, not sys.modules.
    monkeypatch.setattr(
        sys.modules["scripts.confenge_universe"], "parafiscal", edited_module
    )
    drifted = classifier_sha()

    assert drifted != baseline, "adding a marker must produce classifier drift"


def test_sector_classifier_sha_tracks_module_sources() -> None:
    sector_classifier_sha256.cache_clear()
    expected = hashlib.sha256(
        "\n".join(
            (
                inspect.getsource(classification_module),
                inspect.getsource(sector_fit_module),
                inspect.getsource(relevance_module),
            )
        ).encode("utf-8")
    ).hexdigest()
    assert sector_classifier_sha256() == expected


def test_reconcile_drift_predicate_fires_for_a_stale_row() -> None:
    """Mirrors reconcile.py:335-340 — both drift triggers fire independently."""
    stale_row = {
        "target_fit_version": "confenge-target-fit-v2",
        "classifier_sha": "sha256:" + "0" * 64,
        "target_fit_class": "TARGET_CONFIRMED",
    }
    assert stale_row["target_fit_version"] != TARGET_FIT_VERSION
    assert str(stale_row["classifier_sha"]) != classifier_sha()

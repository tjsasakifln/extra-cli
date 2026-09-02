"""AC 16 — no regression on the real 1076-object corpus.

Ported from `docs/stories/assets/story-outbound-sector-classifier-false-positive-01/
architect-exp3-baseline.py` (the @architect baseline, persisted by the @po).

Baseline measured BEFORE the change, on this same versioned corpus:
    relevance PASS = 222   is_execution = 100
    labeled gate:  P = 1.0   R = 1.0  (tp=20 fp=0 tn=24 fn=0)

The AC requires zero `execution True→False` transitions outside the 6 adversarial
target objects. Those 6 are synthetic and are NOT present in the real corpus, so
the operational assertion here is: zero transitions at all.

No monkeypatching, no mocks: this calls the shipped functions and reads the
git-versioned corpora, so it runs in CI without credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.commercial_leads.contract_relevance import classify_contract_relevance
from scripts.confenge_universe.target_fit import _object_is_execution

# tests/commercial_leads/<file>  →  parents[2] == repository root
REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_CORPUS_DIR = REPO_ROOT / "evals" / "commercial_leads" / "real"
LABELED_CORPUS_DIR = REPO_ROOT / "evals" / "commercial_leads"

# Measured on the pre-change code by the @architect and re-measured by the @dev.
BASELINE_REAL_CORPUS_SIZE = 1076
BASELINE_RELEVANCE_PASS = 222
BASELINE_IS_EXECUTION = 100

# Per-file breakdown. A single global count could hide one True→False flip offset
# by one False→True flip; pinning each shard makes that cancellation impossible
# to sneak through. Values are pre-change values: the baseline run's "ALL FLIPS"
# section was EMPTY, i.e. no object changed classification, so the pre-change and
# post-change breakdowns are identical by construction.
BASELINE_PER_FILE: dict[str, tuple[int, int, int]] = {
    # filename: (objects, relevance PASS, is_execution)
    "development-real-v1.jsonl": (368, 82, 38),
    "development-real-v2.jsonl": (368, 82, 38),
    "holdout-real-v1.jsonl": (100, 18, 7),
    "holdout-real-v2.jsonl": (100, 18, 7),
    "validation-real-v1.jsonl": (70, 11, 5),
    "validation-real-v2.jsonl": (70, 11, 5),
}
GATE_MIN_PRECISION = 0.95
GATE_MIN_RECALL = 0.90


def _load_real_objects() -> list[str]:
    objects: list[str] = []
    for path in sorted(REAL_CORPUS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            obj = row.get("objeto_contrato_original") or row.get("objeto") or ""
            if obj:
                objects.append(obj)
    return objects


def _load_labeled_pairs() -> list[tuple[str, bool]]:
    pairs: list[tuple[str, bool]] = []
    for path in sorted(LABELED_CORPUS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("relevant") is None:
                continue
            pairs.append((row.get("objeto") or "", bool(row["relevant"])))
    return pairs


@pytest.fixture(scope="module")
def real_objects() -> list[str]:
    objects = _load_real_objects()
    if not objects:
        pytest.fail(f"real corpus not found under {REAL_CORPUS_DIR}")
    return objects


def test_real_corpus_size_is_stable(real_objects: list[str]) -> None:
    assert len(real_objects) == BASELINE_REAL_CORPUS_SIZE


def test_relevance_pass_count_matches_baseline(real_objects: list[str]) -> None:
    passes = sum(
        1 for obj in real_objects if classify_contract_relevance(obj).status == "PASS"
    )
    assert passes == BASELINE_RELEVANCE_PASS, (
        f"relevance PASS drifted: baseline={BASELINE_RELEVANCE_PASS} now={passes}"
    )


def test_execution_count_has_no_regression(real_objects: list[str]) -> None:
    """AC 16 — no `execution True→False` flip outside the 6 adversarial targets.

    None of the 6 targets exist in the real corpus, so the count must be exactly
    the baseline. A drop would be a real-recall regression; a rise would be a
    precision regression.
    """
    executions = sum(1 for obj in real_objects if _object_is_execution(obj))
    assert executions == BASELINE_IS_EXECUTION, (
        f"is_execution drifted: baseline={BASELINE_IS_EXECUTION} now={executions}"
    )


@pytest.mark.parametrize("filename", sorted(BASELINE_PER_FILE))
def test_per_shard_classification_matches_baseline(filename: str) -> None:
    """AC 16, strict form — per-shard counts, so offsetting flips cannot cancel."""
    path = REAL_CORPUS_DIR / filename
    assert path.is_file(), f"missing corpus shard: {path}"
    objects = [
        obj
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for obj in [
            (json.loads(line).get("objeto_contrato_original") or json.loads(line).get("objeto") or "")
        ]
        if obj
    ]
    expected_n, expected_pass, expected_exec = BASELINE_PER_FILE[filename]
    actual_pass = sum(
        1 for obj in objects if classify_contract_relevance(obj).status == "PASS"
    )
    actual_exec = sum(1 for obj in objects if _object_is_execution(obj))
    assert (len(objects), actual_pass, actual_exec) == (
        expected_n,
        expected_pass,
        expected_exec,
    ), filename


def test_labeled_gate_thresholds_hold() -> None:
    """AC 15 — reuse the labeled holdout gate: P>=0.95, R>=0.90."""
    pairs = _load_labeled_pairs()
    assert pairs, f"labeled corpus not found under {LABELED_CORPUS_DIR}"
    tp = fp = fn = 0
    for objeto, expected in pairs:
        predicted = classify_contract_relevance(objeto).status == "PASS"
        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    assert precision >= GATE_MIN_PRECISION, f"precision={precision}"
    assert recall >= GATE_MIN_RECALL, f"recall={recall}"

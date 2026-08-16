"""Material change invalidates only the affected pack."""

from __future__ import annotations

import copy
from pathlib import Path

from scripts.contract_publication.engine import (
    build_packs,
    build_run_document,
    input_payload_hash,
    load_snapshot,
    rank_candidates,
)
from scripts.contract_publication.schema import load_policy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def _document(records, as_of, mode, previous=None):
    policy = load_policy()
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=mode, policy=policy)
    packs = build_packs(records, ranked, as_of=as_of, catalog_mode=mode, policy=policy)
    digest = input_payload_hash(records, as_of=as_of, policy=policy, window_start=None, window_end=None)
    return (
        build_run_document(
            ranked,
            packs,
            as_of=as_of,
            input_hash=digest,
            catalog_mode=mode,
            policy=policy,
            snapshot_id="golden",
            previous_candidates=previous,
        ),
        ranked,
        packs,
    )


def test_material_change_invalidates_only_affected_candidate() -> None:
    as_of, records, mode, _ = load_snapshot(FIXTURE)
    first, ranked, packs = _document(records, as_of, mode)
    prior = [
        {
            "analysis_candidate_id": item.analysis_candidate_id,
            "material_fingerprint": item.material_fingerprint,
            "evidence_pack_hash": packs[item.analysis_candidate_id]["content_hash"],
        }
        for item in ranked
    ]
    changed = copy.deepcopy(records)
    target = next(item for item in changed if item["canonical_contract_id"] == "CAND-VALUE-TERM-01")
    target["valor_total"] = 15000000
    target["value_changes"] = [
        {"id": "vc-1", "delta": 4000000, "at": "2026-03-01T00:00:00+00:00", "ref": "doc:aditivo-01"}
    ]
    second, _ranked2, packs2 = _document(changed, as_of, mode, previous=prior)
    report = second["invalidation"]
    assert report["invalidated"] == ["CAND-VALUE-TERM-01"]
    assert "CAND-BDI-01" in report["unchanged"]
    assert "CAND-REAJUSTE-01" in report["unchanged"]
    assert packs["CAND-BDI-01"]["content_hash"] == packs2["CAND-BDI-01"]["content_hash"]
    assert packs["CAND-VALUE-TERM-01"]["content_hash"] != packs2["CAND-VALUE-TERM-01"]["content_hash"]
    assert first["content_hash"] != second["content_hash"]

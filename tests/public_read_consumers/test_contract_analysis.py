"""Contract-analysis adapter compatibility with public-read-contract-analysis/1.0."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_read_consumers.contract_analysis import (
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    SCHEMA,
    project_catalog,
    select_canary,
)
from scripts.public_read_consumers.export import build_contract_analysis_bundle, write_contract_analysis_export
from scripts.public_read_consumers.hashutil import content_hash

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "public_read_consumers" / "contract_analysis"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_ready_catalog_is_data_ready_and_never_index() -> None:
    analyses = project_catalog(_load("catalog.json"))
    assert len(analyses) == 8
    assert all(item["data_state"] == DATA_READY for item in analyses)
    assert all(item["publication_readiness"] == DATA_READY for item in analyses)
    assert all(item["schema"] == SCHEMA for item in analyses)
    assert all(item["data_state"] != "INDEX" for item in analyses)
    assert all(item["official_live"] is False for item in analyses)
    assert all(item["producer_status"] == "CONTRACT_FIXTURE" for item in analyses)
    scored = analyses[0]["candidate_score"]
    assert scored["value"] == 0.94
    assert scored["schema"] == "contract-publication-candidate/1.0"
    peer = next(item for item in analyses if item["analysis_candidate_id"] == "cand-preco-02")
    assert peer["peer_group"]["status"] == "NOT_COMPARABLE"
    assert "NOT_COMPARABLE" in peer["reason_codes"]
    assert peer["data_state"] == DATA_READY


def test_unknown_calculation_stays_null() -> None:
    raw = _load("catalog.json")
    raw["candidates"][0]["evidence_pack"]["calculations"].append(
        {"name": "unit_price", "value": 0, "epistemic_class": "UNKNOWN"}
    )
    payload = project_catalog(raw)[0]
    unknown = [item for item in payload["calculations"] if item["epistemic_class"] == "UNKNOWN"]
    assert unknown
    assert unknown[0]["value"] is None
    assert "UNKNOWN" in payload["epistemic_classes"]


def test_stale_evidence_holds() -> None:
    analyses = project_catalog(_load("catalog_stale.json"))
    assert analyses[0]["data_state"] == DATA_HOLD
    assert "stale_evidence" in analyses[0]["reason_codes"]
    assert analyses[0]["freshness"]["stale"] is True


def test_fixture_as_live_is_rejected() -> None:
    analyses = project_catalog(_load("catalog_fixture_as_live.json"))
    assert analyses[0]["data_state"] == DATA_REJECT
    assert "fixture_as_live" in analyses[0]["reason_codes"]
    assert analyses[0]["official_live"] is False


def test_missing_producer_rejects() -> None:
    analyses = project_catalog(_load("catalog_missing.json"))
    assert analyses[0]["data_state"] == DATA_REJECT
    assert "producer_missing" in analyses[0]["reason_codes"]


def test_415_status_map() -> None:
    analyses = {item["analysis_candidate_id"]: item for item in project_catalog(_load("catalog.json"))}
    assert analyses["cand-preco-01"]["peer_group"]["status"] == "PEER_VALID"
    assert analyses["cand-reajuste-01"]["peer_group"]["status"] == "PEER_WEAK"
    assert analyses["cand-aditivo-01"]["peer_group"]["status"] == "ABSENT"


def test_canary_selects_ready_shortlist() -> None:
    canary = select_canary(project_catalog(_load("catalog.json")))
    assert 5 <= len(canary.selected_ids) <= 10
    assert canary.shortfall is False


def test_bundle_is_pr85_shape_and_deterministic(tmp_path: Path) -> None:
    raw = _load("catalog.json")
    first = build_contract_analysis_bundle(raw)
    second = build_contract_analysis_bundle(raw)
    assert first["content_hash"] == second["content_hash"]
    manifest = first["manifest"]
    assert manifest["schema"] == SCHEMA
    assert manifest["catalog_mode"] == "fixture"
    assert manifest["claimed_live"] is False
    assert manifest["official_live"] is False
    assert manifest["producer_status"] == "CONTRACT_FIXTURE"
    assert isinstance(manifest["analyses"], list)
    write_contract_analysis_export(raw, tmp_path)
    on_disk = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert on_disk["content_hash"] == first["content_hash"]
    sample = json.loads((tmp_path / "analyses" / "cand-preco-01.json").read_text(encoding="utf-8"))
    assert sample["data_state"] in {DATA_READY, DATA_HOLD, DATA_REJECT}
    assert sample["publication_readiness"] == sample["data_state"]
    body = {key: value for key, value in sample.items() if key != "content_hash"}
    assert sample["content_hash"] == content_hash(body)


def test_score_version_mismatch_rejects() -> None:
    raw = _load("catalog.json")
    raw["candidates"][0]["score"]["version"] = "9.9"
    payload = project_catalog(raw)[0]
    assert payload["data_state"] == DATA_REJECT
    assert "score_version_mismatch" in payload["reason_codes"]

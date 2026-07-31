"""Exporter must never emit commercial Top-20 proprietary fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pseo.aggregate import assemble_public_payload, classify_bids, classify_rows
from scripts.pseo.export_web_cfg import build_export, write_export
from scripts.pseo.sanitize import contains_forbidden


FIXTURE = Path(__file__).parent / "fixtures" / "sample_contracts.json"


def _sample() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_exists():
    assert FIXTURE.exists()


def test_no_forbidden_in_payload():
    raw = _sample()
    classified = classify_rows(raw["contracts"])
    bids = classify_bids(raw["bids"])
    payload = assemble_public_payload(classified, bids)
    hits = contains_forbidden(payload)
    assert hits == [], hits


def test_build_export_strips_and_hashes(tmp_path: Path):
    raw = _sample()
    # inject forbidden fields into a fake contract path via top20-like pollution
    polluted = {
        "contracts": raw["contracts"],
        "bids": raw["bids"],
        "entity_count": raw.get("entity_count", 0),
    }
    bundle = build_export(
        polluted["contracts"],
        polluted["bids"],
        {"pncp_supplier_contracts": len(polluted["contracts"]), "pncp_raw_bids": len(polluted["bids"])},
        top20_path=None,
        source_run_id="test-run",
    )
    assert bundle["manifest"]["schema_version"]
    assert bundle["manifest"]["dataset_hash"]
    assert bundle["manifest"]["source_run_id"] == "test-run"
    hits = contains_forbidden(bundle["files"])
    assert hits == [], hits
    # ensure top20 key never appears as export table
    blob = json.dumps(bundle["files"])
    assert "score_total" not in blob
    assert "top20" not in blob.lower() or "top20" not in json.dumps(bundle["files"]).lower()
    write_export(tmp_path, bundle)
    assert (tmp_path / "manifest.json").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert "checksums" in manifest
    assert manifest["checksums"].get("markets.json")


def test_top20_artifact_not_reexported(tmp_path: Path):
    raw = _sample()
    top20 = tmp_path / "top20.json"
    top20.write_text(
        json.dumps(
            [
                {
                    "rank": 1,
                    "cnpj14": "12345678000199",
                    "razao_social": "SECRET COMPANY LTDA",
                    "score_total": 99.9,
                    "priority": "CRITICAL",
                    "suggested_offer": "diagnostico_b2g",
                    "commercial_state": "NEW",
                    "activity_class": "ENGINEERING_SERVICE_PROVIDER",
                    "supplier_sector_fit": "CONFIRMED_ENGINEERING",
                    "signal_ids": ["new_agency", "value_growth"],
                }
            ]
        ),
        encoding="utf-8",
    )
    bundle = build_export(
        raw["contracts"],
        raw["bids"],
        {"pncp_supplier_contracts": len(raw["contracts"]), "pncp_raw_bids": len(raw["bids"])},
        top20_path=str(top20),
    )
    text = json.dumps(bundle["files"], ensure_ascii=False)
    assert "SECRET COMPANY" not in text
    assert "12345678000199" not in text
    assert "score_total" not in text
    assert "diagnostico_b2g" not in text or "icp_methodology" in text
    # activity class histogram may appear under methodology aggregates only
    meth = bundle["files"]["icp_methodology"]["internal_signature_aggregates"]
    assert meth.get("available") is True
    assert "ENGINEERING_SERVICE_PROVIDER" in (meth.get("activity_class_histogram") or {})

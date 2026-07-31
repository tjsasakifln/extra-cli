"""Provenance: dataset_hash recomposition, checksums, determinism."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.pseo.pipeline import build_export, write_export
from scripts.pseo.provenance import compute_dataset_hash, verify_snapshot_hashes
from scripts.pseo.validation import validate_export_dir

FIXTURE = Path(__file__).parent / "fixtures" / "sample_contracts.json"


def test_export_deterministic_hash(tmp_path: Path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counts = {
        "pncp_supplier_contracts": len(raw["contracts"]),
        "pncp_raw_bids": len(raw["bids"]),
    }
    b1 = build_export(
        raw["contracts"],
        raw["bids"],
        counts,
        top20_path=None,
        source_run_id="det-test",
        as_of="2026-07-31",
    )
    b2 = build_export(
        raw["contracts"],
        raw["bids"],
        counts,
        top20_path=None,
        source_run_id="det-test",
        as_of="2026-07-31",
    )
    assert b1["dataset_hash"] == b2["dataset_hash"]
    assert b1["dataset_hash"] == compute_dataset_hash(b1["files"])


def test_byte_change_changes_hash(tmp_path: Path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counts = {
        "pncp_supplier_contracts": len(raw["contracts"]),
        "pncp_raw_bids": len(raw["bids"]),
    }
    bundle = build_export(
        raw["contracts"],
        raw["bids"],
        counts,
        top20_path=None,
        source_run_id="mut-test",
        as_of="2026-07-31",
    )
    write_export(tmp_path, bundle)
    h1 = bundle["dataset_hash"]
    markets = tmp_path / "markets.json"
    data = json.loads(markets.read_text(encoding="utf-8"))
    # mutate a material byte of the dataset body (not trailing whitespace)
    if isinstance(data, list) and data:
        data[0]["contract_count"] = int(data[0].get("contract_count") or 0) + 1
    else:
        data = {"mutated": True}
    markets.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    body = {}
    for key in (
        "archetypes",
        "markets",
        "agencies",
        "prices",
        "competition",
        "opportunities",
        "problem_service",
        "icp_methodology",
    ):
        body[key] = json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8"))
    h2 = compute_dataset_hash(body)
    assert h1 != h2


def test_checksums_and_validation(tmp_path: Path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counts = {
        "pncp_supplier_contracts": len(raw["contracts"]),
        "pncp_raw_bids": len(raw["bids"]),
    }
    bundle = build_export(
        raw["contracts"],
        raw["bids"],
        counts,
        top20_path=None,
        source_run_id="val-test",
        as_of="2026-07-31",
    )
    write_export(tmp_path, bundle)
    errs = verify_snapshot_hashes(tmp_path, json.loads((tmp_path / "manifest.json").read_text()))
    assert errs == [], errs
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    for field in (
        "schema_version",
        "generated_at",
        "data_as_of",
        "source_run_id",
        "source_commit_sha",
        "export_entrypoint",
        "dataset_hash",
        "checksums",
        "timezone",
    ):
        assert field in manifest or field.replace("export_", "exporter_") in manifest
    # source_commit should not be empty
    assert manifest.get("source_commit_sha")
    assert manifest.get("export_entrypoint") or manifest.get("exporter_entrypoint")


def test_no_private_fields(tmp_path: Path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counts = {
        "pncp_supplier_contracts": len(raw["contracts"]),
        "pncp_raw_bids": len(raw["bids"]),
    }
    bundle = build_export(
        raw["contracts"],
        raw["bids"],
        counts,
        top20_path=None,
        source_run_id="priv-test",
        as_of="2026-07-31",
    )
    blob = json.dumps(bundle["files"])
    for needle in (
        "score_total",
        "commercial_state",
        "human_notes",
        "do_not_contact",
        "suggested_offer",
        "pipeline_state",
    ):
        assert needle not in blob

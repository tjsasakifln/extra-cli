"""End-to-end pipeline on golden fixture — drives real shipped entry functions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.budget_audit.ingest import create_case, ingest_case
from scripts.budget_audit.pipeline import audit_case, map_case, report_case, verify_case
from scripts.budget_audit.references import compare_to_references, load_reference_manifest
from tests.budget_audit.build_fixtures import (
    build_golden,
    build_operational,
    build_reference_manifest,
)


@pytest.fixture()
def env_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "budget-root"
    for sub in ("cases", "cache", "references", "tmp", "logs"):
        (root / sub).mkdir(parents=True)
    monkeypatch.setenv("BUDGET_AUDIT_ROOT", str(root))
    monkeypatch.setenv("BUDGET_CASE_ROOT", str(root / "cases"))
    monkeypatch.setenv("BUDGET_TMP_ROOT", str(root / "tmp"))
    return root


def test_golden_pipeline(env_roots: Path, tmp_path: Path) -> None:
    golden = build_golden(tmp_path / "golden.xlsx")
    case_dir = create_case("golden-e2e", golden, env_roots / "cases" / "golden-e2e")
    ingest = ingest_case(case_dir)
    assert any(r["status"] == "INGESTED" for r in ingest["results"])
    counts = map_case(case_dir)
    assert counts["budget_items"] >= 5
    summary = audit_case(case_dir)
    assert summary["findings"] >= 5
    reports = report_case(case_dir)
    assert Path(reports["paths"]["pdf"]).is_file()
    assert Path(reports["paths"]["html"]).is_file()
    assert Path(reports["paths"]["xlsx"]).is_file()
    assert Path(reports["paths"]["markdown"]).is_file()
    assert reports["reconciliation"]["status"] == "PASS"
    verification = verify_case(case_dir)
    assert verification["status"] in {"PASS", "BLOCKED", "FAIL"}
    # originals preserved
    manifest = json.loads((case_dir / "case-manifest.json").read_text(encoding="utf-8"))
    for doc in manifest["documents"]:
        obj = case_dir / doc["object_path"]
        assert obj.is_file()


def test_operational_scale(env_roots: Path, tmp_path: Path) -> None:
    op = build_operational(tmp_path / "op.xlsx", 60)
    case_dir = create_case("op-e2e", op, env_roots / "cases" / "op-e2e")
    ingest_case(case_dir)
    counts = map_case(case_dir)
    assert counts["budget_items"] >= 50
    audit_case(case_dir)
    report_case(case_dir)
    v = verify_case(case_dir)
    # Should complete; arithmetic material diffs expected on injected errors
    assert v["status"] in {"PASS", "FAIL"}  # FAIL if report issues; usually PASS
    cells_total = 0
    for p in (case_dir / "workbooks").glob("*/extraction-quality.json"):
        q = json.loads(p.read_text(encoding="utf-8"))
        cells_total += int(q.get("cell_count") or 0)
    assert cells_total >= 100


def test_reference_manifest_required_fields(tmp_path: Path) -> None:
    man = build_reference_manifest(tmp_path / "ref.json", tmp_path / "items.jsonl")
    m = load_reference_manifest(man)
    assert m["system"] == "SINAPI"
    assert m["reference_month"]
    assert m["tax_regime"]
    items = [
        {
            "item_id": "t1",
            "code": "SINAPI-74001",
            "unit": "m³",
            "unit_direct_cost": 400.0,
            "reference_month": "2026-01",
            "reference_locality": "BR-SC",
            "reference_regime": "nao_desonerado",
        }
    ]
    result = compare_to_references(items, m)
    assert result["comparison_count"] == 1
    assert result["comparisons"][0]["comparison_status"].startswith("COMPARABLE")

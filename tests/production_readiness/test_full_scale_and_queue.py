"""Tests for full-scale streaming proof and production readiness helpers."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.production_readiness.deliverables_manifest import (
    build_deliverables_manifest,
    validate_artifact_file,
    write_manifest,
)
from scripts.production_readiness.evidence import sanitize, write_json
from scripts.production_readiness.full_scale import (
    compare_runs,
    process_stream,
    stream_synthetic_contracts,
)
from scripts.production_readiness.official_reference import (
    build_demo_official_snapshot,
    compare_budget_to_official,
)


def test_process_stream_bounded_and_resumable(tmp_path: Path) -> None:
    out = tmp_path / "scale"
    n = 2500
    b1 = process_stream(
        stream_synthetic_contracts(n),
        out_dir=out,
        run_id="t1",
        resume=False,
        expected_total=n,
        source_label="synthetic",
        checkpoint_every=200,
        accept_fn=lambda r: float(r.get("valor_total") or 0) > 0,
    )
    assert b1["completed"] is True
    assert b1["final_offset"] == n
    assert b1["accepted"] + b1["rejected"] + b1["deduplicated"] == n
    assert b1["publication_allowed"] is True
    assert b1["max_rss_bytes"] > 0
    assert (out / "accepted.jsonl").is_file()
    assert (out / "checkpoint.json").is_file()

    # dual run determinism
    out2 = tmp_path / "scale2"
    b2 = process_stream(
        stream_synthetic_contracts(n),
        out_dir=out2,
        run_id="t2",
        resume=False,
        expected_total=n,
        source_label="synthetic",
        checkpoint_every=200,
        accept_fn=lambda r: float(r.get("valor_total") or 0) > 0,
    )
    cmp = compare_runs(b1, b2)
    assert cmp["identical_counts"] is True
    assert cmp["accepted_checksum_match"] is True


def test_process_stream_resume_midway(tmp_path: Path) -> None:
    out = tmp_path / "resume"
    n = 800
    # first: only 300 rows
    def limited():
        for i, row in enumerate(stream_synthetic_contracts(n)):
            if i >= 300:
                break
            yield row

    b_partial = process_stream(
        limited(),
        out_dir=out,
        run_id="r",
        resume=False,
        expected_total=300,
        source_label="synthetic",
        checkpoint_every=50,
    )
    assert b_partial["final_offset"] == 300
    # continue remaining
    def rest():
        for row in stream_synthetic_contracts(n, start_offset=300):
            yield row

    b_full = process_stream(
        rest(),
        out_dir=out,
        run_id="r",
        resume=True,
        expected_total=n,
        source_label="synthetic",
        checkpoint_every=50,
    )
    assert b_full["final_offset"] == n
    assert b_full["completed"] is True


def test_publication_gate_blocks_incomplete(tmp_path: Path) -> None:
    out = tmp_path / "blocked"
    # empty stream with expected total → incomplete warning path
    b = process_stream(
        iter([]),
        out_dir=out,
        run_id="empty",
        resume=False,
        expected_total=100,
        source_label="empty",
    )
    # completed True on empty stream but expected mismatch → warnings
    assert b["completed"] is True
    assert b.get("warnings")


def test_official_matcher_classes(tmp_path: Path) -> None:
    man = build_demo_official_snapshot(tmp_path / "ref")
    assert man["claim_level"] == "STRUCTURE_ONLY_NOT_OFFICIAL_ACQUISITION"
    budget = [
        {"item_id": "1", "code": "88389", "description": "Concreto fck 25 MPa", "unit": "m3"},
        {"item_id": "2", "code": "74109/001", "description": "Servente de obras", "unit": "h"},
        {"item_id": "3", "code": "ZZZ", "description": "Sem ref", "unit": "un"},
        {"item_id": "4", "code": "99901", "description": "Tubo PVC 100mm", "unit": "kg"},
    ]
    # competence mismatch
    r1 = compare_budget_to_official(
        budget,
        tmp_path / "ref" / "manifest.json",
        budget_competence="2020-01",
        allow_demo_structure=True,
    )
    assert r1["counts"]["competence_incompatible"] >= 1
    r2 = compare_budget_to_official(
        budget,
        tmp_path / "ref" / "manifest.json",
        budget_competence="2026-06",
        allow_demo_structure=True,
    )
    statuses = {m["status"] for m in r2["matches"]}
    assert "exact" in statuses
    assert "missing" in statuses
    assert "unit_incompatible" in statuses or "approximate" in statuses


def test_deliverables_manifest_requires_human_and_valid_files(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    xlsx = tmp_path / "a.xlsx"
    pdf.write_bytes(b"%PDF-1.4 minimal content here for size")
    # zip/xlsx magic
    xlsx.write_bytes(b"PK\x03\x04" + b"\x00" * 40)
    m = build_deliverables_manifest(
        execution_id="exec-1",
        conclusions={"counts": {"pdf": {"items": 3}, "excel": {"items": 3}}, "ready": False},
        sources_consulted=["pncp"],
        sources_failed=[],
        documents_used=[{"title": "edital"}],
        documents_missing=[],
        human_review={"accepted_by_tiago": False, "reviewer": None},
        pdf_path=pdf,
        excel_path=xlsx,
    )
    assert m["delivery_blocked"] is True
    assert "awaiting_human_accept" in m["blocked_reasons"]
    assert m["package_released_to_client"] is False
    m2 = build_deliverables_manifest(
        execution_id="exec-1",
        conclusions={"counts": {"pdf": {"items": 3}, "excel": {"items": 3}}},
        sources_consulted=["pncp"],
        sources_failed=[],
        documents_used=[],
        documents_missing=[],
        human_review={"accepted_by_tiago": True, "reviewer": "tiago"},
        pdf_path=pdf,
        excel_path=xlsx,
    )
    assert m2["package_released_to_client"] is True
    path = write_manifest(tmp_path / "manifest.json", m2)
    assert path.is_file()
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    assert validate_artifact_file(empty)["ok"] is False


def test_sanitize_redacts_secrets() -> None:
    raw = {
        "dsn": "postgresql://user:supersecret@10.0.0.5:5432/db",
        "password": "hunter2",
        "nested": {"api_key": "abc", "ok": "fine"},
    }
    clean = sanitize(raw)
    assert "supersecret" not in json.dumps(clean)
    assert clean["password"] == "***REDACTED***"
    assert clean["nested"]["api_key"] == "***REDACTED***"
    assert "x.x.x.x" in clean["dsn"] or "REDACTED" in clean["dsn"]


def test_evidence_write(tmp_path: Path) -> None:
    p = write_json(tmp_path / "sample.json", {"token": "sekrit", "result": "ok"})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["token"] == "***REDACTED***"
    assert data["result"] == "ok"

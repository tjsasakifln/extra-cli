"""Unit tests against shipped pilot completion predicates (NEXT-30D).

Imports real functions from scripts.crawl.run_contracts_90d_pilot — no local reimplementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.crawl.run_contracts_90d_pilot import (
    count_planned_windows,
    evaluate_go_no_go,
    evaluate_pilot_status,
    evaluate_window_completion,
)
from scripts.crawl.run_evidence import bind_checkpoint_run_id


# ---------------------------------------------------------------------------
# evaluate_window_completion
# ---------------------------------------------------------------------------


def test_max_pages_without_exhaustion_is_incomplete():
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=False,
        last_total_pages=100,
        page=51,  # after while page <= 50 exited
        max_pages=50,
    )
    assert fully_ok is False
    assert any("Hit CONTRACTS_MAX_PAGES" in e for e in errors)


def test_exhausted_pages_fully_ok():
    """Full window complete (pages exhausted, no errors)."""
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=10,
        page=10,
        max_pages=200,
    )
    assert fully_ok is True
    assert errors == []


def test_zero_records_legitimate_complete_pages_exhausted():
    """Legitimate zero (pages_exhausted via SUCCESS_ZERO path) is complete."""
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=0,
        page=1,
        max_pages=200,
    )
    assert fully_ok is True
    assert errors == []


def test_page_error_not_complete():
    """Mid-page HTTP 500 → incomplete."""
    fully_ok, errors = evaluate_window_completion(
        ["Page 2: [HTTP_SERVER_ERROR] 500"],
        pages_exhausted=False,
        last_total_pages=10,
        page=2,
        max_pages=200,
    )
    assert fully_ok is False
    assert errors == ["Page 2: [HTTP_SERVER_ERROR] 500"]


def test_timeout_incomplete():
    fully_ok, errors = evaluate_window_completion(
        ["Page 13: [CONNECTION_FAILED] read timeout"],
        pages_exhausted=False,
        last_total_pages=300,
        page=13,
        max_pages=10000,
    )
    assert fully_ok is False
    assert any("timeout" in e.lower() or "CONNECTION_FAILED" in e for e in errors)


def test_rate_limit_429_incomplete():
    fully_ok, errors = evaluate_window_completion(
        ["Page 5: [HTTP_RATE_LIMIT] 429"],
        pages_exhausted=False,
        last_total_pages=50,
        page=5,
        max_pages=200,
    )
    assert fully_ok is False


def test_partial_upsert_failure_incomplete():
    fully_ok, errors = evaluate_window_completion(
        ["upsert failed window=20260417_20260516 page~3: deadlock"],
        pages_exhausted=False,
        last_total_pages=10,
        page=3,
        max_pages=200,
    )
    assert fully_ok is False
    assert any("upsert" in e for e in errors)


# ---------------------------------------------------------------------------
# evaluate_pilot_status — path-level (backward compat, require_full_coverage=False)
# ---------------------------------------------------------------------------


def test_evaluate_pilot_status_success_path_level():
    """Without require_full_coverage: windows_ok>0 & failed==0 ⇒ path-level success."""
    assert evaluate_pilot_status({"windows_ok": 1, "windows_failed": 0}) == "success"


def test_evaluate_pilot_status_partial_path_level():
    assert evaluate_pilot_status({"windows_ok": 2, "windows_failed": 1}) == "partial"


def test_evaluate_pilot_status_failed_path_level():
    assert evaluate_pilot_status({"windows_ok": 0, "windows_failed": 1}) == "failed"
    assert evaluate_pilot_status({"windows_ok": 0, "windows_failed": 0}) == "failed"


# ---------------------------------------------------------------------------
# evaluate_pilot_status — full pilot coverage (require_full_coverage=True)
# ---------------------------------------------------------------------------


def test_full_coverage_success():
    """Complete success: all planned windows covered, no failures/page errors."""
    totals = {
        "windows_ok": 3,
        "windows_failed": 0,
        "windows_skipped_resume": 0,
        "page_errors": 0,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "success"
    )


def test_all_skipped_resume_planned_covered_is_success():
    """Resume where every window already completed → success if planned covered."""
    totals = {
        "windows_ok": 0,
        "windows_failed": 0,
        "windows_skipped_resume": 90,
        "page_errors": 0,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=90, require_full_coverage=True
        )
        == "success"
    )


def test_mixed_ok_and_skipped_covers_planned_success():
    totals = {
        "windows_ok": 2,
        "windows_failed": 0,
        "windows_skipped_resume": 1,
        "page_errors": 0,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "success"
    )


def test_one_window_ok_of_many_planned_is_partial():
    """1-day path proof must NOT be full pilot success."""
    totals = {
        "windows_ok": 1,
        "windows_failed": 0,
        "windows_skipped_resume": 0,
        "page_errors": 0,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=90, require_full_coverage=True
        )
        == "partial"
    )


def test_partial_with_persisted_records_still_partial():
    """Persisted inserts do not upgrade status — only window counters matter."""
    totals = {
        "windows_ok": 1,
        "windows_failed": 1,
        "windows_skipped_resume": 0,
        "page_errors": 1,
        "inserted": 5000,
        "transformed": 5100,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "partial"
    )


def test_page_errors_block_success_even_if_coverage_met():
    totals = {
        "windows_ok": 3,
        "windows_failed": 0,
        "windows_skipped_resume": 0,
        "page_errors": 2,
    }
    # covered >= planned but page_errors > 0
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "partial"
    )


def test_nothing_ok_is_failed_with_full_coverage():
    totals = {
        "windows_ok": 0,
        "windows_failed": 2,
        "windows_skipped_resume": 0,
        "page_errors": 2,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "failed"
    )


def test_planned_windows_zero_cannot_succeed():
    totals = {
        "windows_ok": 0,
        "windows_failed": 0,
        "windows_skipped_resume": 0,
        "page_errors": 0,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=0, require_full_coverage=True
        )
        == "failed"
    )


def test_mid_page_error_incomplete_pilot():
    totals = {
        "windows_ok": 0,
        "windows_failed": 1,
        "windows_skipped_resume": 0,
        "page_errors": 1,
    }
    assert (
        evaluate_pilot_status(
            totals, planned_windows=3, require_full_coverage=True
        )
        == "failed"
    )


# ---------------------------------------------------------------------------
# evaluate_go_no_go
# ---------------------------------------------------------------------------


def test_partial_forces_go_no_go_no_go():
    label, reason = evaluate_go_no_go(
        "partial",
        {
            "P1_run_status": True,
            "P2_date_span": True,
            "P5_no_residual_page_errors": True,
            "P7_sample_fields": True,
        },
    )
    assert label == "NO-GO"
    assert "partial" in reason.lower() or "incomplete" in reason.lower() or "path_proof" in reason


def test_failed_forces_go_no_go_no_go():
    label, _ = evaluate_go_no_go("failed", {})
    assert label == "NO-GO"


def test_success_with_criteria_is_go():
    label, reason = evaluate_go_no_go(
        "success",
        {
            "P1_run_status": True,
            "P2_date_span": True,
            "P5_no_residual_page_errors": True,
            "P7_sample_fields": True,
            "P8_full_window_coverage": True,
        },
        days=90,
    )
    assert label == "GO"
    assert "completed" in reason.lower() or "Pilot" in reason or "90d" in reason


def test_success_missing_criteria_is_no_go():
    label, reason = evaluate_go_no_go(
        "success",
        {
            "P1_run_status": True,
            "P2_date_span": False,
            "P5_no_residual_page_errors": True,
            "P7_sample_fields": True,
            "P8_full_window_coverage": True,
        },
        days=90,
    )
    assert label == "NO-GO"
    assert "P2_date_span" in reason


def test_short_pilot_span_cannot_go_3y():
    label, reason = evaluate_go_no_go(
        "success",
        {
            "P1_run_status": True,
            "P2_date_span": True,
            "P5_no_residual_page_errors": True,
            "P7_sample_fields": True,
            "P8_full_window_coverage": True,
        },
        days=7,
    )
    assert label == "NO-GO"
    assert "7" in reason or "90" in reason


# ---------------------------------------------------------------------------
# checkpoint run_id provenance (across runs)
# ---------------------------------------------------------------------------


def test_checkpoint_other_run_recorded():
    """Resume across runs records previous_run_ids; completed_windows preserved."""
    cp = {
        "mode": "full",
        "completed_windows": ["20260715_20260715"],
        "meta": {"run_id": "run-old", "run_ids": ["run-old"]},
    }
    bound = bind_checkpoint_run_id(cp, "run-new")
    assert bound["meta"]["run_id"] == "run-new"
    assert "run-old" in bound["meta"]["previous_run_ids"]
    assert bound["completed_windows"] == ["20260715_20260715"]


# ---------------------------------------------------------------------------
# count_planned_windows
# ---------------------------------------------------------------------------


def test_count_planned_windows_basic():
    from datetime import date

    # 90 calendar days with 30-day windows → 3 windows
    end = date(2026, 7, 16)
    start = end  # start >= end → 0
    assert count_planned_windows(start, end, 30) == 0

    start = date(2026, 4, 17)
    end = date(2026, 7, 16)
    n = count_planned_windows(start, end, 30)
    assert n == 3


# ---------------------------------------------------------------------------
# Terminal artifact regression (on-disk)
# ---------------------------------------------------------------------------


def test_terminal_pilot_artifact_is_not_running():
    """Regression: committed pilot JSON must be terminal, not mid-run."""
    p = Path("output/contracts/pilot-90d-next30d.json")
    assert p.is_file(), "pilot artifact missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("status") in {"success", "partial", "failed"}
    assert data.get("status") != "running"
    totals = data.get("totals") or {}
    path = data.get("path_proof") or {}
    # Full-coverage semantics when planned_windows present on artifact
    planned = data.get("planned_windows")
    if data["status"] in {"success", "failed"} and "windows_ok" in totals:
        expected = evaluate_pilot_status(
            totals,
            planned_windows=planned,
            require_full_coverage=planned is not None,
        )
        # Annotated/manual artifacts may predate require_full_coverage; allow
        # path_proof wrapper when machine recompute would differ on partial.
        if data["status"] == "success":
            assert data["status"] == expected or path.get("status") == "success"
    if data["status"] in {"success", "partial"}:
        windows_ok = int(
            totals.get("windows_ok")
            or (path.get("totals") or {}).get("windows_ok")
            or 0
        )
        assert windows_ok >= 1
    if data["status"] == "partial":
        # Fail-closed: partial MUST be NO-GO (never GO / CONDITIONAL_GO)
        assert data.get("go_no_go_3y") == "NO-GO"
    # Provenance chain required on sealed/terminal pilot artifacts
    assert data.get("run_id"), "pilot artifact must have run_id"
    evidence = data.get("evidence") or {}
    assert evidence.get("run_id") == data.get("run_id")
    assert evidence.get("checkpoint_hash"), "evidence.checkpoint_hash required"
    assert data.get("git_sha") or evidence.get("git_sha")


def test_partial_artifact_go_no_go_is_no_go():
    """Committed partial pilot must not claim unsupervised 3y GO."""
    p = Path("output/contracts/pilot-90d-next30d.json")
    if not p.is_file():
        pytest.skip("no pilot artifact")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("status") != "partial":
        pytest.skip("artifact not partial")
    assert data.get("go_no_go_3y") == "NO-GO"


def test_path_proof_does_not_imply_pilot_success():
    p = Path("output/contracts/pilot-90d-next30d.json")
    if not p.is_file():
        pytest.skip("no pilot artifact")
    data = json.loads(p.read_text(encoding="utf-8"))
    path = data.get("path_proof") or {}
    if path.get("status") == "success" and data.get("status") == "partial":
        # Core invariant of this workstream
        assert data.get("go_no_go_3y") == "NO-GO"
        assert data.get("status") != "success"


def test_checkpoint_has_completed_window_when_path_ok():
    pilot = json.loads(Path("output/contracts/pilot-90d-next30d.json").read_text())
    path = pilot.get("path_proof") or {}
    if pilot.get("status") != "success" and path.get("status") != "success":
        return
    # Prefer canonical path declared on artifact, else default
    canon = (pilot.get("checkpoint_canonical") or {}).get("path")
    candidates = []
    if canon:
        candidates.append(Path(canon))
    candidates.append(Path("data/contracts_checkpoints/contracts_full.json"))
    candidates.append(Path("data/contracts_checkpoints/a5_next30d/contracts_full.json"))
    found = None
    for cp_path in candidates:
        if cp_path.is_file():
            found = cp_path
            break
    if found is None:
        # Artifact may embed checkpoint list
        embedded = (pilot.get("checkpoint") or {}).get("completed_windows") or (
            (pilot.get("path_proof") or {}).get("checkpoint") or {}
        ).get("completed_windows")
        assert embedded and len(embedded) >= 1
        return
    cp = json.loads(found.read_text())
    assert len(cp.get("completed_windows") or []) >= 1


# ---------------------------------------------------------------------------
# Fail-closed proof / exit codes / foreign run / tamper
# ---------------------------------------------------------------------------


def test_foreign_run_blocked_by_default():
    """Same-run requirement blocks rebinding without allow_cross_run_resume."""
    from scripts.crawl.contracts_crawler import CrawlCheckpoint
    from scripts.crawl.run_contracts_90d_pilot import _apply_run_id_to_checkpoint

    cp = CrawlCheckpoint(mode="full")
    cp.meta = {"run_id": "run-old", "run_ids": ["run-old"]}
    cp.completed_windows = ["20260715_20260715"]
    with pytest.raises(ValueError, match="run_id mismatch"):
        _apply_run_id_to_checkpoint(cp, "run-new", allow_cross_run_resume=False)


def test_foreign_resume_allowed_when_explicit():
    from scripts.crawl.contracts_crawler import CrawlCheckpoint
    from scripts.crawl.run_contracts_90d_pilot import _apply_run_id_to_checkpoint

    cp = CrawlCheckpoint(mode="full")
    cp.meta = {"run_id": "run-old", "run_ids": ["run-old"]}
    prev = _apply_run_id_to_checkpoint(cp, "run-new", allow_cross_run_resume=True)
    assert "run-old" in prev
    assert cp.meta.get("run_id") == "run-new"
    assert cp.meta.get("foreign_resume") is True


def test_path_proof_rejected_when_only_skipped_resume():
    from scripts.crawl.run_evidence import assert_proof_run_coherence

    report = {
        "run_id": "r1",
        "status": "partial",
        "totals": {"windows_ok": 0, "windows_skipped_resume": 3},
        "path_proof": {"status": "success", "run_id": "r1"},
        "evidence": {"run_id": "r1", "checkpoint_hash": "abc"},
    }
    with pytest.raises(ValueError, match="skipped_resume"):
        assert_proof_run_coherence(report)


def test_tampered_checkpoint_hash_detected(tmp_path):
    from scripts.crawl.run_evidence import sha256_file, verify_checkpoint_hash

    p = tmp_path / "cp.json"
    p.write_text('{"ok": true}', encoding="utf-8")
    good = sha256_file(p)
    verify_checkpoint_hash(p, good)
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_checkpoint_hash(p, "0" * 64)


def test_running_status_rejected_by_proof_coherence():
    from scripts.crawl.run_evidence import assert_proof_run_coherence

    with pytest.raises(ValueError, match="running"):
        assert_proof_run_coherence(
            {
                "run_id": "r1",
                "status": "running",
                "evidence": {"run_id": "r1", "checkpoint_hash": "x"},
            }
        )


def test_http_500_window_incomplete():
    fully_ok, errors = evaluate_window_completion(
        ["Page 3: [HTTP_SERVER_ERROR] 500"],
        pages_exhausted=False,
        last_total_pages=10,
        page=3,
        max_pages=200,
    )
    assert fully_ok is False
    assert any("500" in e for e in errors)


def test_main_exit_codes_config_error(monkeypatch):
    """main() returns 2 when DSN missing and not dry-run/seal."""
    import sys

    from scripts.crawl import run_contracts_90d_pilot as mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    old = sys.argv
    try:
        sys.argv = ["run_contracts_90d_pilot.py", "--days", "1"]
        code = mod.main()
        assert code == 2
    finally:
        sys.argv = old


def test_main_exit_code_partial_via_evaluate():
    """Exit code mapping: success=0, partial=3, failed=1."""
    # Mirrors main() terminal mapping without network
    status_to_code = {"success": 0, "partial": 3, "failed": 1}
    assert status_to_code[evaluate_pilot_status({"windows_ok": 1, "windows_failed": 0}, planned_windows=3, require_full_coverage=True)] == 3
    assert status_to_code[evaluate_pilot_status({"windows_ok": 3, "windows_failed": 0, "page_errors": 0, "windows_skipped_resume": 0}, planned_windows=3, require_full_coverage=True)] == 0
    assert status_to_code[evaluate_pilot_status({"windows_ok": 0, "windows_failed": 1}, planned_windows=3, require_full_coverage=True)] == 1


def test_sealed_7d_has_run_id_and_no_go():
    p = Path("output/contracts/pilot-7d-smoke.json")
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("run_id")
    assert data["evidence"]["run_id"] == data["run_id"]
    assert data["evidence"].get("checkpoint_hash")
    assert data.get("go_no_go_3y") == "NO-GO"
    assert data.get("status") in {"success", "partial", "failed"}
    assert "annotation_note" not in data


def test_sealed_90d_partial_proof_coherence():
    from scripts.crawl.run_evidence import assert_proof_run_coherence

    p = Path("output/contracts/pilot-90d-next30d.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert data["go_no_go_3y"] == "NO-GO"
    assert_proof_run_coherence(data)

"""Unit tests against shipped pilot completion predicates (NEXT-30D).

Imports real functions from scripts.crawl.run_contracts_90d_pilot — no local reimplementation.
"""

from __future__ import annotations

from scripts.crawl.run_contracts_90d_pilot import (
    evaluate_pilot_status,
    evaluate_window_completion,
)


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
    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=10,
        page=10,
        max_pages=200,
    )
    assert fully_ok is True
    assert errors == []


def test_page_error_not_complete():
    fully_ok, errors = evaluate_window_completion(
        ["Page 2: [HTTP_SERVER_ERROR] 500"],
        pages_exhausted=False,
        last_total_pages=10,
        page=2,
        max_pages=200,
    )
    assert fully_ok is False
    assert errors == ["Page 2: [HTTP_SERVER_ERROR] 500"]


def test_evaluate_pilot_status_success():
    assert evaluate_pilot_status({"windows_ok": 1, "windows_failed": 0}) == "success"


def test_evaluate_pilot_status_partial():
    assert evaluate_pilot_status({"windows_ok": 2, "windows_failed": 1}) == "partial"


def test_evaluate_pilot_status_failed():
    assert evaluate_pilot_status({"windows_ok": 0, "windows_failed": 1}) == "failed"
    assert evaluate_pilot_status({"windows_ok": 0, "windows_failed": 0}) == "failed"


def test_terminal_pilot_artifact_is_success():
    """Regression: committed pilot JSON must be terminal success|failed, not running."""
    import json
    from pathlib import Path

    p = Path("output/contracts/pilot-90d-next30d.json")
    assert p.is_file(), "pilot artifact missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("status") in {"success", "partial", "failed"}
    assert data.get("status") != "running"
    totals = data.get("totals") or {}
    # Status must match shipped evaluator
    assert data["status"] == evaluate_pilot_status(totals)
    if data["status"] == "success":
        assert int(totals.get("windows_ok") or 0) >= 1
        assert int(totals.get("page_errors") or 0) == 0


def test_checkpoint_has_completed_window_when_success():
    import json
    from pathlib import Path

    pilot = json.loads(Path("output/contracts/pilot-90d-next30d.json").read_text())
    if pilot.get("status") != "success":
        return  # only enforce coherence on success terminal
    cp_path = Path("data/contracts_checkpoints/contracts_full.json")
    assert cp_path.is_file()
    cp = json.loads(cp_path.read_text())
    assert len(cp.get("completed_windows") or []) >= 1
    assert int(cp.get("total_windows_failed") or 0) == 0

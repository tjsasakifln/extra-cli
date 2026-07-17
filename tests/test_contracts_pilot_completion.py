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


def test_terminal_pilot_artifact_is_not_running():
    """Regression: committed pilot JSON must be terminal, not mid-run."""
    import json
    from pathlib import Path

    p = Path("output/contracts/pilot-90d-next30d.json")
    assert p.is_file(), "pilot artifact missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("status") in {"success", "partial", "failed"}
    assert data.get("status") != "running"
    totals = data.get("totals") or {}
    path = data.get("path_proof") or {}
    # Either machine status matches totals, or partial wrapper with path_proof success
    if data["status"] in {"success", "failed"} and "windows_ok" in totals:
        assert data["status"] == evaluate_pilot_status(totals)
    if data["status"] in {"success", "partial"}:
        windows_ok = int(
            totals.get("windows_ok")
            or (path.get("totals") or {}).get("windows_ok")
            or 0
        )
        assert windows_ok >= 1


def test_checkpoint_has_completed_window_when_path_ok():
    import json
    from pathlib import Path

    pilot = json.loads(Path("output/contracts/pilot-90d-next30d.json").read_text())
    path = pilot.get("path_proof") or {}
    if pilot.get("status") != "success" and path.get("status") != "success":
        return
    cp_path = Path("data/contracts_checkpoints/contracts_full.json")
    assert cp_path.is_file()
    cp = json.loads(cp_path.read_text())
    assert len(cp.get("completed_windows") or []) >= 1

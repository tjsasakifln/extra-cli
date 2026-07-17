"""Regression: NEXT-30D committed evidence files must match gate claims.

Reads real on-disk artifacts — no hard-coded success injection.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sc_compras_runtime_evidence_is_success():
    p = ROOT / "output" / "sc_compras" / "runtime-next30d.json"
    assert p.is_file(), "sc_compras evidence missing"
    data = json.loads(p.read_text(encoding="utf-8"))
    results = data.get("results") or []
    assert results, "empty results"
    r0 = results[0]
    assert r0.get("source") == "sc_compras"
    assert r0.get("status") == "success", (
        f"GATE-B claims success ingest; on-disk status={r0.get('status')!r} "
        f"error={str(r0.get('error_message') or '')[:200]}"
    )
    assert int(r0.get("fetched") or 0) >= 1
    assert int(r0.get("inserted") or 0) >= 1
    summary = data.get("summary") or {}
    assert int(summary.get("sources_failed") or 0) == 0
    assert int(summary.get("sources_success") or 0) >= 1


def test_contracts_pilot_terminal_not_running():
    p = ROOT / "output" / "contracts" / "pilot-90d-next30d.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("status") in {"success", "partial", "failed"}
    assert data.get("status") != "running"
    totals = data.get("totals") or {}
    path = data.get("path_proof") or {}
    path_totals = path.get("totals") or {}
    if data.get("status") in {"success", "partial"}:
        windows_ok = int(
            totals.get("windows_ok") or path_totals.get("windows_ok") or 0
        )
        assert windows_ok >= 1, "partial/success pilot must document windows_ok>=1"
    if data.get("status") == "partial":
        assert data.get("go_no_go_3y") in {"NO-GO", "CONDITIONAL_GO", "GO"}


def test_checkpoint_completed_when_path_proof_success():
    pilot = json.loads(
        (ROOT / "output" / "contracts" / "pilot-90d-next30d.json").read_text()
    )
    path = pilot.get("path_proof") or {}
    needs_cp = pilot.get("status") == "success" or path.get("status") == "success"
    if not needs_cp:
        return
    cp = json.loads(
        (ROOT / "data" / "contracts_checkpoints" / "contracts_full.json").read_text()
    )
    assert len(cp.get("completed_windows") or []) >= 1

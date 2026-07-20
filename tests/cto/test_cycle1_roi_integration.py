"""Cycle-1 real ROI binding (PR #50 material advance)."""
from __future__ import annotations

from scripts.cto.cycle1_roi_integration import run_cycle1_real


def test_cycle1_accept_top_binds_ranking(cto_repo, monkeypatch):
    # Provide fake squad responses via monkeypatch of aiox_bridge helpers
    from scripts.cto import cycle1_roi_integration as m

    def fake_status(root=None):
        return {
            "exit_code": 0,
            "json": {
                "cycle": {"selected_id": "cand-dyn-slice:test123"},
                "latest_ranking": {
                    "selected_id": "cand-dyn-slice:test123",
                    "top": [{"id": "cand-dyn-slice:test123", "roi": 2.9}],
                },
            },
            "stdout_tail": "",
        }

    def fake_rank(root=None):
        return {
            "exit_code": 0,
            "json": None,
            "stdout_tail": "### 1. cand-dyn-slice:test123  ROI=2.9\n",
        }

    def fake_audit(root=None):
        return {"exit_code": 0, "stdout_tail": ""}

    monkeypatch.setattr(m, "squad_status", fake_status)
    monkeypatch.setattr(m, "squad_rank_next", fake_rank)
    monkeypatch.setattr(m, "squad_audit_dod_summary", fake_audit)
    monkeypatch.setattr(
        m,
        "preflight_for_cycle",
        lambda root=None, require_grok=False: {"ok": True, "inspect": {}},
    )

    out = run_cycle1_real(root=cto_repo, cycle_id="cyc1-test-unit", dry_run=True, require_grok=False)
    assert out["ok"] is True
    assert out["strategic"]["action"] == "ACCEPT_TOP"
    assert out["strategic"]["selected_id"] == "cand-dyn-slice:test123"
    assert (cto_repo / "docs" / "ops" / "cto-autopilot" / "cycles" / "cyc1-test-unit-roi-binding.json").is_file()

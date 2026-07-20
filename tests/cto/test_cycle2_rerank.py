"""Cycle-2 must not use exclude-list; requires cycle-1 Done then natural ranking[0]."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.cto.cycle2_rerank_integration import (
    prove_cycle1_complete,
    run_cycle2_real,
)


def test_prove_cycle1_incomplete_when_draft(tmp_path: Path):
    stories = tmp_path / ".aiox" / "state" / "stories"
    stories.mkdir(parents=True)
    sid = "ROI-cand-dyn-slice-cb906bb58392"
    (stories / f"{sid}.json").write_text(
        json.dumps(
            {
                "story_id": sid,
                "status": "Draft",
                "po_closed": False,
                "qa_verdict": "PENDING",
            }
        ),
        encoding="utf-8",
    )
    r = prove_cycle1_complete(tmp_path)
    assert r["ok"] is False
    assert r["blocked_reason"] == "BLOCKED_HUMAN"


def test_cycle2_blocked_without_cycle1_done(cto_repo, monkeypatch):
    from scripts.cto import cycle2_rerank_integration as m

    monkeypatch.setattr(
        m,
        "preflight_for_cycle",
        lambda root=None, require_grok=False: {"ok": True},
    )
    # Even if rank-next would offer a second cand, cycle2 must stop first
    monkeypatch.setattr(
        m,
        "squad_rank_next",
        lambda root=None: {
            "exit_code": 0,
            "stdout_text": (
                "### 1. cand-dyn-slice:cb906bb58392  ROI=2.9241\n"
                "### 2. cand-dyn-slice:b84aad7b10ee  ROI=2.9241\n"
            ),
        },
    )
    monkeypatch.setattr(m, "squad_status", lambda root=None: {"exit_code": 0, "json": {}})
    monkeypatch.setattr(m, "squad_audit_dod_summary", lambda root=None: {"exit_code": 0})

    out = run_cycle2_real(
        root=cto_repo,
        cycle_id="cyc2-unit-blocked",
        cycle1_selected_id="cand-dyn-slice:cb906bb58392",
        dry_run=True,
    )
    assert out["ok"] is False
    assert out["status"] == "BLOCKED_HUMAN"
    assert out.get("exclude_list_used") is False
    assert "excluded_work_ids" not in out or not out.get("excluded_work_ids")


def test_cycle2_accepts_natural_ranking0_after_cycle1_done(cto_repo, monkeypatch):
    from scripts.cto import cycle2_rerank_integration as m

    # Plant cycle-1 Done evidence in the temp repo
    stories = Path(cto_repo) / ".aiox" / "state" / "stories"
    stories.mkdir(parents=True, exist_ok=True)
    sid = "ROI-cand-dyn-slice-cb906bb58392"
    (stories / f"{sid}.json").write_text(
        json.dumps(
            {
                "story_id": sid,
                "status": "Done",
                "po_closed": True,
                "po_validated": True,
                "qa_verdict": "PASS",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        m,
        "preflight_for_cycle",
        lambda root=None, require_grok=False: {"ok": True},
    )
    # After cycle-1 done, ranker surfaces a *new* ranking[0]
    monkeypatch.setattr(
        m,
        "squad_rank_next",
        lambda root=None: {
            "exit_code": 0,
            "stdout_text": (
                "### 1. cand-dyn-slice:b84aad7b10ee  ROI=2.9241\n"
                "### 2. cand-dyn-slice:a94b7d79e0a0  ROI=2.78\n"
            ),
        },
    )
    monkeypatch.setattr(m, "squad_status", lambda root=None: {"exit_code": 0, "json": {}})
    monkeypatch.setattr(m, "squad_audit_dod_summary", lambda root=None: {"exit_code": 0})

    out = run_cycle2_real(
        root=cto_repo,
        cycle_id="cyc2-unit-ok",
        cycle1_selected_id="cand-dyn-slice:cb906bb58392",
        dry_run=True,
    )
    assert out["ok"] is True
    assert out["exclude_list_used"] is False
    assert out["chosen"]["id"] == "cand-dyn-slice:b84aad7b10ee"
    assert out["natural_ranking_0"] == "cand-dyn-slice:b84aad7b10ee"
    assert out["strategic"]["action"] == "ACCEPT_TOP"


def test_cycle2_blocks_if_ranking0_still_cycle1(cto_repo, monkeypatch):
    from scripts.cto import cycle2_rerank_integration as m

    stories = Path(cto_repo) / ".aiox" / "state" / "stories"
    stories.mkdir(parents=True, exist_ok=True)
    sid = "ROI-cand-dyn-slice-cb906bb58392"
    (stories / f"{sid}.json").write_text(
        json.dumps(
            {
                "story_id": sid,
                "status": "Done",
                "po_closed": True,
                "qa_verdict": "PASS",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        m, "preflight_for_cycle", lambda root=None, require_grok=False: {"ok": True}
    )
    # Ranker still shows old ranking[0] — must not skip to [1]
    monkeypatch.setattr(
        m,
        "squad_rank_next",
        lambda root=None: {
            "exit_code": 0,
            "stdout_text": (
                "### 1. cand-dyn-slice:cb906bb58392  ROI=2.9241\n"
                "### 2. cand-dyn-slice:b84aad7b10ee  ROI=2.9\n"
            ),
        },
    )
    monkeypatch.setattr(m, "squad_status", lambda root=None: {"exit_code": 0, "json": {}})
    monkeypatch.setattr(m, "squad_audit_dod_summary", lambda root=None: {"exit_code": 0})

    out = run_cycle2_real(
        root=cto_repo,
        cycle_id="cyc2-unit-still-r0",
        cycle1_selected_id="cand-dyn-slice:cb906bb58392",
        dry_run=True,
    )
    assert out["ok"] is False
    assert out["status"] == "BLOCKED_HUMAN"
    assert out["chosen"]["id"] == "cand-dyn-slice:cb906bb58392"

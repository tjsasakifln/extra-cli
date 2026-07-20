from scripts.cto.cycle2_rerank_integration import run_cycle2_real, select_after_rerank


def test_select_skips_excluded():
    top = [
        {"rank": 1, "id": "cand-dyn-slice:cb906bb58392", "roi": 3.0},
        {"rank": 2, "id": "cand-dyn-slice:b84aad7b10ee", "roi": 2.9},
    ]
    chosen = select_after_rerank(top, excluded={"cand-dyn-slice:cb906bb58392"})
    assert chosen["id"] == "cand-dyn-slice:b84aad7b10ee"


def test_cycle2_accepts_second_slice(cto_repo, monkeypatch):
    from scripts.cto import cycle2_rerank_integration as m

    monkeypatch.setattr(
        m,
        "preflight_for_cycle",
        lambda root=None, require_grok=False: {"ok": True},
    )
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
        cycle_id="cyc2-unit",
        cycle1_selected_id="cand-dyn-slice:cb906bb58392",
        dry_run=True,
    )
    assert out["ok"] is True
    assert out["chosen"]["id"] == "cand-dyn-slice:b84aad7b10ee"
    assert out["strategic"]["action"] == "ACCEPT_TOP"
    assert "cb906bb58392" in out["excluded_work_ids"]

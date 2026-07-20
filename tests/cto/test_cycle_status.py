"""Idempotent DOD/HTML cycle status upserts."""
from __future__ import annotations

from scripts.cto.cycle_status import (
    apply_cycle_status,
    render_cycle_block,
    upsert_delimited_block,
    upsert_dod_cycle_status,
    upsert_html_cycle_status,
)


def test_upsert_delimited_idempotent():
    start, end = "<!-- A:START -->", "<!-- A:END -->"
    text = "header\n"
    b1 = f"{start}\none\n{end}\n"
    t1 = upsert_delimited_block(text, start, end, b1)
    assert t1.count(start) == 1
    b2 = f"{start}\ntwo\n{end}\n"
    t2 = upsert_delimited_block(t1, start, end, b2)
    assert t2.count(start) == 1
    assert "two" in t2
    assert "one" not in t2


def test_upsert_dod_twice_single_block(cto_repo):
    status = {
        "cycle_id": "cyc-status-1",
        "branch": "feat/x",
        "commit_base": "aaa",
        "commit_candidate": "bbb",
        "objective": "test",
        "verification_result": "PASS",
        "qa_verdict": "ACCEPT",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
        "before": "0",
        "after": "0",
        "dod_items": ["§test"],
        "next_action": "human review",
    }
    r1 = upsert_dod_cycle_status(status, root=cto_repo, dry_run=False)
    assert r1["ok"]
    r2 = upsert_dod_cycle_status({**status, "after": "partial"}, root=cto_repo, dry_run=False)
    assert r2["ok"]
    text = (cto_repo / "DOD.md").read_text(encoding="utf-8")
    assert text.count("<!-- CTO-CYCLE-STATUS:START -->") == 1
    assert "partial" in text


def test_blocked_cycle_does_not_claim_integrated(cto_repo):
    status = {
        "cycle_id": "cyc-blocked",
        "verification_result": "FAIL",
        "qa_verdict": "BLOCK",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
        "objective": "blocked work",
    }
    block = render_cycle_block(status)
    assert "INTEGRATED" not in block or "AWAITING" in block
    assert "FAIL" in block


def test_html_upsert_idempotent(cto_repo):
    html = cto_repo / "extra-consultoria-plano-executivo.html"
    if not html.is_file():
        html.write_text("<html><body><h1>exec</h1></body></html>\n", encoding="utf-8")
    status = {
        "cycle_id": "cyc-html-1",
        "verification_result": "PASS",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
        "pr": "#50",
    }
    upsert_html_cycle_status(status, root=cto_repo, dry_run=False)
    upsert_html_cycle_status({**status, "pr": "#51"}, root=cto_repo, dry_run=False)
    text = html.read_text(encoding="utf-8")
    assert text.count("<!-- CTO-CYCLE-STATUS:START -->") == 1
    assert "#51" in text


def test_apply_cycle_writes_artifacts(cto_repo):
    status = {
        "cycle_id": "cyc-arts-1",
        "verification_result": "PASS",
        "before": "x",
        "after": "y",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
    }
    out = apply_cycle_status(status, root=cto_repo, dry_run=False)
    assert out["ok"]
    cdir = cto_repo / "output" / "cto" / "cycles" / "cyc-arts-1"
    assert (cdir / "cycle-report.json").is_file()
    assert (cdir / "dod-delta.json").is_file()
    assert (cdir / "manifest.json").is_file()

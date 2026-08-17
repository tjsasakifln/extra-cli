"""Drive the shipped national-backfill auditor — no reimplementation."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.crawl.run_contracts_90d_pilot import (
    count_planned_windows,
    iter_planned_window_keys,
)
from scripts.ops.audit_pncp_national_backfill import (
    HC_CLOSURE_END,
    HC_CLOSURE_START,
    VERDICT_COMPLETO,
    VERDICT_INCOMPLETO,
    VERDICT_PARCIAL,
    build_report,
    build_window_matrix,
    classify_verdict,
    load_json,
    render_html,
    sha256_file,
    write_deliverables,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pncp_national_backfill" / "hc_closure_3y_contracts_full.json"


def _live_checkpoint() -> dict:
    return load_json(FIXTURE)


def _lake(*, within_sla: bool = True, count_all: int = 4_572_996) -> dict:
    return {
        "count_all": count_all,
        "count_active": count_all,
        "count_inactive": 0,
        "min_data_publicacao": "2023-07-20",
        "max_data_publicacao": "2026-08-15",
        "in_3y_span": 4_439_372,
        "after_backfill_end": 133_624,
        "incremental": {
            "age_hours": 65.4,
            "sla_hours": 168,
            "within_sla": within_sla,
        },
    }


def test_iter_planned_keys_match_count_and_fixture_completed_set():
    keys = iter_planned_window_keys(HC_CLOSURE_START, HC_CLOSURE_END)
    assert len(keys) == count_planned_windows(HC_CLOSURE_START, HC_CLOSURE_END)
    assert keys[0] == "20230720_20230818"
    assert keys[-1] == "20260704_20260723"
    completed = set(_live_checkpoint()["completed_windows"])
    assert set(keys) == completed


def test_live_fixture_classifies_completo_via_shipped_entrypoints():
    checkpoint = _live_checkpoint()
    matrix = build_window_matrix(checkpoint)
    assert matrix["never_ran"] == []
    assert matrix["failed_in_set"] == []
    assert matrix["blocked_in_set"] == []
    assert classify_verdict(matrix, _lake()) == VERDICT_COMPLETO
    report = build_report(
        checkpoint=checkpoint,
        checkpoint_path=str(FIXTURE),
        checkpoint_sha256=sha256_file(FIXTURE),
        lake=_lake(),
        reprocess_started=False,
    )
    assert report["verdict"] == VERDICT_COMPLETO
    html = render_html(report)
    assert VERDICT_COMPLETO in html
    assert "20230720_20230818" in html


def test_missing_named_window_is_parcial_not_completo():
    checkpoint = _live_checkpoint()
    removed = checkpoint["completed_windows"][-1]
    checkpoint = {
        **checkpoint,
        "completed_windows": list(checkpoint["completed_windows"][:-1]),
    }
    matrix = build_window_matrix(checkpoint)
    assert matrix["never_ran"] == [removed]
    assert classify_verdict(matrix, _lake()) == VERDICT_PARCIAL


def test_material_hole_is_incompleto():
    keys = iter_planned_window_keys(HC_CLOSURE_START, HC_CLOSURE_END)
    checkpoint = {"completed_windows": keys[:3], "failed_windows": [], "blocked_windows": []}
    matrix = build_window_matrix(checkpoint)
    assert classify_verdict(matrix, _lake()) == VERDICT_INCOMPLETO


def test_stale_incremental_blocks_completo():
    matrix = build_window_matrix(_live_checkpoint())
    assert classify_verdict(matrix, _lake(within_sla=False)) == VERDICT_PARCIAL


def test_write_deliverables_repeat_same_verdict_token(tmp_path: Path):
    report = build_report(
        checkpoint=_live_checkpoint(),
        checkpoint_path=str(FIXTURE),
        checkpoint_sha256=sha256_file(FIXTURE),
        lake=_lake(),
    )
    written = write_deliverables(report, tmp_path)
    decision = json.loads(Path(written["decision.json"]).read_text(encoding="utf-8"))
    html = Path(written["report.html"]).read_text(encoding="utf-8")
    assert decision["verdict"] == report["verdict"] == VERDICT_COMPLETO
    assert html.count(VERDICT_COMPLETO) >= 1
    assert "VPS_OPERATIONAL" not in decision["verdict"]


def test_planned_span_is_at_least_three_years():
    span = (HC_CLOSURE_END - HC_CLOSURE_START).days + 1
    assert span >= 1098
    assert count_planned_windows(HC_CLOSURE_START, HC_CLOSURE_END) == len(
        iter_planned_window_keys(date(2023, 7, 20), date(2026, 7, 23))
    )

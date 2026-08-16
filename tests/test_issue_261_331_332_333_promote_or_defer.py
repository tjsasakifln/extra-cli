"""Refs #261 #331 #332 #333 — consume #346 ranking; promote or defer.

Drives scripts.coverage.promote_or_defer. No adapter modules are created.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.coverage.alerta_miss_ranking import AdapterRank
from scripts.coverage.promote_or_defer import (
    ISSUE_SOURCES,
    MATERIAL_UNIQUE_RECALL,
    decide_all,
    decide_promotion,
    decisions_payload,
    load_ranking,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures" / "alerta_miss"
SNAPSHOT = FIXTURES / "snapshot-197.jsonl"
EXTRA = FIXTURES / "extra-window.jsonl"


def test_issue_261_331_332_333_consume_346_snapshot_and_defer() -> None:
    report = load_ranking(SNAPSHOT, EXTRA)
    decisions = decide_all(report)
    by_issue = {item.issue: item for item in decisions}
    assert set(by_issue) == {261, 331, 332, 333}
    for issue, item in by_issue.items():
        assert item.decision == "DEFER"
        assert item.seed_identity == ISSUE_SOURCES[issue]["seed_identity"]
        assert item.seed_evidence
        assert item.ranking_hash == report.report_hash
        assert item.unique_recall < MATERIAL_UNIQUE_RECALL
    payload = decisions_payload(report, decisions)
    assert payload["consumes"] == "#346"
    assert payload["adapter_code_started"] is False
    assert payload["coverage_engineering_started"] is False
    assert payload["live_ops_started"] is False
    seed_ids = {row["identity"] for row in payload["historical_seeds"]}
    assert {"BLL-261", "BNC-331", "DOU-332", "MUN-333"} <= seed_ids


def test_issue_261_promote_only_when_material_and_top() -> None:
    rank = AdapterRank(
        adapter_key="bll",
        n_misses=5,
        expected_unique_recall_gain=5.0,
        business_relevance=1.0,
        reuse_factor=0.7,
        implementation_effort=5.0,
        score=0.7,
        uncertainty="measured",
        snapshot_ref="fixture:top",
        components={},
    )
    lower = AdapterRank(
        adapter_key="bnc",
        n_misses=4,
        expected_unique_recall_gain=4.0,
        business_relevance=1.0,
        reuse_factor=0.7,
        implementation_effort=5.0,
        score=0.56,
        uncertainty="measured",
        snapshot_ref="fixture:lower",
        components={},
    )
    seed = {"identity": "BLL-261", "evidence": "https://bll.org.br/edital/261", "issue": 261}
    promoted = decide_promotion(issue=261, rank=rank, top=rank, seed=seed, ranking_hash="abc")
    assert promoted.decision == "PROMOTE"
    assert promoted.unique_recall == 5.0
    assert promoted.implementation_effort == 5.0
    deferred = decide_promotion(issue=331, rank=lower, top=rank, seed=seed, ranking_hash="abc")
    assert deferred.decision == "DEFER"
    assert "not the highest" in deferred.reason


def test_issue_332_333_cli_records_decisions(tmp_path: Path) -> None:
    out = tmp_path / "decisions.json"
    rc = main(
        [
            "--alerta",
            str(SNAPSHOT),
            "--extra",
            str(EXTRA),
            "--issues",
            "261,331,332,333",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["issue"] for row in payload["decisions"]] == [261, 331, 332, 333]
    assert all(row["decision"] == "DEFER" for row in payload["decisions"])
    assert payload["adapter_code_started"] is False


def test_issue_261_331_332_333_do_not_add_adapter_modules() -> None:
    root = Path(__file__).resolve().parents[1] / "scripts" / "crawl"
    for name in ("bll_crawler.py", "bnc_crawler.py", "dou_crawler.py", "portais_municipais_crawler.py"):
        assert not (root / name).exists()

"""Refs #252 #254 #255 #260 #334 #335 — consume #346 ranking; promote or defer.

Drives scripts.coverage.promote_or_defer. No adapter modules are created.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.coverage.alerta_miss_ranking import AdapterRank
from scripts.coverage.promote_or_defer import (
    FORBIDDEN_ADAPTER_MODULES,
    ISSUE_SOURCES,
    MATERIAL_UNIQUE_RECALL,
    WAVE2_ISSUES,
    decide_all,
    decide_promotion,
    decisions_payload,
    load_ranking,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures" / "alerta_miss"
SNAPSHOT = FIXTURES / "snapshot-197.jsonl"
EXTRA = FIXTURES / "extra-window.jsonl"


def test_wave2_consume_346_snapshot_and_defer() -> None:
    report = load_ranking(SNAPSHOT, EXTRA)
    decisions = decide_all(report, WAVE2_ISSUES)
    by_issue = {item.issue: item for item in decisions}
    assert set(by_issue) == set(WAVE2_ISSUES)
    for issue, item in by_issue.items():
        assert item.decision == "DEFER"
        assert item.seed_identity == ISSUE_SOURCES[issue]["seed_identity"]
        assert item.seed_evidence
        assert item.ranking_hash == report.report_hash
    for issue in (252, 254, 255, 260):
        item = by_issue[issue]
        assert item.unique_recall is None
        assert item.implementation_effort is None
        assert item.score is None
        assert item.n_misses is None
        assert item.snapshot_ref is None
        assert "no commercially ranked row" in item.reason
    for issue in (334, 335):
        item = by_issue[issue]
        assert item.unique_recall is not None
        assert item.unique_recall < MATERIAL_UNIQUE_RECALL
        assert item.n_misses == 1
        assert item.snapshot_ref
    payload = decisions_payload(report, decisions)
    assert payload["consumes"] == "#346"
    assert payload["adapter_code_started"] is False
    assert payload["coverage_engineering_started"] is False
    assert payload["live_ops_started"] is False
    assert payload["ranking_hash"] == report.report_hash
    assert [row["issue"] for row in payload["decisions"]] == list(WAVE2_ISSUES)


def test_wave2_promote_only_when_material_and_top() -> None:
    rank = AdapterRank(
        adapter_key="joinville",
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
        adapter_key="e-publica",
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
    seed = {"identity": "JOI-334", "evidence": "https://joinville.sc.gov.br/edital/334", "issue": 334}
    promoted = decide_promotion(issue=334, rank=rank, top=rank, seed=seed, ranking_hash="abc")
    assert promoted.decision == "PROMOTE"
    assert promoted.unique_recall == 5.0
    deferred = decide_promotion(issue=335, rank=lower, top=rank, seed=seed, ranking_hash="abc")
    assert deferred.decision == "DEFER"
    assert "not the highest" in deferred.reason
    below = AdapterRank(
        adapter_key="ocds",
        n_misses=1,
        expected_unique_recall_gain=1.0,
        business_relevance=1.0,
        reuse_factor=0.7,
        implementation_effort=5.0,
        score=0.14,
        uncertainty="measured",
        snapshot_ref="fixture:below",
        components={},
    )
    ocds = decide_promotion(
        issue=252,
        rank=below,
        top=below,
        seed={"identity": "OCDS-252", "evidence": "no collector", "issue": 252},
        ranking_hash="abc",
    )
    assert ocds.decision == "DEFER"
    assert "material threshold" in ocds.reason


def test_wave2_cli_records_decisions_and_ranking_hash(tmp_path: Path) -> None:
    out = tmp_path / "decisions.json"
    rc = main(
        [
            "--alerta",
            str(SNAPSHOT),
            "--extra",
            str(EXTRA),
            "--issues",
            "252,254,255,260,334,335",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [row["issue"] for row in payload["decisions"]] == [252, 254, 255, 260, 334, 335]
    assert all(row["decision"] == "DEFER" for row in payload["decisions"])
    assert payload["adapter_code_started"] is False
    assert payload["ranking_hash"]
    by_issue = {row["issue"]: row for row in payload["decisions"]}
    assert by_issue[334]["seed_identity"] == "JOI-334"
    assert by_issue[335]["seed_identity"] == "EPUB-335"
    assert by_issue[334]["unique_recall"] == 1.0
    assert by_issue[335]["unique_recall"] == 1.0
    for issue in (252, 254, 255, 260):
        assert by_issue[issue]["unique_recall"] is None
        assert by_issue[issue]["implementation_effort"] is None
        assert by_issue[issue]["score"] is None
        assert by_issue[issue]["n_misses"] is None
    assert by_issue[252]["source"] == "Compras.gov OCDS"
    assert by_issue[254]["source"] == "DOE-SC"
    assert by_issue[255]["source"] == "TCE-SC"
    assert by_issue[260]["source"] == "PCP"


def test_wave2_do_not_add_adapter_modules() -> None:
    root = Path(__file__).resolve().parents[1] / "scripts" / "crawl"
    for name in FORBIDDEN_ADAPTER_MODULES:
        assert not (root / name).exists()
    # Existing PCP/TCE/DOE crawlers must not be rewritten as a promote.
    # Measurement-only: the new adapter filenames above stay absent.
    assert not (root / "joinville_crawler.py").exists()
    assert not (root / "e_publica_crawler.py").exists()
    assert not (root / "ocds_crawler.py").exists()

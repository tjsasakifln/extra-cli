"""Instantiate real adapters against production seams (ARCH-RESET skeptic remediation)."""
from __future__ import annotations

from pathlib import Path

from scripts.architecture.adapters import (
    DeadlineDecisionAdapter,
    DirectoryPackDeliveryAdapter,
    RatioCoverageAdapter,
    WeeklyFreshnessAdapter,
    default_coverage_contract,
    default_decision_rules,
    default_freshness_gate,
    default_pack_delivery,
)
from scripts.architecture.interfaces import (
    CoverageContract,
    DecisionRules,
    FreshnessGate,
    PackDelivery,
)


def test_freshness_adapter_is_protocol_and_matches_partial_rule() -> None:
    gate: FreshnessGate = default_freshness_gate()
    assert isinstance(gate, WeeklyFreshnessAdapter)
    assert gate.classify(status="partial", age_hours=1.0, sla_hours=48, scope_complete=False) == "incomplete"
    assert gate.classify(status="completed", age_hours=1.0, sla_hours=48, scope_complete=True) == "fresh"


def test_coverage_adapter_fail_closed_universe() -> None:
    c: CoverageContract = default_coverage_contract()
    assert isinstance(c, RatioCoverageAdapter)
    bad = c.compute_operational_ratio(covered=10, universe=0, capability="editais")
    assert bad["ok"] is False
    good = c.compute_operational_ratio(covered=100, universe=1093, capability="editais")
    assert good["ok"] is True
    assert good["claim_95_forbidden"] is True
    assert abs(good["ratio"] - 100 / 1093) < 1e-9


def test_pack_delivery_adapter_reads_manifest(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "manifest.json").write_text(
        '{"cycle_id": "weekly-test-1", "collection_id": "col-1"}\n',
        encoding="utf-8",
    )
    (pack / "executive_summary.md").write_text("# hi\n", encoding="utf-8")
    d: PackDelivery = default_pack_delivery()
    assert isinstance(d, DirectoryPackDeliveryAdapter)
    out = d.collect_artifacts(pack)
    assert out["run_id"] == "weekly-test-1"
    assert out["artifacts"]["manifest.json"]
    assert out["artifacts"]["executive_summary.md"]
    assert out["artifacts"]["opportunities.csv"] is None
    assert out["n_present"] == 2


def test_decision_rules_expired_blocks_even_if_open() -> None:
    rules: DecisionRules = default_decision_rules()
    assert isinstance(rules, DeadlineDecisionAdapter)
    assert rules.is_expired_blocker(deadline_passed=True, status_open=True) is True
    assert rules.is_expired_blocker(deadline_passed=False, status_open=True) is False

"""Structural fitness functions for ARCH-RESET recovery.

These are real structural checks — not scanners that only prove a string exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from scripts.collect.run_contract import CollectionRun
from scripts.ops.weekly_cycle import (
    EXIT_OK,
    StageResult,
    evaluate_readiness,
)

ROOT = Path(__file__).resolve().parents[2]


def test_single_product_canonical_weekly_entrypoint() -> None:
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    product = data["entrypoint_classification"]["product_canonical"]
    assert len(product) == 1
    assert product[0]["make"] == "extra-weekly"
    assert product[0]["module"] == "scripts.ops.weekly_cycle"
    assert data["product_canonical_module"] == "scripts.ops.weekly_cycle"


def test_engineering_verify_is_narrow_not_product() -> None:
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    eng = {r.get("make") for r in data["entrypoint_classification"]["engineering"]}
    prod = {r.get("make") for r in data["entrypoint_classification"]["product_canonical"]}
    assert data["engineering_verify_command"] == "verify-weekly"
    assert "verify-weekly" in eng
    assert "verify-weekly" not in prod
    assert "extra-weekly" not in eng


def test_makefile_mandatory_gates_no_or_true() -> None:
    """ruff/pytest recipes must not swallow failures with || true."""
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("lint", "verify-weekly", "test", "test-all", "extra-weekly"):
        m = re.search(rf"^{re.escape(target)}:.*?(?=^\S|\Z)", mk, flags=re.M | re.S)
        assert m, f"missing make target {target}"
        block = m.group(0)
        # Allow || true only in clean's find (not in these gates)
        if target == "clean":
            continue
        assert "|| true" not in block, f"{target} must not use || true"


def test_no_llm_in_freshness_or_coverage_modules() -> None:
    """Freshness/coverage classification must stay deterministic (no LLM imports)."""
    banned = re.compile(
        r"\b(openai|anthropic|litellm|langchain|chat_completion|ChatCompletion)\b",
        re.I,
    )
    paths = [
        ROOT / "scripts/ops/weekly_cycle.py",
        ROOT / "scripts/quality/indicator_catalog.py",
    ]
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert not banned.search(text), f"LLM dependency found in {path}"


def test_impossible_exit_ok_with_mandatory_blockers() -> None:
    stages = [
        StageResult(
            name="validate_db",
            status="warn",
            detail={"universe_200km": 0, "expected_universe": 1093},
        ),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 1}},
        ),
        StageResult(
            name="delivery",
            status="ok",
            detail={
                "excel_ok": True,
                "checksums_file": "x",
                "product_checksums": {"a": {"sha256": "b"}},
            },
        ),
    ]
    opp = CollectionRun.start(
        source="pncp_opportunities", collection_id="c", collector_version="t"
    )
    opp.finish(
        records_obtained=1,
        records_persisted=1,
        request_completed=True,
        scope_complete=True,
    )
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(request_completed=False, scope_complete=False, error="no contracts")
    ev = evaluate_readiness(
        stages,
        [opp, ct],
        strict=True,
        freshness=[
            {"source": "pncp_opportunities", "level": "never", "age_hours": None},
            {"source": "pncp_contracts", "level": "never"},
        ],
        execution_scope="sample",
    )
    assert ev.exit_code != EXIT_OK
    assert ev.consultive_ready is False
    assert ev.blockers


def test_sample_execution_cannot_be_consultive_ready() -> None:
    stages = [
        StageResult(
            name="validate_db",
            status="ok",
            detail={"universe_200km": 1093, "expected_universe": 1093},
        ),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 5}},
        ),
        StageResult(
            name="delivery",
            status="ok",
            detail={
                "excel_ok": True,
                "checksums_file": "x",
                "product_checksums": {"a": {"sha256": "b"}},
            },
        ),
    ]
    opp = CollectionRun.start(
        source="pncp_opportunities", collection_id="c", collector_version="t"
    )
    opp.finish(
        records_obtained=10,
        records_persisted=10,
        request_completed=True,
        scope_complete=True,
        reused_within_sla=True,
    )
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(
        records_obtained=10,
        records_persisted=10,
        request_completed=True,
        scope_complete=False,
        reused_within_sla=True,
    )
    fr = [
        {"source": "pncp_opportunities", "level": "fresh", "age_hours": 1.0},
        {"source": "pncp_contracts", "level": "fresh", "age_hours": 1.0},
    ]
    ev = evaluate_readiness(
        stages, [opp, ct], strict=True, freshness=fr, execution_scope="sample"
    )
    assert ev.consultive_ready is False
    assert ev.exit_code != EXIT_OK


def test_weekly_cycle_is_registered_canonical_module() -> None:
    """Only one module registered as product weekly contract."""
    data = yaml.safe_load((ROOT / "docs/canonical-entry-points.yaml").read_text(encoding="utf-8"))
    modules = [
        row.get("module")
        for row in data["entrypoint_classification"]["product_canonical"]
        if row.get("module")
    ]
    assert modules == ["scripts.ops.weekly_cycle"]
    # Module file must exist
    assert (ROOT / "scripts/ops/weekly_cycle.py").is_file()

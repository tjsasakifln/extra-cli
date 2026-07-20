"""Characterization tests for the canonical Extra weekly pipeline.

Selectively reused from ARCH-RESET PR #55, strengthened for fail-closed readiness
(PR #63 / ARCH-RESET-RECOVERY). Behavior locks, not string theater.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.collect.run_contract import CollectionRun
from scripts.ops.weekly_cycle import (
    EXIT_OK,
    EXIT_TECH,
    EXIT_UNRELIABLE,
    StageResult,
    build_parser,
    classify_execution_scope,
    classify_opportunity_freshness,
    compute_exit_code,
    evaluate_readiness,
    run_weekly_cycle,
)

ROOT = Path(__file__).resolve().parents[2]


def test_makefile_extra_weekly_points_to_weekly_cycle_module() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^extra-weekly:", makefile, flags=re.M)
    assert "scripts.ops.weekly_cycle" in makefile
    assert "--strict" in makefile


def test_makefile_verify_weekly_has_no_true_swallow() -> None:
    """Mandatory weekly gate must not ignore ruff/pytest failures."""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^verify-weekly:", makefile, flags=re.M)
    # Extract verify-weekly recipe block until next target
    m = re.search(
        r"^verify-weekly:.*?(?=^\S|\Z)",
        makefile,
        flags=re.M | re.S,
    )
    assert m, "verify-weekly target missing"
    block = m.group(0)
    assert "|| true" not in block
    assert "ruff check" in block
    assert "pytest" in block or "python3 -m pytest" in block


def test_canonical_entry_points_yaml_marks_weekly_product() -> None:
    path = ROOT / "docs" / "canonical-entry-points.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data.get("product_canonical_command") == "extra-weekly"
    assert data.get("product_canonical_module") == "scripts.ops.weekly_cycle"
    cmds = data.get("commands") or {}
    assert "weekly" in cmds
    weekly_blob = cmds["weekly"]
    text = weekly_blob if isinstance(weekly_blob, str) else yaml.safe_dump(weekly_blob)
    assert "extra-weekly" in text or "weekly_cycle" in text


def test_competing_make_targets_still_exist_but_are_not_extra_weekly() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-zA-Z0-9_.-]+):", makefile, flags=re.M))
    assert "extra-weekly" in targets
    for t in ("golden-path", "run-pipeline", "report-executivo", "resilient-local-cycle"):
        assert t in targets, f"expected make target {t} present at baseline"


def test_cli_parser_exposes_strict_and_offline_seams() -> None:
    p = build_parser()
    help_text = p.format_help()
    assert "--strict" in help_text
    assert "--offline" in help_text


def test_stage_boundary_names_stable_for_strangler() -> None:
    critical_stage_names = {
        "validate_config",
        "validate_db",
        "delivery",
        "quality",
        "intelligence",
        "collect",
    }
    src = (ROOT / "scripts" / "ops" / "weekly_cycle.py").read_text(encoding="utf-8")
    for name in critical_stage_names:
        assert f'"{name}"' in src or f"'{name}'" in src
    # Central policy must exist (not scattered ifs only)
    assert "StrictReadinessPolicy" in src
    assert "evaluate_readiness" in src


def test_partial_collect_never_exit_ok_strict() -> None:
    run = CollectionRun.start(
        source="pncp_opportunities",
        collection_id="char-c",
        collector_version="t",
    )
    run.finish(
        records_obtained=5,
        records_persisted=5,
        request_completed=True,
        scope_complete=False,
        error="partial",
    )
    stages = [
        StageResult(name="validate_db", status="ok", detail={"universe_200km": 1093, "expected_universe": 1093}),
        StageResult(name="collect", status="ok"),
        StageResult(name="quality", status="ok"),
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 3}},
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
    assert compute_exit_code(stages, [run], strict=True) == EXIT_UNRELIABLE
    assert compute_exit_code(stages, [run], strict=True) != EXIT_OK


def test_freshness_fail_closed_for_partial() -> None:
    assert (
        classify_opportunity_freshness(
            status="partial",
            age_hours=0.1,
            sla_hours=48,
            scope_complete=False,
        )
        == "incomplete"
    )


def test_run_weekly_without_db_is_tech_fail_and_has_ids(tmp_path: Path) -> None:
    report = run_weekly_cycle(
        dsn="postgresql://invalid:invalid@127.0.0.1:1/no_db",
        output_dir=tmp_path / "out",
        strict=True,
        offline=True,
        skip_collect=True,
        limit=5,
    )
    assert report.cycle_id
    assert report.collection_id
    assert report.exit_code == EXIT_TECH
    assert "LOCAL_READY" in report.claims_forbidden


def test_two_offline_cycles_get_distinct_cycle_ids(tmp_path: Path) -> None:
    r1 = run_weekly_cycle(
        dsn="postgresql://invalid:invalid@127.0.0.1:1/no_db",
        output_dir=tmp_path / "a",
        offline=True,
        skip_collect=True,
    )
    r2 = run_weekly_cycle(
        dsn="postgresql://invalid:invalid@127.0.0.1:1/no_db",
        output_dir=tmp_path / "b",
        offline=True,
        skip_collect=True,
    )
    assert r1.cycle_id != r2.cycle_id
    assert r1.collection_id != r2.collection_id


@pytest.mark.parametrize(
    "forbidden",
    [
        "LOCAL_READY",
        "VPS_OPERATIONAL",
        "PROJECT_DONE",
        "cobertura operacional 95%",
    ],
)
def test_forbidden_claims_always_listed(forbidden: str, tmp_path: Path) -> None:
    report = run_weekly_cycle(
        dsn="postgresql://invalid:invalid@127.0.0.1:1/no_db",
        output_dir=tmp_path / "c",
        offline=True,
        skip_collect=True,
    )
    assert forbidden in report.claims_forbidden


def test_sample_scope_never_consultive_ready() -> None:
    assert classify_execution_scope(offline=False, limit=5) == "sample"
    stages = [
        StageResult(
            name="validate_db",
            status="ok",
            detail={"universe_200km": 1093, "expected_universe": 1093},
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
        StageResult(
            name="intelligence",
            status="ok",
            detail={"counts": {"opportunities": 1}},
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
        reused_within_sla=True,
    )
    ct = CollectionRun.start(
        source="pncp_contracts", collection_id="c", collector_version="t"
    )
    ct.finish(
        records_obtained=1,
        records_persisted=1,
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

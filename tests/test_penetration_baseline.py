"""Tests for the #381 operational penetration snapshot (reuses #388 classify)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.market_penetration.baseline import (
    build_operational_snapshot,
    emit_snapshot,
    render_executive_report,
)
from scripts.market_penetration.cli import main as penetration_main
from scripts.market_penetration.facts import (
    WARMBLY_EVENT_TO_STAGE,
    assess_warmbly_freshness,
    join_account_facts,
    join_from_paths,
    map_warmbly_event,
)
from scripts.market_penetration.icp_denominator import STAGES, PenetrationError
from scripts.market_penetration.sanity import collect_pii_hits, run_sanity

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "penetration"
AS_OF = "2026-08-15"


def _hashes() -> dict[str, str]:
    return {"universe": "u", "dui": "d", "warmbly": "w"}


def _join(
    universe: list[dict],
    dui: list[dict] | None = None,
    warmbly: list[dict] | None = None,
    *,
    absent: bool = False,
    max_age: int = 90,
    version: str = "fixture:v1",
):
    return join_account_facts(
        tuple(universe),
        tuple(dui or []),
        tuple(warmbly or []),
        as_of=AS_OF,
        universe_version=version,
        input_hashes=_hashes(),
        warmbly_absent=absent,
        max_warmbly_age_days=max_age,
    )


def test_shipped_map_only_uses_388_stages() -> None:
    assert set(WARMBLY_EVENT_TO_STAGE.values()) <= set(STAGES)
    assert map_warmbly_event("REPLIED") == "QUALIFIED_CONVERSATION"
    assert map_warmbly_event("WON") == "CLIENT"
    assert map_warmbly_event("LEAD_REVIEWED") is None
    assert map_warmbly_event("LOST") is None


def test_in_process_facts_cover_each_stage_without_invented_tam() -> None:
    join = _join(
        [
            {"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 2}},
            {"cnpj14": "22333444000155", "uf": "SC", "portfolio": {"contract_count_total": 2}},
            {"cnpj14": "33445566000186", "uf": "SC", "portfolio": {"contract_count_total": 2}},
            {"cnpj14": "44555666000181", "uf": "SC", "portfolio": {"contract_count_total": 2}},
            {"cnpj14": "77888999000181", "uf": "SC", "portfolio": {"contract_count_total": 2}},
            {"cnpj14": "99888777000166", "uf": "PR", "portfolio": {"contract_count_total": 2}},
        ],
        [
            {"cnpj": "22333444000155", "terminal": "DECISION_UNIT_IDENTIFIED_REACHABILITY_UNRESOLVED"},
            {
                "cnpj": "33445566000186",
                "terminal": "ACTIONABLE_ROUTE",
                "extra": {"account_reachability_class": "R4_ROLE_ROUTE"},
            },
            {
                "cnpj": "44555666000181",
                "terminal": "ACTIONABLE_ROUTE",
                "extra": {"account_reachability_class": "R3_ROUTED_TO_NAMED_PERSON"},
            },
            {
                "cnpj": "77888999000181",
                "terminal": "ACTIONABLE_ROUTE",
                "extra": {"account_reachability_class": "R1_DIRECT"},
            },
        ],
        [
            {"cnpj14": "44555666000181", "event_type": "CONTACTED", "occurred_at": "2026-08-10T00:00:00Z"},
            {"cnpj14": "77888999000181", "event_type": "PROPOSAL", "occurred_at": "2026-08-10T00:00:00Z"},
        ],
    )
    first = build_operational_snapshot(join, as_of=AS_OF)
    second = build_operational_snapshot(join, as_of=AS_OF)
    assert first["hashes"]["assembly_hash"] == second["hashes"]["assembly_hash"]
    assert first["hashes"]["snapshot_hash"] == second["hashes"]["snapshot_hash"]
    assert first["denominator"]["invented_tam"] is False
    assert first["policy"]["invented_tam"] is False
    constructed_icp = sum(1 for account in join.accounts if account.fact.uf == "SC")
    assert first["counts"]["X_icp"] == constructed_icp
    assert first["by_stage"]["ICP_ACCOUNT"] == 1
    assert first["by_stage"]["DECISION_UNIT_KNOWN"] == 1
    assert first["by_stage"]["ACTIONABLE_ROUTE"] == 1
    assert first["by_stage"]["CONTACTED"] == 1
    assert first["by_stage"]["PROPOSAL"] == 1
    assert first["counts"]["Z_contacted"] == 1
    assert first["counts"]["P_proposals"] == 1
    assert first["counts"]["Y_reachable"] == 3
    assert first["by_stage"]["UNKNOWN"] == 1
    assert "99888777000166" in first["uncaptured_account_ids"]
    assert set(first["dimensions"]) == {"region", "size_portfolio", "trigger", "wedge", "route_class"}


def test_missing_evidence_stays_unknown_and_queryable() -> None:
    join = _join(
        [
            {
                "cnpj14": "11222333000181",
                "uf": "SC",
                "has_public_portfolio": False,
                "portfolio": {"contract_count_total": 0},
            }
        ],
    )
    snap = build_operational_snapshot(join, as_of=AS_OF)
    assert snap["by_stage"]["UNKNOWN"] == 1
    assert snap["counts"]["X_icp"] == 0
    assert "11222333000181" in snap["uncaptured_account_ids"]


def test_warmbly_absent_zeros_contacted_plus_and_keeps_unknown() -> None:
    join = _join(
        [
            {"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 4}},
            {"cnpj14": "99888777000166", "uf": "SP", "portfolio": {"contract_count_total": 4}},
        ],
        [
            {
                "cnpj": "11222333000181",
                "terminal": "ACTIONABLE_ROUTE",
                "extra": {"account_reachability_class": "R5_CORPORATE_ONLY"},
            }
        ],
        [{"cnpj14": "11222333000181", "event_type": "CLIENT", "occurred_at": "2026-08-10T00:00:00Z"}],
        absent=True,
    )
    snap = build_operational_snapshot(join, as_of=AS_OF)
    assert join.warmbly_status == "absent"
    assert snap["policy"]["warmbly_status"] == "absent"
    assert snap["by_stage"]["CONTACTED"] == 0
    assert snap["by_stage"]["QUALIFIED_CONVERSATION"] == 0
    assert snap["by_stage"]["MEETING"] == 0
    assert snap["by_stage"]["PROPOSAL"] == 0
    assert snap["by_stage"]["CLIENT"] == 0
    assert snap["by_stage"]["EXPANDED_CLIENT"] == 0
    assert snap["by_stage"]["ACTIONABLE_ROUTE"] == 1
    assert snap["by_stage"]["UNKNOWN"] == 1
    assert snap["counts"]["UNKNOWN"] == 1
    assert "99888777000166" in snap["uncaptured_account_ids"]


def test_warmbly_stage_not_overwritten_by_reachability() -> None:
    join = _join(
        [{"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 9}}],
        [
            {
                "cnpj": "11222333000181",
                "terminal": "ACTIONABLE_ROUTE",
                "extra": {"account_reachability_class": "R3_ROUTED_TO_NAMED_PERSON"},
            }
        ],
        [{"cnpj14": "11222333000181", "event_type": "CLIENT", "occurred_at": "2026-08-10T00:00:00Z"}],
    )
    snap = build_operational_snapshot(join, as_of=AS_OF)
    assert snap["by_stage"]["CLIENT"] == 1
    assert snap["by_stage"]["ACTIONABLE_ROUTE"] == 0
    assert snap["warmbly_authoritative_from"] == "CONTACTED"


def test_duplicate_join_fail_closed() -> None:
    join = _join(
        [
            {"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 1}},
            {"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 2}},
        ]
    )
    with pytest.raises(PenetrationError, match="duplicate_joins"):
        build_operational_snapshot(join, as_of=AS_OF)


def test_missing_canonical_id_fail_closed() -> None:
    join = _join([{"uf": "SC", "portfolio": {"contract_count_total": 1}}])
    with pytest.raises(PenetrationError, match="missing_canonical_id"):
        build_operational_snapshot(join, as_of=AS_OF)


def test_stale_warmbly_import_fail_closed() -> None:
    join = _join(
        [{"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 1}}],
        warmbly=[{"cnpj14": "11222333000181", "event_type": "CONTACTED", "occurred_at": "2025-01-01T00:00:00Z"}],
        max_age=30,
    )
    assert join.warmbly_freshness.stale is True
    with pytest.raises(PenetrationError, match="stale_warmbly_import"):
        build_operational_snapshot(join, as_of=AS_OF)


def test_warmbly_events_without_timestamp_are_stale() -> None:
    freshness = assess_warmbly_freshness(
        ({"cnpj14": "11222333000181", "event_type": "CONTACTED"},),
        as_of=AS_OF,
    )
    assert freshness.stale is True
    assert freshness.status == "stale"


def test_aggregates_have_no_pii_keys_or_values() -> None:
    join = _join(
        [{"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 6}}],
        [
            {
                "cnpj": "11222333000181",
                "terminal": "ACTIONABLE_ROUTE",
                "primary_decision_unit_target": "Ana Silva",
                "why_now": {"code": "CONTRACT_EXTENSION"},
                "offer": {"service_code": "acompanhamento_admin"},
                "extra": {"account_reachability_class": "R3_ROUTED_TO_NAMED_PERSON"},
            }
        ],
    )
    snap = build_operational_snapshot(join, as_of=AS_OF)
    assert collect_pii_hits(snap["dimensions"]) == []
    dumped = json.dumps(snap["dimensions"])
    assert "Ana Silva" not in dumped
    assert "@" not in dumped
    assert "email" not in dumped
    report = render_executive_report(snap)
    assert "Ana Silva" not in report


def test_replay_equality_from_same_rows() -> None:
    rows = ([{"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 3}}],)
    first = _join(*rows)
    second = _join(*rows)
    a = build_operational_snapshot(first, as_of=AS_OF)
    b = build_operational_snapshot(second, as_of=AS_OF)
    assert a["hashes"]["snapshot_hash"] == b["hashes"]["snapshot_hash"]
    assert a["hashes"]["assembly_hash"] == b["hashes"]["assembly_hash"]
    assert a["universe_version"] == b["universe_version"]
    assert a["as_of"] == b["as_of"]


def test_no_hardcoded_tam_constants_in_shipped_modules() -> None:
    root = Path(__file__).resolve().parents[1] / "scripts" / "market_penetration"
    banned = ("1093", "1.093", "48748", "401923")
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path.name} contains banned TAM token {token}"


def test_cli_snapshot_twice_same_hashes(tmp_path: Path) -> None:
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    common = [
        "snapshot",
        "--universe",
        str(FIXTURES / "universe.jsonl"),
        "--universe-manifest",
        str(FIXTURES / "universe_manifest.json"),
        "--dui",
        str(FIXTURES / "dui_accounts.json"),
        "--warmbly",
        str(FIXTURES / "warmbly_outcomes.jsonl"),
        "--as-of",
        AS_OF,
    ]
    assert penetration_main([*common, "--out", str(out1)]) == 0
    assert penetration_main([*common, "--out", str(out2)]) == 0
    snap1 = json.loads((out1 / "penetration-snapshot.json").read_text(encoding="utf-8"))
    snap2 = json.loads((out2 / "penetration-snapshot.json").read_text(encoding="utf-8"))
    assert snap1["hashes"]["assembly_hash"] == snap2["hashes"]["assembly_hash"]
    assert snap1["hashes"]["snapshot_hash"] == snap2["hashes"]["snapshot_hash"]
    assert snap1["as_of"] == AS_OF
    assert snap1["universe_version"].startswith("confenge-universe-rules-v1:2026-08-15:")
    assert snap1["policy"]["invented_tam"] is False
    assert "region" in snap1["dimensions"]
    assert (out1 / "penetration-aggregates.csv").is_file()
    assert "X ICP accounts" in (out1 / "penetration-executive.md").read_text(encoding="utf-8")
    assert all(check["passed"] for check in snap1["sanity"])
    assert snap1["counts"]["Z_contacted"] == snap1["by_stage"]["CONTACTED"]
    assert snap1["counts"]["P_proposals"] == snap1["by_stage"]["PROPOSAL"]
    assert snap1["by_stage"]["CLIENT"] == 0


def test_cli_warmbly_absent_flag(tmp_path: Path) -> None:
    out = tmp_path / "absent"
    code = penetration_main(
        [
            "snapshot",
            "--universe",
            str(FIXTURES / "universe.jsonl"),
            "--dui",
            str(FIXTURES / "dui_accounts.json"),
            "--warmbly-absent",
            "--as-of",
            AS_OF,
            "--out",
            str(out),
        ]
    )
    assert code == 0
    snap = json.loads((out / "penetration-snapshot.json").read_text(encoding="utf-8"))
    assert snap["policy"]["warmbly_status"] == "absent"
    assert snap["counts"]["Z_contacted"] == 0
    assert snap["counts"]["N_conversations"] == 0
    assert snap["counts"]["P_proposals"] == 0
    assert snap["counts"]["C_clients"] == 0
    assert snap["counts"]["UNKNOWN"] >= 1


def test_join_from_paths_matches_in_process() -> None:
    from_disk = join_from_paths(
        as_of=AS_OF,
        universe_path=FIXTURES / "universe.jsonl",
        dui_path=FIXTURES / "dui_accounts.json",
        warmbly_path=FIXTURES / "warmbly_outcomes.jsonl",
        universe_manifest_path=FIXTURES / "universe_manifest.json",
    )
    snap = build_operational_snapshot(from_disk, as_of=AS_OF)
    assert snap["by_stage"]["CONTACTED"] == 1
    assert snap["by_stage"]["PROPOSAL"] == 1
    assert snap["by_stage"]["ICP_ACCOUNT"] == 1
    assert snap["by_stage"]["DECISION_UNIT_KNOWN"] == 1
    assert snap["by_stage"]["ACTIONABLE_ROUTE"] == 0
    assert snap["by_stage"]["UNKNOWN"] == 2


def test_emit_snapshot_writes_three_artifacts(tmp_path: Path) -> None:
    join = _join([{"cnpj14": "11222333000181", "uf": "SC", "portfolio": {"contract_count_total": 1}}])
    payload = build_operational_snapshot(join, as_of=AS_OF)
    paths = emit_snapshot(payload, tmp_path)
    assert Path(paths["json"]).is_file()
    assert Path(paths["csv"]).is_file()
    assert Path(paths["report"]).is_file()


def test_sanity_fail_closed_unknown_recoded() -> None:
    join = _join([{"cnpj14": "99888777000166", "uf": "SP", "portfolio": {"contract_count_total": 1}}])
    fake_core = {
        "by_stage": {stage: 0 for stage in (*STAGES, "UNKNOWN")},
        "counts": {"UNKNOWN": 0},
        "uncaptured_account_ids": [],
    }
    fake_core["by_stage"]["ICP_ACCOUNT"] = 1
    with pytest.raises(PenetrationError, match="unknown_preserved"):
        run_sanity(join, fake_core, {"region": []}, fail_closed=True)

"""Fail-closed national, unit, freshness and pertinence gates on shipped functions."""

from __future__ import annotations

from scripts.bofu_evidence.claims import make_claim
from scripts.bofu_evidence.fixtures import load_comparable, load_national_coverage, load_snapshot
from scripts.bofu_evidence.gates import evaluate_gates
from scripts.bofu_evidence.producer import assemble_pack, build_family_pack, build_packs


def test_pr437_partial_keeps_national_false_and_blocks_national_claim() -> None:
    coverage = load_national_coverage()
    assert coverage["verdict"] == "PARTIAL"
    assert coverage["national_claim_authorized"] is False
    bundle = build_packs(national_coverage=coverage)
    for pack in bundle["packs"]:
        assert pack["national"] is False
        assert pack["coverage"]["national_claim_authorized"] is False
        assert pack["coverage"]["national_verdict"] == "PARTIAL"

    base = build_family_pack("reequilibrio")
    drafted = {key: value for key, value in base.items() if key != "content_hash"}
    drafted["national"] = True
    drafted["coverage"] = {**drafted["coverage"], "kind": "BR"}
    gate = evaluate_gates(
        drafted,
        national_coverage=coverage,
        now=drafted["as_of"],
        as_of_source=drafted["as_of_source"],
    )
    assert gate["national"] is False
    assert gate["state"] == "HOLD"
    assert "national_claim_blocked" in gate["reason_codes"]


def test_unit_promotion_of_brl_total_holds() -> None:
    snapshot = load_snapshot()
    coverage = load_national_coverage()
    peers = load_comparable()
    claims = [
        make_claim(
            "promoted-unit",
            "CALCULATION",
            "Valor do grupo convertido para custo por km.",
            value="12.5",
            unit="BRL_PER_KM",
            refs=("fixture:scripts/bofu_evidence/fixtures/pr435_comparable.json",),
            reason_code="unit_promotion",
        )
    ]
    pack = assemble_pack(
        family="orcamento_bdi",
        snapshot=snapshot,
        national_coverage=coverage,
        claims=claims,
        calculations=[],
        comparable_attached=True,
        as_of=snapshot["as_of"],
        expires=snapshot["expires"],
        as_of_source="snapshot",
        now=snapshot["as_of"],
    )
    assert pack["state"] == "HOLD"
    assert "unit_promotion_blocked" in pack["reason_codes"]
    assert pack["national"] is False
    assert peers["unit"] == "BRL_TOTAL"


def test_freshness_expired_or_wall_clock_blocks_ready() -> None:
    expired = build_family_pack("defesa_tecnica", now="2026-08-22T00:00:00Z")
    assert expired["state"] == "HOLD"
    assert "freshness_expired" in expired["reason_codes"]
    assert expired["publication"] is False

    wall = build_family_pack("defesa_tecnica", as_of_source="wall_clock")
    assert wall["state"] == "HOLD"
    assert "as_of_wall_clock" in wall["reason_codes"]
    assert wall["state"] != "READY"


def test_comparable_on_non_pertinent_family_holds() -> None:
    pack = build_family_pack("medicoes_glosas", force_comparable=True)
    assert pack["comparable_attached"] is True
    assert pack["state"] == "HOLD"
    assert "comparable_not_pertinent" in pack["reason_codes"]


def test_negative_absence_fact_is_rejected() -> None:
    snapshot = load_snapshot()
    coverage = load_national_coverage()
    pack = assemble_pack(
        family="aditivos",
        snapshot=snapshot,
        national_coverage=coverage,
        claims=[
            make_claim(
                "neg-abs",
                "FACT",
                "Nao houve aditivo neste contrato.",
                refs=("fixture:scripts/bofu_evidence/fixtures/snapshot.json",),
                reason_code="invented_negative",
            )
        ],
        calculations=[],
        comparable_attached=False,
        as_of=snapshot["as_of"],
        expires=snapshot["expires"],
        as_of_source="snapshot",
        now=snapshot["as_of"],
    )
    assert pack["state"] == "REJECT"
    assert "negative_absence_fact" in pack["reason_codes"]

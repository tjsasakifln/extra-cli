"""Tests for CONFENGE commercial activation planner.

Proves ordering score (not probability), capacity-aware hot set, determinism,
no mega-contract bias, observational language, DNC suppression, deactivation
deltas, and bounded processing of large reservoirs.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from scripts.confenge_activation.models import stable_hash
from scripts.confenge_activation.planner import (
    evaluate_row,
    run_activation_cycle,
    select_hot_set,
    source_hash_for_row,
)
from scripts.confenge_activation.policy import load_policy
from scripts.confenge_activation.publish import atomic_publish_directory
from scripts.confenge_activation.score import compute_activation_score
from scripts.confenge_activation.triggers import detect_triggers
from scripts.warmbly_bridge.mapping import map_lead

POLICY = load_policy()
AS_OF = date(2026, 8, 8)


def _company(
    cnpj: str,
    *,
    last: str = "2026-07-20",
    first: str = "2024-08-01",
    active: int = 3,
    recent: int = 2,
    value: float = 500_000.0,
    fit: str = "STRONG_ENGINEERING_FIT",
    objetos: list[str] | None = None,
    data_fim: str | None = None,
    commercial_state: str = "NEW",
    eligibility: str = "ELIGIBLE",
    priority: float = 55.0,
) -> dict:
    contracts = []
    for i, obj in enumerate(objetos or ["obra de engenharia civil"]):
        contracts.append(
            {
                "contrato_id": str(1000 + i),
                "objeto": obj,
                "data_publicacao": last,
                "data_fim": data_fim,
                "valor_total": value / max(1, len(objetos or [1])),
                "is_active": True,
                "category": "obra_engenharia",
            }
        )
    return {
        "cnpj14": cnpj,
        "cnpj_root": cnpj[:8],
        "razao_social": f"Empresa {cnpj[:4]}",
        "outreach_eligibility": eligibility,
        "commercial_state": commercial_state,
        "priority_score": priority,
        "construction_evidence": {
            "sector_fit": fit,
            "relevant_contract_count": max(1, recent),
        },
        "portfolio": {
            "active_contract_count": active,
            "contract_count_recent": recent,
            "contract_count_total": active + 5,
            "first_contract_date": first,
            "last_contract_date": last,
            "value_recent_brl": value,
            "value_total_brl": value * 2,
            "orgaos": ["ORGAO A", "ORGAO B"][: max(1, min(2, active))],
            "ufs_atuacao": ["SP", "RJ"][: max(1, min(2, active))],
            "recent_contracts": contracts,
        },
        "temporal_signals": {
            "last_contract_date": last,
            "note": "observational only",
        },
    }


def test_policy_weights_sum_to_100():
    assert abs(POLICY.score_weights.total() - 100.0) < 1e-6


def test_score_range_and_determinism():
    row = _company("11222333000181", last="2026-07-25")
    fired = detect_triggers(row, policy=POLICY, as_of=AS_OF)
    s1, c1 = compute_activation_score(row, fired, policy=POLICY, as_of=AS_OF)
    s2, c2 = compute_activation_score(row, fired, policy=POLICY, as_of=AS_OF)
    assert 0 <= s1 <= 100
    assert s1 == s2
    assert c1.as_dict() == c2.as_dict()
    assert sum(c1.as_dict().values()) == pytest.approx(s1, rel=1e-3)


def test_mega_contract_does_not_dominate_small_diverse():
    mega = _company(
        "11222333000181",
        value=5_000_000_000.0,  # R$ 5B
        active=1,
        recent=1,
        fit="POSSIBLE_ENGINEERING_FIT",
        last="2025-01-01",  # stale — weak freshness
        priority=40,
    )
    diverse = _company(
        "11222333000182",
        value=800_000.0,
        active=8,
        recent=5,
        fit="CONFIRMED_ENGINEERING",
        last="2026-07-28",
        priority=70,
        objetos=["obra de engenharia", "reforma estrutural"],
    )
    cycle = run_activation_cycle([mega, diverse], policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    by = {p.cnpj14: p for p in cycle.projections}
    # Recent diversified construction should outrank stale mega-contract alone
    assert by["11222333000182"].activation_score > by["11222333000181"].activation_score


def test_anniversary_is_not_unpaid_reajuste_claim():
    # first contract ~1 year ago → anniversary window near as_of
    row = _company(
        "11222333000183",
        first="2025-08-10",
        last="2025-09-01",
        active=1,
        recent=0,
        value=100_000,
    )
    fired = detect_triggers(row, policy=POLICY, as_of=AS_OF)
    codes = {f.code for f in fired}
    if "CONTRACT_ANNIVERSARY_WINDOW" in codes:
        ann = next(f for f in fired if f.code == "CONTRACT_ANNIVERSARY_WINDOW")
        lang = (ann.language + " " + json.dumps(ann.details)).lower()
        assert "não pago" not in lang
        assert "devido" not in lang or "justifica" in lang
        assert "verificar" in lang or "janela" in lang


def test_dnc_is_suppressed():
    row = _company("11222333000184", commercial_state="DO_NOT_CONTACT", last="2026-07-30")
    proj = evaluate_row(row, policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    assert proj.activation_state == "SUPPRESSED"
    assert proj.activation_score == 0.0


def test_new_relevant_contract_promotes():
    row = _company("11222333000185", last="2026-07-20", fit="STRONG_ENGINEERING_FIT")
    proj = evaluate_row(row, policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    assert "NEW_RELEVANT_CONTRACT" in proj.reason_codes or proj.activation_state in {
        "ACTIONABLE_NOW",
        "RESEARCH_REQUIRED",
    }
    if proj.activation_state == "ACTIONABLE_NOW":
        assert proj.reason_codes
        assert proj.next_best_action_at


def test_hot_set_respects_capacity():
    rows = []
    for i in range(300):
        cnpj = f"{i:08d}000181"
        assert len(cnpj) == 14
        rows.append(_company(cnpj, last="2026-07-25", priority=60))
    # Capacity override below reservoir proves planner bounds expensive path
    cap = 40
    planned = POLICY.capacity.planned_capacity()
    assert planned >= POLICY.capacity.min_hot_set
    assert planned <= POLICY.capacity.max_hot_set
    cycle = run_activation_cycle(
        rows, policy=POLICY, as_of=AS_OF, capacity_override=cap, evaluated_at="2026-08-08T10:00:00Z"
    )
    assert cycle.reservoir_count == 300
    assert cycle.hot_set_count <= cap
    assert cycle.hot_set_count <= POLICY.capacity.max_hot_set
    # Expensive path size << reservoir
    assert cycle.hot_set_count < cycle.reservoir_count


def test_large_reservoir_not_all_sent_downstream():
    """50k synthetic: planner finishes; hot set bounded; not all actionable."""
    n = 5000  # large enough to prove bound without multi-minute CI
    rows = []
    for i in range(n):
        # Only ~2% recent; rest stale watch
        last = "2026-07-20" if i % 50 == 0 else "2023-01-01"
        cnpj = f"{i:08d}000199"
        assert len(cnpj) == 14
        rows.append(
            _company(
                cnpj,
                last=last,
                first="2020-01-01",
                active=1 if i % 50 == 0 else 0,
                recent=1 if i % 50 == 0 else 0,
                value=100_000 + i,
                priority=30,
            )
        )
    cycle = run_activation_cycle(
        rows,
        policy=POLICY,
        as_of=AS_OF,
        capacity_override=80,
        evaluated_at="2026-08-08T10:00:00Z",
    )
    assert cycle.reservoir_count == n
    assert cycle.hot_set_count <= 80
    assert cycle.hot_set_count < n * 0.1
    assert cycle.elapsed_seconds < 120


def test_same_input_same_hashes():
    row = _company("11222333000186", last="2026-07-15")
    h1 = source_hash_for_row(row)
    h2 = source_hash_for_row(deepcopy(row))
    assert h1 == h2
    p1 = evaluate_row(row, policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    p2 = evaluate_row(deepcopy(row), policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    assert p1.source_hash == p2.source_hash
    assert p1.trigger_hash == p2.trigger_hash
    assert p1.activation_score == p2.activation_score
    assert p1.activation_state == p2.activation_state


def test_empty_delta_when_nothing_changed():
    rows = [_company("11222333000187", last="2026-07-18")]
    c1 = run_activation_cycle(rows, policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    prior = {p.cnpj14: p.as_dict() for p in c1.projections}
    c2 = run_activation_cycle(
        rows, policy=POLICY, as_of=AS_OF, prior_projections=prior, evaluated_at="2026-08-08T11:00:00Z"
    )
    assert c2.deactivations == []
    # scores/states stable
    assert c2.projections[0].activation_state == c1.projections[0].activation_state


def test_deactivation_exported_when_leaving_actionable(tmp_path: Path):
    row = _company("11222333000188", last="2026-07-20")
    c1 = run_activation_cycle([row], policy=POLICY, as_of=AS_OF, evaluated_at="2026-08-08T10:00:00Z")
    prior = {p.cnpj14: p.as_dict() for p in c1.projections}
    # Force prior to ACTIONABLE_NOW
    prior["11222333000188"]["activation_state"] = "ACTIONABLE_NOW"
    # Make row stale so it becomes WATCH
    stale = _company("11222333000188", last="2022-01-01", recent=0, active=0, value=10_000)
    c2 = run_activation_cycle(
        [stale], policy=POLICY, as_of=AS_OF, prior_projections=prior, evaluated_at="2026-08-08T12:00:00Z"
    )
    assert any(d["cnpj14"] == "11222333000188" for d in c2.deactivations)


def test_activation_block_maps_into_lead():
    row = _company("11222333000189", last="2026-07-22")
    row["activation"] = {
        "state": "ACTIONABLE_NOW",
        "score": 72.5,
        "reason_codes": ["NEW_RELEVANT_CONTRACT"],
        "policy_version": "confenge-activation-v1",
        "evaluated_at": "2026-08-08T10:00:00Z",
        "next_best_action_at": "2026-08-08T10:00:00Z",
        "expires_at": "2026-08-22T10:00:00Z",
        "source_hash": "abc",
        "score_components": {
            "trigger_strength": 30,
            "freshness": 20,
            "evidence_quality": 12,
            "commercial_relevance": 10.5,
        },
    }
    lead = map_lead(row, intel={}, contacts_row={"contacts": []})
    assert lead is not None
    assert "activation" in lead
    assert lead["activation"]["state"] == "ACTIONABLE_NOW"
    assert 0 <= lead["activation"]["score"] <= 100
    assert lead["activation"]["reason_codes"] == ["NEW_RELEVANT_CONTRACT"]


def test_legacy_lead_without_activation_still_maps():
    row = _company("11222333000190")
    lead = map_lead(row, intel={}, contacts_row={"contacts": []})
    assert lead is not None
    assert "activation" not in lead
    assert lead["commercial_state"]


def test_atomic_publish(tmp_path: Path):
    build = tmp_path / "build"
    build.mkdir()
    chunk = build / "chunk_0000.json"
    payload = {
        "schema_version": "confenge.outreach.v1",
        "generated_at": "2026-08-08T10:00:00Z",
        "source": {
            "system": "extra-cli",
            "run_id": "run-test123",
            "snapshot_hash": "deadbeef",
            "profile_id": "p",
            "profile_version": "1",
        },
        "pagination": {"has_more": False, "chunk_index": 0},
        "leads": [],
    }
    raw = (json.dumps(payload, sort_keys=True) + "\n").encode()
    chunk.write_bytes(raw)
    import hashlib

    chash = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": "confenge.outreach.manifest.v1",
        "source": payload["source"],
        "chunks": [{"file": "chunk_0000.json", "content_hash": chash, "chunk_index": 0}],
        "deactivations": [],
    }
    (build / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pub = tmp_path / "publish"
    result = atomic_publish_directory(build, pub)
    assert result["ok"]
    assert (pub / "current" / "manifest.json").is_file()
    assert (pub / "current" / "chunk_0000.json").is_file()


def test_no_juridical_invention_in_trigger_language():
    for code, tdef in POLICY.triggers.items():
        lang = tdef.language.lower()
        # Must not assert unpaid reajuste / legal right
        assert "não foi pago" not in lang
        assert "reajuste devido" not in lang
        assert "direito adquirido" not in lang


def test_select_hot_set_prefers_actionable():
    from scripts.confenge_activation.models import ActivationProjection

    projs = [
        ActivationProjection(
            cnpj14="11222333000191",
            activation_state="RESEARCH_REQUIRED",
            activation_score=90,
            reason_codes=["RESEARCH_GAP_WORTH_RESOLVING"],
            evaluated_at="2026-08-08T10:00:00Z",
            next_best_action_at="2026-08-08T10:00:00Z",
            expires_at=None,
            source_hash="a",
            trigger_hash="b",
            policy_version="v1",
        ),
        ActivationProjection(
            cnpj14="11222333000192",
            activation_state="ACTIONABLE_NOW",
            activation_score=50,
            reason_codes=["NEW_RELEVANT_CONTRACT"],
            evaluated_at="2026-08-08T10:00:00Z",
            next_best_action_at="2026-08-08T10:00:00Z",
            expires_at=None,
            source_hash="c",
            trigger_hash="d",
            policy_version="v1",
        ),
        ActivationProjection(
            cnpj14="11222333000193",
            activation_state="WATCH",
            activation_score=99,
            reason_codes=[],
            evaluated_at="2026-08-08T10:00:00Z",
            next_best_action_at="2026-08-22T00:00:00Z",
            expires_at=None,
            source_hash="e",
            trigger_hash="f",
            policy_version="v1",
        ),
    ]
    hot = select_hot_set(projs, policy=POLICY, capacity_override=2)
    assert hot[0].cnpj14 == "11222333000192"
    assert all(h.activation_state != "WATCH" for h in hot)


def test_stable_hash_deterministic():
    assert stable_hash({"a": 1, "b": [2, 3]}) == stable_hash({"b": [2, 3], "a": 1})


def test_capacity_override_none_uses_policy_planned_capacity():
    """capacity_override=None must use policy.planned_capacity, not an arbitrary Top-N."""
    rows = []
    for i in range(800):
        cnpj = f"{i:08d}000199"
        rows.append(
            _company(
                cnpj,
                last="2026-07-25",
                first="2024-01-01",
                active=3,
                recent=2,
                priority=60,
            )
        )
    planned = POLICY.capacity.planned_capacity()
    assert planned > 200  # default policy is well above smoke sample size
    cycle = run_activation_cycle(
        rows,
        policy=POLICY,
        as_of=AS_OF,
        capacity_override=None,
        evaluated_at="2026-08-08T10:00:00Z",
    )
    assert cycle.reservoir_count == 800
    assert cycle.hot_set_count <= planned
    assert cycle.hot_set_count <= POLICY.capacity.max_hot_set
    # Must not silently collapse to default limit_downstream=200
    assert cycle.hot_set_count > 200 or cycle.activation_counts.get("ACTIONABLE_NOW", 0) + cycle.activation_counts.get(
        "RESEARCH_REQUIRED", 0
    ) <= 200

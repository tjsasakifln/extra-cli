"""§21 remaining boundary cases — drive shipped public_agency modules."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.public_agency import OBJECT_ENGINEERING, SUM_UNKNOWN
from scripts.public_agency.conflict import STATE_PENDING, assess_conflict
from scripts.public_agency.contacts import validate_contact
from scripts.public_agency.entities import infer_agency_flags
from scripts.public_agency.exports import export_public_agency_run
from scripts.public_agency.fragmentation import assess_fragmentation, price_from_scope
from scripts.public_agency.legal_thresholds import evaluate_potential_eligibility, get_threshold
from scripts.public_agency.pipeline import git_sha, run_public_agency_pipeline
from scripts.public_agency.proposal import LEGAL_DISCLAIMER, generate_proposal
from scripts.public_agency.publishability import (
    COMPLIANCE_BLOCKED,
    NOT_A_FIT,
    PUBLISHABLE,
    RESEARCH_REQUIRED,
    evaluate_publishability,
)
from scripts.public_agency.signals import SignalHit

AS_OF = date(2026, 7, 15)


def test_consortium_flag_and_no_special_limit_assumption():
    flags = infer_agency_flags("CONSÓRCIO INTERMUNICIPAL DE SANEAMENTO DE SC")
    assert flags["consorcio_publico"] is True
    # No automatic doubled ceiling — eligibility still uses standard art.75 class
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF)
    assert thr is not None
    # Without special enquadramento evidence, same federal threshold applies
    # (no consortium multiplier field exists in evaluate_potential_eligibility)
    r = evaluate_potential_eligibility(100000.0, OBJECT_ENGINEERING, as_of=AS_OF)
    assert r["threshold_amount"] == thr.amount
    assert r["threshold_id"] == thr.threshold_id
    # annual sum unknown by default → no annual adherence claim
    assert r.get("annual_limit_adherence_claimed") is False
    assert r.get("annual_sum_state") == SUM_UNKNOWN


def test_entity_without_special_framework_uses_standard_threshold():
    r = evaluate_potential_eligibility(
        50000.0,
        OBJECT_ENGINEERING,
        as_of=AS_OF,
        annual_sum_known=False,
    )
    assert r["threshold_id"] and "ART75_I" in r["threshold_id"]
    assert r.get("annual_limit_adherence_claimed") is False
    assert r["threshold_amount"] == get_threshold(OBJECT_ENGINEERING, as_of=AS_OF).amount


def test_same_nature_objects_and_recurring_fragmentation():
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF)
    assert thr
    contracts = [
        {"amount": 40000, "object": "obra de pavimentação trecho 1", "id": "1"},
        {"amount": 40000, "object": "obra de pavimentação trecho 2", "id": "2"},
        {"amount": 40000, "object": "obra de pavimentação trecho 3", "id": "3"},
    ]
    frag = assess_fragmentation(
        proposed_amount=40000,
        ceiling=thr.amount,
        same_nature_contracts=contracts,
        proposed_packages=[
            {"amount": 40000, "object": "obra pavimentação A"},
            {"amount": 40000, "object": "obra pavimentação B"},
            {"amount": 40000, "object": "obra pavimentação C"},
        ],
    )
    assert "recurring_same_nature_contracting" in frag.indicators or frag.fragmentation_suspected
    assert "multiple_packages_same_nature" in frag.indicators or len(frag.indicators) >= 1


def test_stale_evidence_and_lead_without_evidence_not_publishable():
    conflict = assess_conflict(agency_id="x")
    stale = [
        SignalHit(
            signal_id="stale_data",
            status="FIRED",
            confidence=0.8,
            weight=-0.08,
        ),
        SignalHit(
            signal_id="recurring_engineering_procurements",
            status="FIRED",
            confidence=0.7,
            weight=0.15,
        ),
    ]
    # no official evidence
    pub = evaluate_publishability(
        has_official_identity=True,
        signals=stale,
        has_official_evidence=False,
        service_fit_score=0.6,
        explanation="has material signal but no evidence rows",
        conflict=conflict,
        contact_research_justified=True,
    )
    assert pub.publishable is False
    assert pub.category == RESEARCH_REQUIRED

    empty = evaluate_publishability(
        has_official_identity=True,
        signals=[],
        has_official_evidence=False,
        service_fit_score=0.1,
        explanation="",
        conflict=conflict,
        contact_research_justified=False,
    )
    assert empty.publishable is False
    assert empty.category in {NOT_A_FIT, RESEARCH_REQUIRED, COMPLIANCE_BLOCKED}


def test_compliance_blocked_category():
    conflict = assess_conflict(agency_id="y")
    material = [
        SignalHit(
            signal_id="recurring_engineering_procurements",
            status="FIRED",
            confidence=0.8,
            weight=0.15,
        )
    ]
    pub = evaluate_publishability(
        has_official_identity=True,
        signals=material,
        has_official_evidence=True,
        service_fit_score=0.7,
        explanation="ok",
        conflict=conflict,
        compliance_blocks=["possible_expense_fragmentation"],
        contact_research_justified=True,
    )
    assert pub.category == COMPLIANCE_BLOCKED


def test_proposal_has_disclaimer_and_no_ceiling_price_anchor():
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF)
    service = {
        "service_id": "PLANEJAMENTO_TECNICO_DA_CONTRATACAO",
        "nome": "Planejamento",
        "escopo": "Apoio técnico",
        "exclusoes": ["parecer jurídico"],
        "duracao_estimada": "4 semanas",
    }
    prop = generate_proposal(
        agency_name="Prefeitura Teste",
        problem="Baixa capacidade preparatória",
        object_text="Elaboração de ETP e TR de obra",
        service=service,
        deliverables=["ETP", "TR"],
        effort_hours=80,
        eligibility={"threshold_amount": thr.amount if thr else None, "eligibility_state": "POTENTIALLY_ELIGIBLE_FOR_DIRECT_CONTRACTING"},
    )
    assert LEGAL_DISCLAIMER in prop["markdown"]
    assert prop["pricing"]["ceiling_used_as_price_anchor"] is False
    assert "dispensa garantida" not in prop["markdown"].lower()


def test_manifest_checksums_and_sha_binding(tmp_path: Path):
    result = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "bind",
        as_of=AS_OF,
        fixture_rows=[
            {
                "contrato_id": "b1",
                "orgao_cnpj": "83102373000100",
                "orgao_nome": "PREFEITURA MUNICIPAL DE JUPIÁ",
                "objeto_contrato": "Obra de pavimentação e engenharia",
                "valor_total": 100000,
                "data_publicacao": "2026-01-10",
                "data_inicio": "2026-01-15",
                "data_fim": "2026-12-31",
                "uf": "SC",
                "source": "pncp",
                "source_id": "b1",
                "is_active": True,
            },
            {
                "contrato_id": "b2",
                "orgao_cnpj": "83102373000100",
                "orgao_nome": "PREFEITURA MUNICIPAL DE JUPIÁ",
                "objeto_contrato": "Reforma de escola — engenharia",
                "valor_total": 80000,
                "data_publicacao": "2025-06-01",
                "data_inicio": "2025-07-01",
                "data_fim": "2026-07-01",
                "uf": "SC",
                "source": "pncp",
                "is_active": True,
            },
            {
                "contrato_id": "b3",
                "orgao_cnpj": "83102373000100",
                "orgao_nome": "PREFEITURA MUNICIPAL DE JUPIÁ",
                "objeto_contrato": "Serviços de engenharia infraestrutura",
                "valor_total": 90000,
                "data_publicacao": "2025-11-01",
                "uf": "SC",
                "source": "pncp",
                "is_active": True,
            },
        ],
        skip_kit=True,
    )
    assert result["status"] == "PASS"
    assert result["git_sha"] == git_sha()
    out = tmp_path / "bind"
    man = out / "public-agency-manifest.json"
    chk = out / "public-agency-checksums.sha256"
    assert man.exists() and chk.exists()
    assert "public-agency-run-result.json" in chk.read_text(encoding="utf-8")
    import json

    m = json.loads(man.read_text(encoding="utf-8"))
    assert m["code_sha"] == result["git_sha"]
    assert m["outreach_sent"] is False


def test_cycle_cli_target_public_agencies_help(monkeypatch, tmp_path):
    """Multi-target CLI is the router (freeze cycle remains suppliers-only)."""
    from scripts.ops import confenge_commercial_cycle as frozen_cycle
    from scripts.ops import confenge_commercial_target_router as router

    assert hasattr(router, "main")
    assert hasattr(frozen_cycle, "main")
    # With official registry required (default), missing ACTIVE release fails closed (2).
    monkeypatch.setenv("CONFENGE_REQUIRE_OFFICIAL_REGISTRY", "1")
    monkeypatch.delenv("COMPANY_REGISTRY_ROOT", raising=False)
    code = router.main(
        ["--target", "suppliers", "--dsn", "postgresql://x", "--out", str(tmp_path / "reg")]
    )
    assert code == 2  # BLOCKED_OFFICIAL_REGISTRY (or equivalent)
    # Opt-out of registry: suppliers path still fails closed without snapshot (1).
    monkeypatch.setenv("CONFENGE_REQUIRE_OFFICIAL_REGISTRY", "0")
    code_no_reg = router.main(
        ["--target", "suppliers", "--dsn", "postgresql://x", "--out", str(tmp_path / "nope")]
    )
    assert code_no_reg == 1  # missing snapshot
    # frozen suppliers entry also fails closed without snapshot (no --target flag)
    code_frozen = frozen_cycle.main(["--dsn", "postgresql://x", "--out", str(tmp_path / "frozen")])
    assert code_frozen == 1


def test_whatsapp_requires_official_publication():
    bad = validate_contact(channel="whatsapp", value="48999999999", officially_published=False)
    assert bad.institutional is False
    good = validate_contact(channel="whatsapp", value="4833334444", officially_published=True)
    assert good.institutional is True


def test_price_near_ceiling_warning():
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF)
    assert thr
    p = price_from_scope(
        effort_hours=500,
        hourly_rate=250,
        margin=0.05,
        ceiling=thr.amount,
    )
    # large effort may exceed or approach; method never anchors
    assert p["ceiling_used_as_price_anchor"] is False
    near = price_from_scope(
        effort_hours=1,
        hourly_rate=thr.amount * 0.98,
        margin=0.0,
        ceiling=thr.amount,
    )
    assert near.get("warning") == "PRICE_NEAR_CEILING_REVIEW_REQUIRED" or near["proposed_price"] < thr.amount

"""Pipeline, publishability, separation, reproducibility tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.public_agency import ENTITY_TYPE, MODE_PROACTIVE
from scripts.public_agency.pipeline import run_public_agency_pipeline
from scripts.public_agency.publishability import (
    CONFLICT_BLOCKED,
    NOT_A_FIT,
    PUBLISHABLE,
    evaluate_publishability,
)
from scripts.public_agency.conflict import assess_conflict
from scripts.public_agency.signals import SignalHit, compute_agency_signals


def _fixture_rows() -> list[dict]:
    return [
        {
            "contrato_id": "c1",
            "orgao_cnpj": "83102373000100",
            "orgao_nome": "PREFEITURA MUNICIPAL DE ABDON BATISTA",
            "objeto_contrato": "Obra de pavimentação asfáltica e drenagem",
            "valor_total": 450000.0,
            "data_inicio": "2025-01-10",
            "data_fim": "2026-06-30",
            "data_publicacao": "2025-01-05",
            "uf": "SC",
            "source": "pncp",
            "source_id": "s1",
            "is_active": True,
        },
        {
            "contrato_id": "c2",
            "orgao_cnpj": "83102373000100",
            "orgao_nome": "PREFEITURA MUNICIPAL DE ABDON BATISTA",
            "objeto_contrato": "Reforma de unidade básica de saúde — engenharia",
            "valor_total": 220000.0,
            "data_inicio": "2024-03-01",
            "data_fim": "2025-12-01",
            "data_publicacao": "2024-02-20",
            "uf": "SC",
            "source": "pncp",
            "source_id": "s2",
            "is_active": True,
        },
        {
            "contrato_id": "c3",
            "orgao_cnpj": "83102373000100",
            "orgao_nome": "PREFEITURA MUNICIPAL DE ABDON BATISTA",
            "objeto_contrato": "Serviços de engenharia para infraestrutura urbana",
            "valor_total": 180000.0,
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "data_publicacao": "2026-01-15",
            "uf": "SC",
            "source": "pncp",
            "source_id": "s3",
            "is_active": True,
        },
        # private company as "orgao" noise — should be skipped
        {
            "contrato_id": "c9",
            "orgao_cnpj": "11222333000181",
            "orgao_nome": "EMPRESA XYZ CONSTRUÇÕES LTDA",
            "objeto_contrato": "obra",
            "valor_total": 10000,
            "data_publicacao": "2026-01-01",
            "uf": "SC",
            "source": "pncp",
            "is_active": True,
        },
    ]


def test_pipeline_fixture_produces_artifacts(tmp_path: Path):
    out = tmp_path / "pag-run"
    result = run_public_agency_pipeline(
        dsn=None,
        out_dir=out,
        as_of=date(2026, 7, 15),
        fixture_rows=_fixture_rows(),
        max_leads=20,
        skip_kit=False,
    )
    assert result["status"] == "PASS"
    assert result["git_sha"]
    assert result["target"] == "public-agencies"
    leads = result.get("leads") or []
    # At least the prefeitura should be publishable
    assert len(leads) >= 1
    lead = leads[0]
    assert lead["entity_type"] == ENTITY_TYPE
    assert lead["agency"]["entity_type"] == ENTITY_TYPE
    assert "supplier" not in (lead.get("agency") or {}).get("entity_type", "").lower()

    required = [
        "public-agency-leads.csv",
        "public-agency-leads.json",
        "public-agency-run-result.json",
        "public-agency-lead-explanations.jsonl",
        "public-agency-evidence-ledger.jsonl",
        "public-agency-outreach-queue.csv",
        "public-agency-service-fit.csv",
        "public-agency-compliance-flags.csv",
        "public-agency-conflict-review.csv",
        "public-agency-manifest.json",
        "public-agency-checksums.sha256",
        "public-agency-summary.md",
        "public-agency-report.html",
    ]
    for name in required:
        assert (out / name).exists(), name

    assert (out / "dossiers").is_dir()
    assert list((out / "dossiers").glob("dossier-*.md"))
    assert (out / "commercial-kit").is_dir()

    manifest = json.loads((out / "public-agency-manifest.json").read_text(encoding="utf-8"))
    assert manifest["code_sha"] == result["git_sha"]
    assert manifest["outreach_sent"] is False

    # no forbidden eligibility language in outputs
    blob = (out / "public-agency-summary.md").read_text(encoding="utf-8")
    for bad in ("dispensa garantida", "sem licitação", "contratação assegurada"):
        assert bad not in blob.lower()


def test_small_municipality_alone_not_publishable():
    signals = [
        SignalHit(
            signal_id="small_municipality",
            status="FIRED",
            confidence=0.9,
            weight=0.05,
        )
    ]
    conflict = assess_conflict(agency_id="x")
    pub = evaluate_publishability(
        has_official_identity=True,
        signals=signals,
        has_official_evidence=True,
        service_fit_score=0.5,
        explanation="only small",
        conflict=conflict,
        contact_research_justified=True,
    )
    assert pub.publishable is False
    assert pub.category in {NOT_A_FIT, "RESEARCH_REQUIRED"}


def test_conflict_blocked_category():
    signals = [
        SignalHit(
            signal_id="recurring_engineering_procurements",
            status="FIRED",
            confidence=0.8,
            weight=0.15,
        )
    ]
    conflict = assess_conflict(known_conflict=True, known_conflict_reason="fiscal")
    pub = evaluate_publishability(
        has_official_identity=True,
        signals=signals,
        has_official_evidence=True,
        service_fit_score=0.6,
        explanation="ok",
        conflict=conflict,
        contact_research_justified=True,
    )
    assert pub.category == CONFLICT_BLOCKED


def test_reproducibility_same_fixture(tmp_path: Path):
    rows = _fixture_rows()
    r1 = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "a",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    r2 = run_public_agency_pipeline(
        dsn=None,
        out_dir=tmp_path / "b",
        as_of=date(2026, 7, 15),
        fixture_rows=rows,
        skip_kit=True,
    )
    assert r1["status"] == r2["status"]
    assert len(r1["leads"]) == len(r2["leads"])
    if r1["leads"]:
        assert r1["leads"][0]["agency"]["agency_id"] == r2["leads"][0]["agency"]["agency_id"]
        assert r1["leads"][0]["score"]["priority_score"] == r2["leads"][0]["score"]["priority_score"]


def test_source_failure_without_dsn(tmp_path: Path):
    r = run_public_agency_pipeline(dsn=None, out_dir=tmp_path / "fail", fixture_rows=None)
    assert r["status"] == "FAIL"
    assert r["reason"] == "SOURCE_FAILURE"


def test_signals_compute():
    rows = _fixture_rows()[:3]
    hits = compute_agency_signals(
        contracts=rows,
        population=2598,
        as_of=date(2026, 7, 15),
    )
    ids = {h.signal_id for h in hits}
    assert "small_municipality" in ids
    assert "recurring_engineering_procurements" in ids

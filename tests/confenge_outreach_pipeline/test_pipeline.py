"""Pipeline orchestrator: fixture path chains all stages without manual JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.confenge_outreach_pipeline.adapt import (
    contact_resolution_to_bridge_row,
    intelligence_dossier_to_bridge_row,
    universe_row_to_intelligence_input,
)
from scripts.confenge_outreach_pipeline.cli import main as cli_main
from scripts.confenge_outreach_pipeline.pipeline import PipelineConfig, run_pipeline
from scripts.confenge_outreach_pipeline.sample import classify_profile, select_diverse_sample
from scripts.warmbly_bridge.mapping import build_leads


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CSV = ROOT / "tests" / "fixtures" / "confenge_universe" / "contracts_sample.csv"
DNC_TXT = ROOT / "tests" / "fixtures" / "confenge_universe" / "dnc.txt"


def test_limit_downstream_does_not_shrink_universe(tmp_path: Path) -> None:
    """Universe discovery runs fully; only expensive batch is limited."""
    out = tmp_path / "run"
    result = run_pipeline(
        PipelineConfig(
            out_dir=out,
            csv_path=str(FIXTURE_CSV),
            dnc_path=str(DNC_TXT) if DNC_TXT.is_file() else None,
            as_of=__import__("datetime").date(2026, 8, 1),
            limit_downstream=1,
            max_workers=1,
            skip_contacts=True,
            progress=False,
        )
    )
    assert result.ok, result.errors
    universe_total = result.stages["universe_row_count"]
    assert universe_total >= 1
    # Sample/hot set is capped by limit_downstream (batch only)
    assert result.stages["sample"]["count"] == 1
    assert result.stages["sample"]["count"] <= universe_total
    # limit_downstream must NOT change universe_total
    assert result.stages["manifest_summary"]["universe_total"] == universe_total
    assert result.stages["manifest_summary"]["limit_downstream_is_batch_only"] is True
    # Intelligence only for sample
    assert result.stages["account_intelligence"]["count"] == 1
    # Feed produced (or empty-ok)
    feed = result.stages["feed"]
    assert feed.get("ok") is True
    assert feed.get("lead_count") == 1
    # Manifest records sampling flags honestly
    assert result.stages.get("sampling") is False  # no max_rows on universe
    assert result.stages.get("full_scale_universe") is False  # csv path
    # Checkpoint written for resume
    assert (out / "pipeline-checkpoint.json").is_file()


def test_cli_run_fixture_end_to_end(tmp_path: Path) -> None:
    out = tmp_path / "cli_out"
    code = cli_main(
        [
            "run",
            "--csv",
            str(FIXTURE_CSV),
            "--out",
            str(out),
            "--as-of",
            "2026-08-01",
            "--limit-downstream",
            "5",
            "--max-workers",
            "2",
            "--skip-contacts",
        ]
    )
    assert code == 0
    manifest = out / "reports" / "pipeline-manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["limit_downstream"] == 5
    assert data["account_intelligence"]["count"] >= 1
    assert "service_distribution" in data["account_intelligence"]
    # At least one feed chunk exists
    feed_dir = out / "06_warmbly_feed"
    chunks = list(feed_dir.glob("chunk_*.json"))
    assert chunks, "expected confenge.outreach.v1 chunk files"
    feed = json.loads(chunks[0].read_text(encoding="utf-8"))
    assert feed["schema_version"] == "confenge.outreach.v1"
    assert feed["leads"]
    lead = feed["leads"][0]
    assert lead["company"]["cnpj14"]
    assert "offer" in lead
    assert "messaging_context" in lead
    # Service chosen by intelligence, not blank for companies with contracts
    # (may be discovery for thin portfolios — still must be a string)
    assert isinstance(lead["offer"].get("service_code"), str)


def test_diverse_sample_not_pure_top_score() -> None:
    rows = []
    # High score mid-market
    for i in range(10):
        rows.append(
            {
                "cnpj14": f"11222333{i:04d}81"[:14].ljust(14, "0"),
                "priority_score": 90 - i,
                "outreach_eligibility": "ELIGIBLE",
                "portfolio": {
                    "contract_count_total": 5,
                    "value_total_brl": 1_000_000,
                    "ufs_atuacao": ["SC", "PR"],
                },
            }
        )
    # Low score regional lean — must still appear when limit allows diversity
    rows.append(
        {
            "cnpj14": "99888777000166",
            "priority_score": 5,
            "outreach_eligibility": "ELIGIBLE",
            "portfolio": {
                "contract_count_total": 2,
                "value_total_brl": 100_000,
                "ufs_atuacao": ["SC"],
            },
        }
    )
    # Few contracts
    rows.append(
        {
            "cnpj14": "55444333000122",
            "priority_score": 3,
            "outreach_eligibility": "ELIGIBLE",
            "portfolio": {
                "contract_count_total": 1,
                "value_total_brl": 50_000,
                "ufs_atuacao": ["RS"],
            },
        }
    )
    sample = select_diverse_sample(rows, limit=5)
    profiles = {r.get("_sample_profile") or classify_profile(r) for r in sample}
    assert "regional_lean" in profiles or "few_contracts" in profiles
    assert len(sample) == 5


def test_adapt_intelligence_and_contacts_join() -> None:
    universe = {
        "cnpj14": "11222333000181",
        "cnpj_root": "11222333",
        "razao_social": "ACME",
        "municipio": "Florianopolis",
        "uf": "SC",
        "outreach_eligibility": "ELIGIBLE",
        "priority_score": 70,
        "portfolio": {
            "contract_count_total": 2,
            "value_total_brl": 500_000,
            "ufs_atuacao": ["SC"],
            "recent_contracts": [
                {
                    "contrato_id": "C-1",
                    "objeto": "Pavimentacao",
                    "valor_total": 250_000,
                    "data_publicacao": "2024-03-01",
                    "data_fim": "2025-12-31",
                    "uf": "SC",
                    "orgao_nome": "Pref Joinville",
                }
            ],
        },
    }
    intel_in = universe_row_to_intelligence_input(universe, as_of="2026-08-01")
    assert intel_in["contracts"]
    assert intel_in["cnpj14"] == "11222333000181"

    dossier = {
        "schema_id": "confenge-account-intelligence-v1",
        "account_snapshot": {
            "cnpj14": "11222333000181",
            "cnpj_root": "11222333",
            "razao_social": "ACME",
        },
        "primary_service": {
            "service_id": "gestao_monitoramento_contratual",
            "label": "Gestao contratual",
            "approach_mode": "diagnostico_focal",
        },
        "why_now": {
            "trigger": "portfolio_review",
            "temporal_fact": "Portfólio observável",
            "epistemic_class": "strong_inference",
        },
        "fact_to_mention": "Contrato de pavimentacao no PNCP",
        "question_to_ask": "Pergunta?",
        "cta": "CTA",
        "claims_to_avoid": ["garantia de economia"],
        "confirmed_facts": [
            {
                "id": "cf-1",
                "text": "Contrato C-1 publicado",
                "epistemic_class": "confirmed",
            }
        ],
        "strong_inferences": [],
        "weak_inferences": [],
        "service_fit_rationale": "Portfólio multi-contrato",
        "dominant_state": {"state": "NEW"},
        "generated_at": "2026-08-01T00:00:00Z",
        "as_of": "2026-08-01",
    }
    bridge_intel = intelligence_dossier_to_bridge_row(dossier)
    assert bridge_intel["offer"]["service_code"] == "gestao_monitoramento_contratual"
    assert bridge_intel["messaging"]["fact_to_mention"]

    resolution = {
        "cnpj14": "11222333000181",
        "candidates": [
            {
                "candidate_id": "ct-1",
                "name": "Ana Silva",
                "cargo": "Engenheira de contratos",
                "email": "ana@acme.example.com",
                "phone_e164": "",
                "verification_status": "OBSERVED",
                "confidence": 0.9,
                "recommended": True,
                "source": {"source_url": "https://acme.example.com/equipe"},
            }
        ],
        "recommended_candidate_id": "ct-1",
    }
    bridge_contacts = contact_resolution_to_bridge_row(resolution)
    assert bridge_contacts["contacts"][0]["role"] == "Engenheira de contratos"
    assert bridge_contacts["contacts"][0]["verification_status"] == "OFFICIAL_SOURCE"

    from scripts.confenge_outreach_pipeline.adapt import universe_row_for_bridge

    u = universe_row_for_bridge(universe, rank=1)
    leads = build_leads([u], [bridge_intel], [bridge_contacts])
    assert len(leads) == 1
    assert leads[0]["offer"]["service_code"] == "gestao_monitoramento_contratual"
    assert leads[0]["contacts"][0]["email"] == "ana@acme.example.com"
    assert leads[0]["messaging_context"]["fact_to_mention"]


def test_contract_schema_matches_warmbly_constants() -> None:
    """Producer schema_version equals Warmbly consumer constant."""
    schema_path = (
        ROOT / "scripts" / "warmbly_bridge" / "schemas" / "confenge.outreach.v1.json"
    )
    assert schema_path.is_file()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    # schema file may use $id; constant in package is authoritative
    from scripts.warmbly_bridge import SCHEMA_OUTREACH

    assert SCHEMA_OUTREACH == "confenge.outreach.v1"
    # properties expected by Warmbly Feed struct
    props = schema.get("properties") or schema
    # If JSON Schema, check required top-level
    if "properties" in schema:
        for key in ("schema_version", "source", "leads"):
            assert key in schema["properties"] or key in (schema.get("required") or [])

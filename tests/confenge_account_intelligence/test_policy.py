"""Policy tests: DO_NOT_CONTACT dominant, robust framing, offline enrich."""

from __future__ import annotations

from scripts.confenge_account_intelligence.enrich import NoOpEnrichProvider
from scripts.confenge_account_intelligence.pipeline import build_dossier, process_batch


def test_do_not_contact_dominant(do_not_contact: dict) -> None:
    d = build_dossier(do_not_contact)
    dom = d["dominant_state"]
    assert dom["state"] == "DO_NOT_CONTACT"
    assert dom["is_dominant"] is True
    assert dom["blocks_outreach"] is True
    # Still produces an approach angle (not qualify/disqualify-only product)
    assert d["primary_service"]["service_id"]
    assert d["cta"]
    assert any("DO_NOT_CONTACT" in lim or "outreach" in lim.lower() for lim in d["limitations"])


def test_robust_not_full_outsource(national_structured: dict) -> None:
    d = build_dossier(national_structured)
    assert d["primary_service"]["service_id"] != "reforco_temporario_backoffice"
    mode = d["primary_service"]["approach_mode"]
    assert "outsourcing_operacional" not in mode
    # Prefer independent review framing
    assert d["primary_service"]["service_id"] in {
        "auditoria_orcamento_bdi",
        "diagnostico_contratual_b2g",
        "gestao_monitoramento_contratual",
    }


def test_noop_enrich_does_not_mutate_or_network(regional_lean: dict) -> None:
    original = dict(regional_lean)
    provider = NoOpEnrichProvider()
    out = provider.enrich(regional_lean)
    assert out == original
    assert out is not regional_lean  # shallow copy
    d = build_dossier(regional_lean, enricher=provider)
    assert d["schema_id"] == "confenge-account-intelligence-v1"


def test_batch_preserves_order_and_concurrency(
    regional_lean: dict,
    insufficient_facts: dict,
    addendum_signals: dict,
) -> None:
    records = [regional_lean, insufficient_facts, addendum_signals]
    out = process_batch(records, max_workers=3)
    assert len(out) == 3
    assert out[0]["account_snapshot"]["razao_social"] == regional_lean["razao_social"]
    assert out[1]["primary_service"]["service_id"] == "diagnostico_contratual_b2g"
    assert out[2]["primary_service"]["service_id"] == "aditivos_extracontratuais"

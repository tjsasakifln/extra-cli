"""Mandatory regime hierarchy tests (R-A…R-X) and human-review completeness.

Exercises shipped classify_legal_regime + evaluate_commercial_stage +
load_human_review_file — not re-implemented copies.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.commercial.reajuste_14133 import (
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    POTENTIAL_ADJUSTMENT_SIGNAL,
    REGIME_14133,
    REGIME_8666,
    REGIME_LIKELY_14133,
    REGIME_TRANSITIONAL_UNRESOLVED,
    REGIME_UNKNOWN,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)
from scripts.commercial.reajuste_14133.domain.commercial_stages import (
    MSG_REGIME_LIKELY,
    MSG_REGIME_PROVEN,
    MSG_REGIME_UNRESOLVED,
    evaluate_commercial_stage,
    regime_probable_14133,
)
from scripts.commercial.reajuste_14133.domain.regime import classify_legal_regime
from scripts.commercial.reajuste_14133.io.human_review import (
    human_review_done_for,
    load_human_review_file,
)
from scripts.commercial.reajuste_14133.pipeline import classify_row

AS_OF = date(2026, 8, 4)


def test_year_alone_never_probable_14133():
    r = classify_legal_regime(signature_year=2023, published_on_pncp=True)
    assert r.regime in {REGIME_UNKNOWN, REGIME_TRANSITIONAL_UNRESOLVED}
    assert r.proven is False
    assert r.regime != REGIME_LIKELY_14133
    assert r.regime != REGIME_14133
    assert not regime_probable_14133(
        regime=r.regime, regime_proven=r.proven, signature_year=2023
    )


def test_pncp_publication_never_proves_regime():
    r = classify_legal_regime(published_on_pncp=True, signature_year=2024)
    assert r.proven is False
    assert "PNCP" in r.notes or any("PNCP" in c for c in r.chronological_context)
    assert r.regime != REGIME_14133 or not r.proven


def test_2022_under_8666_blocks_14133_outreach():
    """Signature after 14.133 entry into force + official 8.666 doc → legacy."""
    r = classify_legal_regime(
        document_texts=["Contrato regido pela Lei nº 8.666/1993, art. 55"],
        signature_year=2022,
        published_on_pncp=True,
    )
    assert r.regime == REGIME_8666
    assert r.proven is True
    assert r.regime != REGIME_LIKELY_14133

    stage = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=r.regime,
        regime_proven=r.proven,
        signature_year=2022,
        data_assinatura=date(2022, 6, 1),
        open_obligation=True,
        contact_verifiable=True,
    )
    assert stage.commercial_stage not in {
        LIKELY_ADJUSTMENT_OPPORTUNITY,
        DIAGNOSTIC_OUTREACH_READY,
        VERIFIED_ADJUSTMENT_OPPORTUNITY,
    }
    assert stage.regime_probable_14133 is False
    assert stage.diagnostic_outreach_allowed is False


def test_2023_unknown_mature_obra_is_signal_or_doc_request():
    """Mature obra, unknown regime → SIGNAL or DOCUMENT_REQUEST, never LIKELY."""
    r = classify_legal_regime(signature_year=2023)
    assert r.regime in {REGIME_UNKNOWN, REGIME_TRANSITIONAL_UNRESOLVED}

    stage = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=r.regime,
        regime_proven=False,
        signature_year=2023,
        data_assinatura=date(2023, 3, 15),
        open_obligation=True,
        contact_verifiable=False,
    )
    assert stage.commercial_stage in {
        POTENTIAL_ADJUSTMENT_SIGNAL,
        DOCUMENT_REQUEST_READY,
    }
    assert stage.commercial_stage != LIKELY_ADJUSTMENT_OPPORTUNITY
    assert stage.regime_probable_14133 is False
    lang = stage.language_allowed.lower()
    # Must not claim the contract is governed by Lei 14.133
    assert "regido pela lei 14.133" not in lang
    assert stage.diagnostic_outreach_allowed is False


def test_2024_contract_from_legacy_2023_edital_stays_legacy():
    """Signature year must not override origin process under 8.666."""
    r = classify_legal_regime(
        signature_year=2024,
        origin_edital_year=2023,
        origin_document_texts=[
            "Edital de licitação regido pela Lei nº 8.666/1993"
        ],
        published_on_pncp=True,
    )
    assert r.regime == REGIME_8666
    assert r.proven is True
    assert "signature_year_does_not_override" in r.reason_codes

    # Also: origin year pre-2021 without text
    r2 = classify_legal_regime(
        signature_year=2024,
        origin_process_year=2020,
        published_on_pncp=True,
    )
    assert r2.regime == REGIME_8666
    assert r2.proven is True


def test_post_transition_proven_14133_can_reach_likely_or_diagnostic():
    r = classify_legal_regime(
        document_texts=[
            "Contrato administrativo regido pela Lei nº 14.133/2021, art. 92"
        ],
        signature_year=2024,
        origin_edital_year=2024,
        initiation_act_date=date(2024, 2, 1),
        document_link_validated=True,
        has_official_linked_document=True,
    )
    assert r.regime == REGIME_14133
    assert r.proven is True
    assert r.evidence_level == "R-A"
    assert r.legal_confidence == "high"

    stage = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=r.regime,
        regime_proven=r.proven,
        legal_confidence=r.legal_confidence,
        data_assinatura=date(2024, 3, 1),
        open_obligation=True,
        contact_verifiable=True,
    )
    assert stage.commercial_stage in {
        LIKELY_ADJUSTMENT_OPPORTUNITY,
        DIAGNOSTIC_OUTREACH_READY,
    }
    assert stage.regime_probable_14133 is True
    assert stage.message_template == "proven"


def test_convergent_likely_14133_never_proven():
    """R-B: post-transition official pack + validated link + no legacy → LIKELY_14133."""
    r = classify_legal_regime(
        document_texts=[
            "Termo de contrato vinculado ao processo SEI 123/2024. "
            "Modalidade: concorrência. Objeto: execução de obras de pavimentação."
        ],
        signature_year=2024,
        origin_edital_year=2024,
        initiation_act_date=date(2024, 1, 15),
        document_link_validated=True,
        has_official_linked_document=True,
        published_on_pncp=True,
    )
    assert r.regime == REGIME_LIKELY_14133
    assert r.proven is False
    assert r.evidence_level == "R-B"
    assert r.legal_confidence == "medium"

    stage = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=r.regime,
        regime_proven=r.proven,
        legal_confidence=r.legal_confidence,
        data_assinatura=date(2024, 4, 1),
        open_obligation=True,
        contact_verifiable=False,
    )
    assert stage.commercial_stage == LIKELY_ADJUSTMENT_OPPORTUNITY
    assert stage.regime_probable_14133 is True
    # Cannot be VERIFIED without proven regime
    verified = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=REGIME_LIKELY_14133,
        regime_proven=False,
        data_assinatura=date(2023, 5, 10),
        exact_budget_date=date(2023, 1, 20),
        open_obligation=True,
        clause_located=True,
        index_or_formula=True,
        docs_text_extracted=True,
        document_link_validated=True,
        human_review_done=True,
        contact_verifiable=True,
    )
    assert verified.commercial_stage != VERIFIED_ADJUSTMENT_OPPORTUNITY


def test_transitional_unresolved_explicit_state():
    r = classify_legal_regime(signature_year=2022)
    assert r.regime == REGIME_TRANSITIONAL_UNRESOLVED
    assert r.legal_confidence == "unresolved"
    assert r.evidence_level == "R-C"
    assert r.priority_documents

    stage = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=r.regime,
        regime_proven=False,
        legal_confidence=r.legal_confidence,
        signature_year=2022,
        data_assinatura=date(2022, 8, 1),
        open_obligation=True,
        contact_verifiable=True,
    )
    assert stage.commercial_stage in {
        DOCUMENT_REQUEST_READY,
        POTENTIAL_ADJUSTMENT_SIGNAL,
    }
    assert stage.dimensions.claim_readiness == "claim_blocked"
    assert stage.diagnostic_outreach_allowed is False
    assert stage.dimensions.commercial_action in {
        "request_legal_regime_documents",
        "request_documents",
        "intelligence_only",
    }


def test_human_review_incomplete_reviewer_decision_only(tmp_path: Path):
    path = tmp_path / "inc.json"
    path.write_text(
        """[
          {
            "contrato_id": "c-inc",
            "reviewer": "Tiago",
            "decision": "ACCEPT"
          }
        ]""",
        encoding="utf-8",
    )
    recs = load_human_review_file(path)
    assert recs["c-inc"]["human_review_completed"] is False
    assert recs["c-inc"]["human_review_status"] == "human_review_incomplete"
    assert not human_review_done_for(recs, contrato_id="c-inc")
    assert "documents_read" in recs["c-inc"]["missing_fields"]
    assert "reviewed_at" in recs["c-inc"]["missing_fields"]


def test_human_review_complete_allows_completed_flag(tmp_path: Path):
    path = tmp_path / "ok.json"
    path.write_text(
        """[
          {
            "contrato_id": "c-ok",
            "reviewer": "Tiago",
            "reviewed_at": "2026-08-05T12:00:00Z",
            "documents_read": ["contrato.pdf"],
            "pages": ["14"],
            "clauses": ["cláusula 8"],
            "regime_confirmed": "LEI_14133_2021",
            "data_base_confirmed": "2023-01-20",
            "index_confirmed": "INCC-DI",
            "prior_adjustment": "none_found",
            "document_link_validated": true,
            "decision": "ACCEPT",
            "notes": "Leitura completa do PDF oficial, cláusula e data-base confirmadas.",
            "confidence": "high"
          }
        ]""",
        encoding="utf-8",
    )
    recs = load_human_review_file(path)
    assert recs["c-ok"]["human_review_completed"] is True
    assert human_review_done_for(recs, contrato_id="c-ok")
    assert recs["c-ok"].get("can_promote_verified") is True


def test_message_templates_three_variants():
    assert "Lei 14.133" in MSG_REGIME_PROVEN
    assert "possível enquadramento" in MSG_REGIME_LIKELY or "possivel enquadramento" in MSG_REGIME_LIKELY
    # Unresolved must not claim 14.133 applies
    assert "regido pela Lei 14.133" not in MSG_REGIME_UNRESOLVED
    assert "confirmar o regime" in MSG_REGIME_UNRESOLVED


def test_pipeline_row_2024_legacy_edital():
    row = {
        "contrato_id": "org-1-000100/2024",
        "fornecedor_cnpj": "82743832000162",
        "fornecedor_nome": "PLANATERRA TERRAPLENAGEM E PAVIMENTACAO LTDA",
        "orgao_cnpj": "04892707000100",
        "orgao_nome": "DNIT",
        "objeto_contrato": (
            "Execução de obras de pavimentação asfáltica e drenagem "
            "na rodovia — empreitada por preço global"
        ),
        "valor_total": 8_000_000,
        "data_assinatura": "2024-02-10",
        "data_inicio": "2024-03-01",
        "data_fim": "2027-02-28",
        "uf": "SC",
        "is_active": True,
        "ano_edital": 2023,
        "edital_fundamento_legal": "Edital regido pela Lei nº 8.666/1993",
    }
    lead = classify_row(row, as_of=AS_OF, contacts={})
    assert lead["regime_legal"] == REGIME_8666
    assert lead["regime_proven"] is True
    assert lead["commercial_stage"] not in {
        LIKELY_ADJUSTMENT_OPPORTUNITY,
        DIAGNOSTIC_OUTREACH_READY,
    }
    assert lead["regime_probable_14133"] is False

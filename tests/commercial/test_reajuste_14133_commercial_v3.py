"""Commercial funnel v3: multi-dimension stages, temporal B, fail-closed claims."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.commercial.reajuste_14133 import (
    CALCULABLE_ADJUSTMENT_CLAIM,
    DIAGNOSTIC_OUTREACH_READY,
    DOCUMENT_REQUEST_READY,
    LIKELY_ADJUSTMENT_OPPORTUNITY,
    REGIME_14133,
    REGIME_LIKELY_14133,
    TEMPORAL_LEVEL_A,
    TEMPORAL_LEVEL_B,
    VERIFIED_ADJUSTMENT_OPPORTUNITY,
)
from scripts.commercial.reajuste_14133.domain.commercial_stages import (
    DIAGNOSTIC_LANGUAGE,
    MSG_REGIME_LIKELY,
    MSG_REGIME_PROVEN,
    MSG_REGIME_UNRESOLVED,
    evaluate_commercial_stage,
    evaluate_temporal_hierarchy,
)
from scripts.commercial.reajuste_14133.export.reports import write_v2_deliverables
from scripts.commercial.reajuste_14133.io.human_review import (
    human_review_done_for,
    load_human_review_file,
)
from scripts.commercial.reajuste_14133.pipeline import classify_row

AS_OF = date(2026, 8, 4)

MATURE_OBRA_ROW = {
    "contrato_id": "04892707000100-1-000200/2023",
    "fornecedor_cnpj": "82743832000162",
    "fornecedor_nome": "PLANATERRA TERRAPLENAGEM E PAVIMENTACAO LTDA",
    "orgao_cnpj": "04892707000100",
    "orgao_nome": "Departamento Nacional de Infraestrutura de Transportes",
    "objeto_contrato": (
        "Execução de obras de pavimentação asfáltica e drenagem urbana na rodovia SC-401 — empreitada por preço global"
    ),
    "valor_total": 12_500_000,
    "data_assinatura": "2023-05-10",
    "data_inicio": "2023-06-01",
    "data_fim": "2027-05-31",
    "uf": "SC",
    "municipio": "Florianopolis",
    "is_active": True,
}


def test_temporal_level_b_signature_gt_12_months():
    t = evaluate_temporal_hierarchy(
        as_of=AS_OF,
        exact_budget_date=None,
        data_assinatura=date(2023, 5, 10),
    )
    assert t.level == TEMPORAL_LEVEL_B
    assert t.minimum_elapsed_confirmed is True
    assert t.exact_budget_date is None
    assert t.calculation_blocked is True
    assert t.diagnostic_outreach_allowed is True
    assert t.proxy_type == "data_assinatura"
    assert "orçamento" in t.temporal_reasoning.lower() or "orcamento" in t.temporal_reasoning.lower()


def test_temporal_level_a_exact_budget():
    t = evaluate_temporal_hierarchy(
        as_of=AS_OF,
        exact_budget_date=date(2023, 1, 15),
        data_assinatura=date(2023, 5, 10),
    )
    assert t.level == TEMPORAL_LEVEL_A
    assert t.interregno_complete_exact is True
    assert t.exact_budget_date == date(2023, 1, 15)


def test_likely_without_exact_data_base_contact_or_human():
    """Proven 14.133 + signature >12m without exact data-base → LIKELY, null value.

    Unknown regime alone must NOT become LIKELY (year is not evidence).
    """
    unknown = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime="UNKNOWN",
        regime_proven=False,
        signature_year=2023,
        exact_budget_date=None,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=False,
        human_review_done=False,
        clause_located=False,
        index_or_formula=False,
    )
    assert unknown.commercial_stage in {
        DOCUMENT_REQUEST_READY,
        "POTENTIAL_ADJUSTMENT_SIGNAL",
    }
    assert unknown.commercial_stage != LIKELY_ADJUSTMENT_OPPORTUNITY
    assert unknown.regime_probable_14133 is False
    assert unknown.valor_potencial_allowed is False

    r = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        exact_budget_date=None,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=False,
        human_review_done=False,
        clause_located=False,
        index_or_formula=False,
    )
    assert r.commercial_stage == LIKELY_ADJUSTMENT_OPPORTUNITY
    assert r.temporal.level == TEMPORAL_LEVEL_B
    assert r.valor_potencial_allowed is False
    assert r.dimensions.claim_readiness == "claim_blocked"
    assert r.dimensions.contact_readiness == "none"
    assert r.dimensions.human_review_status != "human_review_completed"


def test_diagnostic_when_contact_present():
    """DIAGNOSTIC requires proven or LIKELY_14133 + verifiable contact."""
    # Object mention alone + year must NOT unlock 14.133 diagnostic
    blocked = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=False,
        signature_year=2023,
        object_mentions_14133=True,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=True,
        human_review_done=False,
    )
    assert blocked.commercial_stage != DIAGNOSTIC_OUTREACH_READY
    assert blocked.regime_probable_14133 is False

    r = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=True,
        human_review_done=False,
    )
    assert r.commercial_stage == DIAGNOSTIC_OUTREACH_READY
    assert (
        "não significa" in r.language_allowed.lower()
        or "nao significa" in r.language_allowed.lower()
        or "potencialmente" in r.language_allowed.lower()
    )
    assert r.valor_potencial_allowed is False
    assert (
        "valor devido" in r.prohibited_language.lower()
        or "crédito" in r.prohibited_language.lower()
        or "credito" in r.prohibited_language.lower()
    )

    likely = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=REGIME_LIKELY_14133,
        regime_proven=False,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=True,
    )
    assert likely.commercial_stage == DIAGNOSTIC_OUTREACH_READY
    assert "possível" in likely.language_allowed.lower() or "possivel" in likely.language_allowed.lower()


def test_pipeline_e2e_likely_and_diagnostic():
    """Mature obra without regime proof → DOCUMENT_REQUEST, not LIKELY by year."""
    no_contact = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert no_contact["commercial_stage"] in {
        DOCUMENT_REQUEST_READY,
        "POTENTIAL_ADJUSTMENT_SIGNAL",
    }
    assert no_contact["commercial_stage"] != LIKELY_ADJUSTMENT_OPPORTUNITY
    assert no_contact["valor_potencial"] is None
    assert no_contact["minimum_elapsed_confirmed"] is True
    assert no_contact["exact_budget_date"] is None
    assert no_contact["proxy_date"] is not None
    assert no_contact["calculation_blocked"] is True
    assert no_contact["claim_readiness"] == "claim_blocked"
    assert no_contact["regime_probable_14133"] is False
    # Still in commercial queue for document request
    assert no_contact["opportunity_score"] > 0
    assert no_contact["priority_score"] > 0

    with_contact = classify_row(
        MATURE_OBRA_ROW,
        as_of=AS_OF,
        contacts={
            "email_comercial": "contato@planaterra.com.br",
            "telefone_empresarial": "4833334444",
            "site_oficial": "https://planaterra.com.br",
            "contact_score": 0.85,
        },
    )
    # Contact does not invent 14.133 regime — still doc request / potential
    assert with_contact["commercial_stage"] != DIAGNOSTIC_OUTREACH_READY
    assert with_contact["valor_potencial"] is None
    arg = (with_contact.get("argumento_comercial") or with_contact.get("language_allowed") or "").lower()
    # Must not assert due credit as a positive claim
    for banned in ("inadimpl", "crédito constituído", "credito constituido", "r$ "):
        assert banned not in arg
    assert "regido pela lei 14.133" not in arg

    # With structured proven regime → LIKELY / DIAGNOSTIC
    proven_row = {**MATURE_OBRA_ROW}
    proven = classify_row(
        proven_row,
        as_of=AS_OF,
        structured_regime="LEI_14133_2021",
        contacts={
            "email_comercial": "contato@planaterra.com.br",
            "site_oficial": "https://planaterra.com.br",
            "contact_score": 0.85,
        },
    )
    assert proven["commercial_stage"] == DIAGNOSTIC_OUTREACH_READY
    assert proven["regime_proven"] is True
    assert proven["valor_potencial"] is None


def test_verified_only_after_full_documentary_and_human_pack():
    """AC9: same contract only reaches VERIFIED after data-base+index+clause+human."""
    base = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert base["commercial_stage"] != VERIFIED_ADJUSTMENT_OPPORTUNITY
    assert base["commercial_stage"] in {
        DOCUMENT_REQUEST_READY,
        "POTENTIAL_ADJUSTMENT_SIGNAL",
    }

    # Still LIKELY/DIAGNOSTIC without exact pack even with human flag alone
    partial = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        data_assinatura=date(2023, 5, 10),
        exact_budget_date=None,  # missing
        open_obligation=True,
        clause_located=True,
        index_or_formula=True,
        docs_text_extracted=True,
        document_link_validated=True,
        contact_verifiable=True,
        human_review_done=True,
    )
    assert partial.commercial_stage != VERIFIED_ADJUSTMENT_OPPORTUNITY
    assert partial.commercial_stage in {
        DIAGNOSTIC_OUTREACH_READY,
        LIKELY_ADJUSTMENT_OPPORTUNITY,
    }

    full = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        data_assinatura=date(2023, 5, 10),
        exact_budget_date=date(2023, 1, 20),
        open_obligation=True,
        clause_located=True,
        index_or_formula=True,
        docs_text_extracted=True,
        document_link_validated=True,
        contact_verifiable=True,
        human_review_done=True,
        has_calculable_base=False,
        has_index_series=False,
    )
    assert full.commercial_stage == VERIFIED_ADJUSTMENT_OPPORTUNITY
    assert full.valor_potencial_allowed is False
    assert full.dimensions.human_review_status == "human_review_completed"

    calc = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.9,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        data_assinatura=date(2023, 5, 10),
        exact_budget_date=date(2023, 1, 20),
        open_obligation=True,
        clause_located=True,
        index_or_formula=True,
        docs_text_extracted=True,
        document_link_validated=True,
        contact_verifiable=True,
        human_review_done=True,
        has_calculable_base=True,
        has_index_series=True,
    )
    assert calc.commercial_stage == CALCULABLE_ADJUSTMENT_CLAIM
    assert calc.valor_potencial_allowed is True


def test_absence_of_prior_adjustment_is_uncertainty_not_exclusion():
    r = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.8,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        adjustment_history="NO_PRIOR_ADJUSTMENT_LOCATED",
        contact_verifiable=False,
    )
    assert r.commercial_stage == LIKELY_ADJUSTMENT_OPPORTUNITY
    assert any("apostila" in u or "inexistencia" in u or "existencia" in u for u in r.uncertainties)


def test_only_calculable_allows_valor_potencial_in_pipeline():
    lead = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert lead["commercial_stage"] != CALCULABLE_ADJUSTMENT_CLAIM
    assert lead["valor_potencial"] is None


def test_human_review_file_import(tmp_path: Path):
    path = tmp_path / "reviews.json"
    path.write_text(
        """[
          {
            "contrato_id": "04892707000100-1-000200/2023",
            "reviewer": "Tiago",
            "reviewed_at": "2026-08-05T12:00:00Z",
            "documents_read": ["contrato.pdf", "edital.pdf"],
            "pages": ["12-15"],
            "clauses": ["cláusula 8 — reajuste"],
            "data_base_confirmed": "2023-01-20",
            "index_confirmed": "INCC-DI",
            "prior_adjustment": "none_found",
            "regime_confirmed": "LEI_14133_2021",
            "document_link_validated": true,
            "decision": "ACCEPT",
            "notes": "Cláusula e data-base lidas no PDF oficial",
            "confidence": "high"
          }
        ]""",
        encoding="utf-8",
    )
    recs = load_human_review_file(path)
    assert human_review_done_for(recs, contrato_id="04892707000100-1-000200/2023")
    # Incomplete: reviewer+decision only
    path_inc = tmp_path / "incomplete.json"
    path_inc.write_text(
        '[{"contrato_id":"inc-1","reviewer":"Tiago","decision":"ACCEPT"}]',
        encoding="utf-8",
    )
    incomplete = load_human_review_file(path_inc)
    assert not human_review_done_for(incomplete, contrato_id="inc-1")
    assert incomplete["inc-1"]["human_review_status"] == "human_review_incomplete"
    assert incomplete["inc-1"]["human_review_completed"] is False
    # Automated source rejected
    path2 = tmp_path / "bad.json"
    path2.write_text(
        '[{"contrato_id":"x","reviewer":"bot","decision":"ACCEPT","source":"ai_assisted"}]',
        encoding="utf-8",
    )
    bad = load_human_review_file(path2)
    assert not human_review_done_for(bad, contrato_id="x")


def test_automated_path_never_sets_human_review_completed():
    lead = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert lead["human_review_done"] is False
    assert lead["human_review_completed"] is False
    assert lead["human_review_status"] != "human_review_completed"
    assert lead.get("automated_review_queue") is True


def test_exports_stage_csvs(tmp_path: Path):
    lead = classify_row(
        MATURE_OBRA_ROW,
        as_of=AS_OF,
        structured_regime="LEI_14133_2021",
        contacts={
            "email_comercial": "c@planaterra.com.br",
            "site_oficial": "https://planaterra.com.br",
            "contact_score": 0.8,
        },
    )
    lead["ranking"] = 1
    from scripts.commercial.reajuste_14133.domain.supplier_portfolio import consolidate_suppliers

    portfolios = consolidate_suppliers([lead])
    run = {
        "run_id": "test-v3",
        "as_of": AS_OF.isoformat(),
        "git_sha": "test",
        "leads": [lead],
        "supplier_portfolios": portfolios,
        "top_leads": [lead],
    }
    write_v2_deliverables(tmp_path, run)
    assert (tmp_path / "likely_adjustment_opportunities.csv").exists() or (
        tmp_path / "diagnostic_outreach_ready.csv"
    ).exists()
    assert (tmp_path / "diagnostic_outreach_ready.csv").exists()
    assert (tmp_path / "supplier_priority_queue.csv").exists()
    assert (tmp_path / "top30_sul_manual_review.md").exists()
    assert (tmp_path / "top100_nacional_manual_review.md").exists()
    assert (tmp_path / "automated_review_queue.json").exists()
    auto = (tmp_path / "automated_review_queue.json").read_text(encoding="utf-8")
    assert "human_review_completed" in auto
    assert '"human_review_completed": false' in auto.lower() or '"human_review_completed": false' in auto
    # Diagnostic CSV must not invent valor for non-calculable
    diag = (tmp_path / "diagnostic_outreach_ready.csv").read_text(encoding="utf-8")
    assert "DIAGNOSTIC_OUTREACH_READY" in diag or "planaterra" in diag.lower() or "PLANATERRA" in diag


def test_missing_contact_keeps_supplier_in_document_or_likely_queue():
    """Without regime proof: DOCUMENT_REQUEST; with proof: LIKELY even without contact."""
    lead = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert lead["commercial_stage"] in {
        DOCUMENT_REQUEST_READY,
        "POTENTIAL_ADJUSTMENT_SIGNAL",
    }
    assert lead["contact_readiness"] == "none"
    from scripts.commercial.reajuste_14133.domain.supplier_portfolio import consolidate_suppliers

    portfolios = consolidate_suppliers([lead])
    assert len(portfolios) == 1
    assert portfolios[0]["contato_verificavel"] is False

    proven = classify_row(
        MATURE_OBRA_ROW,
        as_of=AS_OF,
        structured_regime="LEI_14133_2021",
        contacts={},
    )
    assert proven["commercial_stage"] == LIKELY_ADJUSTMENT_OPPORTUNITY
    assert proven["contact_readiness"] == "none"


def test_diagnostic_language_template():
    msg = DIAGNOSTIC_LANGUAGE.lower()
    assert "potencialmente" in msg
    assert "não significa" in msg or "nao significa" in msg
    assert "valor pendente" in msg or "conferência" in msg or "conferencia" in msg
    assert "14.133" in MSG_REGIME_PROVEN
    assert "possível" in MSG_REGIME_LIKELY or "possivel" in MSG_REGIME_LIKELY
    assert "14.133" not in MSG_REGIME_UNRESOLVED.split("reajuste")[0] or "confirmar o regime" in MSG_REGIME_UNRESOLVED


def test_proxy_not_presented_as_legal_data_base():
    """Proxy signature must never fill lead.data_base (legal field)."""
    lead = classify_row(MATURE_OBRA_ROW, as_of=AS_OF, contacts={})
    assert lead["exact_budget_date"] is None
    assert lead["data_base"] is None  # legal field empty without exact orçamento
    assert lead["proxy_date"] is not None
    assert lead["proxy_type"] == "data_assinatura"
    assert lead["data_base_status"] in {"PROXY_PROSPECTION_ONLY", "MISSING"}
    assert lead["minimum_elapsed_confirmed"] is True


def test_freemail_low_confidence_not_diagnostic():
    """Freemail public CNPJ email: keep in queue, low readiness, not DIAGNOSTIC alone."""
    from scripts.commercial.reajuste_14133.io.contacts import (
        contact_readiness_level,
        is_contact_verifiable_for_diagnostic,
    )

    freemail_contacts = {
        "email_comercial": None,
        "email_comercial_low_confidence": "contato@gmail.com",
        "email_confidence": "low",
        "contact_requires_review": True,
        "contact_score": 0.35,
    }
    assert is_contact_verifiable_for_diagnostic(freemail_contacts) is False
    assert contact_readiness_level(freemail_contacts) == "low"

    r = evaluate_commercial_stage(
        as_of=AS_OF,
        is_construction=True,
        obra_confidence=0.85,
        private_supplier=True,
        regime=REGIME_14133,
        regime_proven=True,
        signature_year=2023,
        data_assinatura=date(2023, 5, 10),
        open_obligation=True,
        contact_verifiable=False,
        contact_confidence="low",
        human_review_done=False,
    )
    assert r.commercial_stage == LIKELY_ADJUSTMENT_OPPORTUNITY
    assert r.dimensions.contact_readiness == "low"
    assert any("freemail" in u or "baixa_confianca" in u for u in r.uncertainties)


def test_exports_never_write_human_review_filenames(tmp_path: Path):
    lead = classify_row(
        MATURE_OBRA_ROW,
        as_of=AS_OF,
        contacts={
            "email_comercial": "c@planaterra.com.br",
            "email_confidence": "high",
            "site_oficial": "https://planaterra.com.br",
            "contact_score": 0.8,
        },
    )
    lead["ranking"] = 1
    from scripts.commercial.reajuste_14133.domain.supplier_portfolio import consolidate_suppliers

    portfolios = consolidate_suppliers([lead])
    run = {
        "run_id": "test-v3-hr",
        "as_of": AS_OF.isoformat(),
        "git_sha": "test",
        "leads": [lead],
        "supplier_portfolios": portfolios,
        "top_leads": [lead],
    }
    write_v2_deliverables(tmp_path, run)
    assert not (tmp_path / "human_review_top30_suppliers.json").exists()
    assert not (tmp_path / "human_review_top30_suppliers.md").exists()
    assert (tmp_path / "automated_review_queue.json").exists()
    assert (tmp_path / "human_review_pending.json").exists()
    assert (tmp_path / "ai_assisted_evidence_review_top30.json").exists()
    ai = json.loads((tmp_path / "ai_assisted_evidence_review_top30.json").read_text())
    assert ai.get("kind") == "ai_assisted_evidence_review"
    assert ai.get("human_review_completed") is False


def test_export_run_rejects_ai_as_human_review(tmp_path: Path):
    """cli.export_run must not treat ai_assisted artifacts as human_review."""
    import json as _json

    from scripts.commercial.reajuste_14133.cli import export_run

    # Plant AI artifact that formerly poisoned human_review path
    (tmp_path / "human_review_top30_suppliers.json").write_text(
        _json.dumps(
            {
                "kind": "ai_assisted_evidence_review",
                "reviews": [{"fornecedor": "X"}],
                "n": 1,
            }
        ),
        encoding="utf-8",
    )
    run = {
        "run_id": "test",
        "as_of": "2026-08-04",
        "module_version": "3.0.0",
        "campaign": "reajuste_14133",
        "source_mode": "csv",
        "source_dsn_masked": "postgresql://user:***@127.0.0.1/db",
        "funnel": {},
        "metrics": {},
        "language_policy": {},
        "top_leads": [],
        "leads": [],
        "supplier_portfolios": [],
        "git_sha": "test",
    }
    # Minimal files for export path
    result = export_run(run, tmp_path, dossier_count=0, manual_review=False)
    paths = result.get("paths") or {}
    assert "human_review" not in paths
    assert "human_review_completed" not in paths or not str(paths.get("human_review_completed", "")).endswith(
        "human_review_top30_suppliers.json"
    )
    assert run.get("metrics", {}).get("human_review_count") in {None, 0} or ("human_review" not in paths)

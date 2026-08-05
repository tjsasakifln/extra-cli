"""v2 tests: outreach gates, keyset, supplier consolidation, FPs, value quality."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    DATA_BASE_PROXY,
    DOCUMENT_REQUEST_CANDIDATE,
    NOT_READY_FOR_OUTREACH,
    OUTREACH_READY,
    OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
    REGIME_14133,
    REGIME_CONFLICT,
    REGIME_UNKNOWN,
    STATUS_LEGAL_REGIME_UNKNOWN,
    VALUE_OUTLIER_REQUIRES_REVIEW,
    VALUE_PLAUSIBLE,
)
from scripts.commercial.reajuste_14133.cli import build_parser
from scripts.commercial.reajuste_14133.domain.adjustment_history import (
    classify_adjustment_history,
)
from scripts.commercial.reajuste_14133.domain.contradictions import (
    detect_material_contradictions,
)
from scripts.commercial.reajuste_14133.domain.dates import consolidate_dates
from scripts.commercial.reajuste_14133.domain.execution_status import (
    classify_execution_status,
)
from scripts.commercial.reajuste_14133.domain.finance import estimate_reajuste
from scripts.commercial.reajuste_14133.domain.freshness import compute_source_freshness
from scripts.commercial.reajuste_14133.domain.obra_classifier import classify_construction
from scripts.commercial.reajuste_14133.domain.outreach import evaluate_outreach
from scripts.commercial.reajuste_14133.domain.regime import classify_legal_regime
from scripts.commercial.reajuste_14133.domain.supplier_portfolio import (
    consolidate_suppliers,
    dedupe_economic_opportunities,
    same_obra_cross_org_key,
)
from scripts.commercial.reajuste_14133.domain.value_quality import validate_contract_value
from scripts.commercial.reajuste_14133.io.documents import extract_from_text
from scripts.commercial.reajuste_14133.io.source import (
    build_prefilter_query,
    iter_contracts_keyset,
    resolve_source,
)
from scripts.commercial.reajuste_14133.pipeline import classify_row

AS_OF = date(2026, 8, 4)


# --- False positive regressions (§14) ---


def test_fp_aeronautical_logistics_not_construction():
    r = classify_construction(
        "Suporte logístico de motores aeronáuticos e componentes de aeronaves"
    )
    assert not r.is_construction


def test_fp_software_gestao_obras_not_construction():
    r = classify_construction(
        "Licenciamento de software de gestão de obras e construção civil"
    )
    assert not r.is_construction


def test_fp_software_license_not_engineering():
    r = classify_construction("Licenciamento de uso de software ERP para engenharia")
    assert not r.is_construction


def test_fp_ppp_escolar_not_empreitada():
    r = classify_construction("PPP de operação e manutenção de escolas públicas")
    assert not r.is_construction


def test_fp_concessao_hospitalar_not_obra():
    r = classify_construction(
        "Concessão hospitalar de longo prazo com gestão de serviços de saúde"
    )
    assert not r.is_construction


def test_fp_projeto_sem_execucao_not_obra():
    r = classify_construction(
        "Elaboração de projeto básico e executivo sem execução de obra"
    )
    assert not r.is_construction


def test_fp_locacao_equipamentos_not_obra():
    r = classify_construction("Locação de equipamentos de engenharia e guindastes")
    assert not r.is_construction


def test_fp_manutencao_equipamento_not_obra():
    r = classify_construction("Manutenção de equipamento de usina asfáltica")
    assert not r.is_construction


def test_true_pavimentacao_still_construction():
    r = classify_construction(
        "Execução de obra de pavimentação asfáltica e drenagem urbana com empreitada"
    )
    assert r.is_construction


# --- Regime conflict ---


def test_regime_conflict_blocks():
    r = classify_legal_regime(
        document_texts=[
            "Contrato regido pela Lei nº 14.133/2021 e subsidiariamente pela Lei 8.666/1993"
        ]
    )
    assert r.regime == REGIME_CONFLICT
    assert not r.proven


# --- Index only in clause ---


def test_index_outside_clause_not_assigned():
    text = (
        "O memorial descritivo cita o SINAPI apenas para referência de preços unitários "
        "de insumos em planilha orçamentária. Especificações técnicas sem menção a "
        "periodicidade anual nem fórmula de correção de preços."
    )
    scan = extract_from_text(text, doc_type="anexo", url=None)
    assert not scan.reajuste_clause_mention
    assert "SINAPI" not in scan.index_in_clause
    assert "SINAPI" in scan.index_outside_clause_only or "SINAPI" in (
        scan.index_candidates or []
    )


def test_index_in_reajuste_clause_assigned():
    text = (
        "CLÁUSULA DE REAJUSTE: os preços serão reajustados anualmente pelo INCC-DI "
        "divulgado pela FGV, contados da data-base do orçamento estimado."
    )
    scan = extract_from_text(
        text,
        doc_type="contrato",
        url="https://example.com",
        method="pncp_pdf_pypdf2",
        is_official_document=True,
    )
    assert scan.reajuste_clause_mention
    assert any("INCC" in x for x in scan.index_in_clause)
    assert scan.docs_accessible is True
    assert scan.official_text_extracted is True


def test_pdf_binary_not_docs_accessible():
    text = "[PDF_BINARY bytes=12345 sha256=abcdef0123456789]"
    scan = extract_from_text(
        text, doc_type="pdf", url="https://x", is_binary_placeholder=True
    )
    assert scan.pdf_binary_located
    assert not scan.docs_accessible
    assert not scan.text_extracted
    assert not getattr(scan, "official_text_extracted", False)


def test_portal_html_not_official_documentary_proof():
    """Portal/object HTML must not set docs_accessible / official_text_extracted."""
    scan = extract_from_text(
        "Edital regido pela Lei 14.133/2021 com cláusula de reajuste pelo INCC",
        doc_type="pncp_portal_html",
        url="https://pncp.gov.br/app/contratos/x",
        method="http_get_html",
        is_official_document=False,
    )
    assert scan.regime_14133_mention  # signal may exist
    assert not scan.docs_accessible
    assert not scan.official_text_extracted


def test_official_pdf_text_sets_docs_accessible():
    scan = extract_from_text(
        "CLÁUSULA DE REAJUSTE: reajuste anual pelo INCC-DI. Edital regido pela Lei nº 14.133/2021. "
        "Data-base do orçamento estimado: janeiro/2024.",
        doc_type="pncp_pdf:edital.pdf",
        url="https://pncp.gov.br/pncp-api/v1/orgaos/x/compras/2024/1/arquivos/1",
        method="pncp_pdf_pypdf2",
        is_official_document=True,
        page_hint="1-10",
    )
    assert scan.docs_accessible
    assert scan.official_text_extracted
    assert scan.reajuste_clause_mention
    assert any(e.page for e in scan.evidences)


def test_fp_concessao_agua_not_construction():
    r = classify_construction(
        "Concessão Comum dos serviços públicos de abastecimento de água potável "
        "e esgotamento sanitário do Município de Palhoça"
    )
    assert not r.is_construction


# --- Temporal layers ---


def test_signature_under_12m_not_hard_exclude_when_budget_base_old():
    """Contract signed recently but orçamento ≥12m → interregno can be complete."""
    d = consolidate_dates(
        as_of=AS_OF,
        orcamento_estimado=date(2024, 6, 1),
        orcamento_source="edital",
        orcamento_confidence="high",
        data_assinatura=date(2025, 10, 1),  # <12m from as_of
        allow_proxy_for_prospection=True,
    )
    assert d.data_base_status == DATA_BASE_CONFIRMED
    assert d.interregno_completo


def test_proxy_temporal_not_confirmed():
    d = consolidate_dates(
        as_of=AS_OF,
        data_assinatura=date(2023, 1, 1),
        allow_proxy_for_prospection=True,
    )
    assert d.data_base_status == DATA_BASE_PROXY


# --- Value quality ---


def test_billion_road_value_outlier():
    v = validate_contract_value(
        valor_total=3_500_000_000,
        objeto="Pavimentação asfáltica de rodovia estadual trecho X",
        confirmed_by_document=False,
    )
    assert v.status == VALUE_OUTLIER_REQUIRES_REVIEW
    assert not v.may_drive_financial_score


def test_plausible_mid_market_value():
    v = validate_contract_value(
        valor_total=25_000_000,
        objeto="Execução de obra de pavimentação urbana",
    )
    assert v.status == VALUE_PLAUSIBLE
    assert v.may_drive_financial_score


# --- Finance: no potential without series ---


def test_no_valor_potencial_without_index_series():
    f = estimate_reajuste(
        valor_original=10_000_000,
        saldo_contratual=4_000_000,
        indice_contratual="INCC-DI",
        # no series values
    )
    assert f.valor_potencial is None


def test_valor_potencial_with_series_and_saldo():
    f = estimate_reajuste(
        valor_original=10_000_000,
        saldo_contratual=4_000_000,
        indice_contratual="INCC-DI",
        indice_base_value=100,
        indice_final_value=110,
    )
    assert f.valor_potencial is not None


# --- Adjustment history honesty ---


def test_no_prior_adjustment_is_not_proof():
    h = classify_adjustment_history(searched_sources=True)
    assert h.status == "NO_PRIOR_ADJUSTMENT_LOCATED"
    assert h.absence_is_not_proof


def test_partial_adjustment():
    h = classify_adjustment_history(
        document_texts=["Foi concedido reajuste parcial das parcelas de 2024."]
    )
    assert h.status == "PARTIAL_ADJUSTMENT_CONFIRMED"


# --- Execution ---


def test_expired_with_open_obligation():
    e = classify_execution_status(
        as_of=AS_OF,
        is_active=False,
        data_fim=date(2025, 1, 1),
        valor_total=10_000_000,
        valor_medido=6_000_000,
    )
    assert e.status == "CONTRACT_EXPIRED_WITH_OPEN_FINANCIAL_OBLIGATIONS"
    assert e.open_obligation_possible


# --- Freshness not fixed ---


def test_freshness_varies_by_date():
    recent = compute_source_freshness(as_of=AS_OF, data_publicacao=date(2026, 7, 1))
    old = compute_source_freshness(as_of=AS_OF, data_publicacao=date(2020, 1, 1))
    assert recent > old
    assert recent != 0.55 or old != 0.55  # at least one differs from old fixed constant


# --- Contradictions computed ---


def test_contradictions_not_hardcoded_false():
    c = detect_material_contradictions(
        legal_regime_conflict=True,
        already_adjusted=True,
        claiming_no_adjustment=True,
    )
    assert c.material_contradiction
    assert c.items


# --- Outreach gates ---


def test_legal_regime_unknown_never_outreach_ready():
    r = evaluate_outreach(
        eligibility_status=STATUS_LEGAL_REGIME_UNKNOWN,
        regime=REGIME_UNKNOWN,
        regime_proven=False,
        is_construction=True,
        private_supplier=True,
        clause_located=True,
        data_base_status=DATA_BASE_CONFIRMED,
        index_in_clause=True,
        interregno_completo=True,
        open_obligation=True,
        adjustment_history="NO_PRIOR_ADJUSTMENT_LOCATED",
        value_quality=VALUE_PLAUSIBLE,
        contact_verifiable=True,
        human_review_done=True,
        has_valor_potencial=True,
        docs_text_extracted=True,
    )
    assert r.status != OUTREACH_READY
    assert r.status != OUTREACH_READY_WITHOUT_VALUE_ESTIMATE


def test_outreach_ready_requires_all_gates():
    r = evaluate_outreach(
        eligibility_status="HOT_VERIFIED",
        regime=REGIME_14133,
        regime_proven=True,
        is_construction=True,
        private_supplier=True,
        clause_located=True,
        data_base_status=DATA_BASE_CONFIRMED,
        data_base_exact=True,
        index_in_clause=True,
        interregno_completo=True,
        open_obligation=True,
        adjustment_history="PARTIAL_ADJUSTMENT_CONFIRMED",
        value_quality=VALUE_PLAUSIBLE,
        contact_verifiable=True,
        human_review_done=True,
        has_valor_potencial=True,
        docs_text_extracted=True,
    )
    assert r.status == OUTREACH_READY


def test_outreach_ready_without_value():
    r = evaluate_outreach(
        eligibility_status="HOT_VERIFIED",
        regime=REGIME_14133,
        regime_proven=True,
        is_construction=True,
        private_supplier=True,
        clause_located=True,
        data_base_status=DATA_BASE_CONFIRMED,
        data_base_exact=True,
        index_in_clause=True,
        interregno_completo=True,
        open_obligation=True,
        adjustment_history="NO_PRIOR_ADJUSTMENT_LOCATED",
        value_quality=VALUE_PLAUSIBLE,
        contact_verifiable=True,
        human_review_done=True,
        has_valor_potencial=False,
        docs_text_extracted=True,
    )
    assert r.status == OUTREACH_READY_WITHOUT_VALUE_ESTIMATE


def test_document_request_candidate_strong_signal():
    r = evaluate_outreach(
        eligibility_status="STRONG_CANDIDATE",
        regime=REGIME_UNKNOWN,
        regime_proven=False,
        is_construction=True,
        private_supplier=True,
        clause_located=False,
        data_base_status=DATA_BASE_PROXY,
        index_in_clause=False,
        interregno_completo=True,
        open_obligation=True,
        adjustment_history="NO_PRIOR_ADJUSTMENT_LOCATED",
        value_quality=VALUE_PLAUSIBLE,
        contact_verifiable=False,
        human_review_done=False,
        has_valor_potencial=False,
        docs_text_extracted=False,
    )
    assert r.status == DOCUMENT_REQUEST_CANDIDATE


def test_human_review_without_docs_blocks_ready():
    r = evaluate_outreach(
        eligibility_status="HOT_VERIFIED",
        regime=REGIME_14133,
        regime_proven=True,
        is_construction=True,
        private_supplier=True,
        clause_located=True,
        data_base_status=DATA_BASE_CONFIRMED,
        data_base_exact=True,
        index_in_clause=True,
        interregno_completo=True,
        open_obligation=True,
        adjustment_history="NO_PRIOR_ADJUSTMENT_LOCATED",
        value_quality=VALUE_PLAUSIBLE,
        contact_verifiable=True,
        human_review_done=False,
        has_valor_potencial=True,
        docs_text_extracted=True,
    )
    assert r.status != OUTREACH_READY


# --- Supplier consolidation ---


def test_multiple_contracts_one_supplier_one_lead():
    leads = []
    for i in range(4):
        leads.append(
            {
                "cnpj": "12345678000199",
                "razao_social": "GAIA RODOVIAS LTDA",
                "contrato_id": f"11111111000111-1-{i}/2023",
                "orgao_contratante": f"ORGAO {i}",
                "orgao_cnpj": f"2222222200011{i}",
                "valor_original": 10_000_000 + i,
                "score_total": 50 + i,
                "classificacao": "LEGAL_REGIME_UNKNOWN",
                "outreach_status": DOCUMENT_REQUEST_CANDIDATE,
                "uf": "SC",
                "objeto": f"Pavimentação asfáltica trecho {i} com empreitada",
                "data_assinatura": "2023-01-01",
            }
        )
    portfolios = consolidate_suppliers(leads)
    assert len(portfolios) == 1
    assert portfolios[0]["qtd_contratos_candidatos"] == 4
    assert portfolios[0]["cnpj"] == "12345678000199"


def test_same_obra_multi_org_cnpj_dedupe():
    a = {
        "cnpj": "12345678000199",
        "contrato_id": "11111111000111-1-1/2023",
        "orgao_cnpj": "11111111000111",
        "valor_original": 50_000_000,
        "objeto": "Execução de obra de pavimentação asfáltica BR-101 trecho Norte",
        "data_assinatura": "2023-05-01",
        "score_total": 40,
        "classificacao": "REVIEW_REQUIRED",
        "outreach_status": NOT_READY_FOR_OUTREACH,
        "uf": "SC",
        "razao_social": "X",
    }
    b = {
        **a,
        "contrato_id": "99999999000199-1-1/2023",
        "orgao_cnpj": "99999999000199",  # different admin unit
        "score_total": 30,
    }
    assert same_obra_cross_org_key(a) == same_obra_cross_org_key(b)
    out = dedupe_economic_opportunities([a, b])
    assert len(out) == 1


# --- Keyset SQL / no silent 25k ---


def test_cli_max_source_rows_default_none():
    p = build_parser()
    args = p.parse_args([])
    assert args.max_source_rows is None


def test_cli_manual_review_default_false():
    p = build_parser()
    args = p.parse_args([])
    assert args.manual_review is False


def test_keyset_query_has_no_offset_when_keyset():
    sql, params = build_prefilter_query(
        columns=["contrato_id", "valor_total", "fornecedor_cnpj", "data_assinatura", "data_inicio", "data_publicacao", "data_fim", "is_active", "uf"],
        as_of=AS_OF,
        min_contract_value=1_000_000,
        limit=100,
        keyset_valor=50_000_000,
        keyset_contrato_id="x-1-1/2023",
    )
    assert "OFFSET" not in sql.upper()
    assert "valor_total <" in sql or "valor_total < %s" in sql
    assert "LIMIT" in sql.upper()


def test_keyset_stream_csv(tmp_path: Path):
    csv_path = tmp_path / "c.csv"
    csv_path.write_text(
        "contrato_id,fornecedor_cnpj,fornecedor_nome,objeto_contrato,valor_total,uf,data_assinatura,data_inicio,data_fim,is_active,orgao_cnpj,orgao_nome\n"
        "1,12345678000199,ACME ENGENHARIA,Execucao de obra de pavimentacao,10000000,SC,2023-01-01,2023-02-01,,true,11111111000111,PREFEITURA\n"
        "2,12345678000199,ACME ENGENHARIA,Execucao de obra de drenagem,20000000,SC,2022-01-01,2022-02-01,,true,11111111000111,PREFEITURA\n",
        encoding="utf-8",
    )
    cfg = resolve_source(csv_path=str(csv_path))
    batches = list(
        iter_contracts_keyset(cfg, as_of=AS_OF, min_contract_value=1_000_000, batch_size=1)
    )
    assert len(batches) == 2
    assert sum(len(b) for b in batches) == 2


def test_classify_row_blocks_unknown_regime_from_ready():
    row = {
        "contrato_id": "12345678000199-1-1/2023",
        "fornecedor_cnpj": "12345678000199",
        "fornecedor_nome": "CONSTRUTORA REGIONAL LTDA",
        "objeto_contrato": "Execução de obra de pavimentação asfáltica e drenagem",
        "valor_total": 15_000_000,
        "uf": "SC",
        "data_assinatura": "2023-01-15",
        "data_inicio": "2023-02-01",
        "data_fim": "2027-02-01",
        "is_active": True,
        "orgao_cnpj": "11111111000111",
        "orgao_nome": "PREFEITURA MUNICIPAL",
    }
    lead = classify_row(row, as_of=AS_OF)
    assert lead["outreach_status"] != OUTREACH_READY
    if lead["classificacao"] == STATUS_LEGAL_REGIME_UNKNOWN:
        assert lead["outreach_status"] in {
            NOT_READY_FOR_OUTREACH,
            DOCUMENT_REQUEST_CANDIDATE,
        }


# --- Atomic rebind-export unit ---


def _official_pdf_scan_dict(*, conflict: bool = False) -> dict:
    """Minimal stored doc_scan with official PDF evidence (as on disk after recovery)."""
    excerpts_14133 = (
        "EDITAL REGIDO PELA LEI 14.133 DE 01/04/2021 e demais normas aplicáveis."
    )
    excerpts_clause = (
        "CLÁUSULA DE REAJUSTE: os preços serão reajustados anualmente pelo INCC."
    )
    evidences = [
        {
            "doc_type": "edital_pdf",
            "orgao_emissor": "PNCP",
            "identificador_oficial": "pdf-1",
            "url_or_location": "https://pncp.gov.br/arquivo.pdf",
            "consulted_at": "2026-08-05T01:35:00Z",
            "excerpt": excerpts_14133,
            "content_hash": "abc123",
            "extraction_method": "pncp_pdf_pypdf2",
            "confidence": "high",
            "field_found": "regime_legal_14133",
            "page": 2,
            "section": "preambulo",
            "human_confirmed": False,
        },
        {
            "doc_type": "edital_pdf",
            "orgao_emissor": "PNCP",
            "identificador_oficial": "pdf-1",
            "url_or_location": "https://pncp.gov.br/arquivo.pdf",
            "consulted_at": "2026-08-05T01:35:00Z",
            "excerpt": excerpts_clause,
            "content_hash": "def456",
            "extraction_method": "pncp_pdf_pypdf2",
            "confidence": "high",
            "field_found": "clausula_reajuste",
            "page": 12,
            "section": "reajuste",
            "human_confirmed": False,
        },
    ]
    if conflict:
        evidences.append(
            {
                "doc_type": "edital_pdf",
                "orgao_emissor": "PNCP",
                "identificador_oficial": "pdf-1",
                "url_or_location": "https://pncp.gov.br/arquivo.pdf",
                "consulted_at": "2026-08-05T01:35:00Z",
                "excerpt": "Contrato regido pela Lei 8.666/93 e alterações posteriores.",
                "content_hash": "ghi789",
                "extraction_method": "pncp_pdf_pypdf2",
                "confidence": "high",
                "field_found": "regime_legal_8666",
                "page": 3,
                "section": "preambulo",
                "human_confirmed": False,
            }
        )
    return {
        "evidences": evidences,
        "index_candidates": ["INCC"],
        "index_in_clause": ["INCC"],
        "index_outside_clause_only": [],
        "regime_14133_mention": True,
        "regime_8666_mention": conflict,
        "regime_rdc_mention": False,
        "regime_conflict": conflict,
        "reajuste_clause_mention": True,
        "data_base_mention": True,
        "apostila_mention": False,
        "already_adjusted_hint": False,
        "docs_accessible": True,
        "text_extracted": True,
        "official_text_extracted": True,
        "pdf_binary_located": True,
        "pdf_text_pages": 40,
        "pipeline_state": "CLAUSE_LOCATED",
        "network_error": False,
        "limitations": [],
        "arquivos_listed": 2,
        "pdfs_downloaded": 1,
        "pdfs_text_extracted": 1,
        "deep_document_work": True,
    }


def test_reclassify_from_pdf_evidence_not_legal_regime_unknown():
    """Post-hoc regime_proven=True + LEGAL_REGIME_UNKNOWN must be fixed by reclassify."""
    from scripts.commercial.reajuste_14133.rebind_export import reclassify_contract

    prior = {
        "contrato_id": "12345678000199-1-000001/2024",
        "cnpj": "12345678000199",
        "razao_social": "CONSTRUTORA REGIONAL LTDA",
        "objeto": "Execução de obra de pavimentação asfáltica e drenagem urbana",
        "valor_original": 18_000_000,
        "uf": "SC",
        "data_assinatura": "2024-03-01",
        "data_inicio": "2024-04-01",
        "data_fim": "2027-04-01",
        "data_publicacao": "2024-02-15",
        "is_active": True,
        "orgao_cnpj": "11111111000111",
        "orgao_contratante": "PREFEITURA MUNICIPAL",
        "regime_legal": REGIME_14133,
        "regime_proven": True,  # patched post-hoc
        "classificacao": STATUS_LEGAL_REGIME_UNKNOWN,  # stale
        "outreach_status": NOT_READY_FOR_OUTREACH,
        "doc_scan": _official_pdf_scan_dict(conflict=False),
        "canais_contato": {"email": "contato@example.com", "telefone": None, "site": None},
        "human_review_done": False,
    }
    new = reclassify_contract(prior, as_of=AS_OF)
    assert not (
        new.get("regime_proven")
        and new.get("regime_legal") == REGIME_14133
        and new.get("classificacao") == STATUS_LEGAL_REGIME_UNKNOWN
    ), "rebind must not leave proven 14133 as LEGAL_REGIME_UNKNOWN"
    # With clean official 14133 + construction + mature proxy → not NOT_ELIGIBLE solely for regime
    assert new.get("classificacao") != STATUS_LEGAL_REGIME_UNKNOWN
    assert new.get("regime_legal") in {REGIME_14133, REGIME_CONFLICT}
    if new.get("regime_legal") == REGIME_14133:
        assert new.get("regime_proven") is True
        assert new.get("outreach_status") in {
            DOCUMENT_REQUEST_CANDIDATE,
            OUTREACH_READY,
            OUTREACH_READY_WITHOUT_VALUE_ESTIMATE,
            NOT_READY_FOR_OUTREACH,
        }


def test_rebind_export_invariants_atomic(tmp_path: Path):
    """Single rebind-export rewrites classify+CSV+manifest with HEAD binding."""
    from scripts.commercial.reajuste_14133.rebind_export import (
        rebind_export,
        validate_invariants,
        RebindInvariantError,
    )

    fake_head = "a" * 40
    run_dir = tmp_path / "nacional"
    run_dir.mkdir()
    contracts = []
    for i in range(3):
        contracts.append(
            {
                "contrato_id": f"12345678000199-1-00000{i}/2023",
                "cnpj": "12345678000199",
                "razao_social": "CONSTRUTORA REGIONAL LTDA",
                "objeto": "Execução de obra de pavimentação asfáltica e drenagem",
                "valor_original": 12_000_000 + i * 1000,
                "uf": "PR",
                "data_assinatura": "2023-01-15",
                "data_inicio": "2023-02-01",
                "data_fim": "2027-02-01",
                "data_publicacao": "2023-01-10",
                "is_active": True,
                "orgao_cnpj": "11111111000111",
                "orgao_contratante": "PREFEITURA",
                "regime_legal": REGIME_14133,
                "regime_proven": True,
                "classificacao": STATUS_LEGAL_REGIME_UNKNOWN,
                "outreach_status": NOT_READY_FOR_OUTREACH,
                "doc_scan": _official_pdf_scan_dict(conflict=False),
                "canais_contato": {"email": None, "telefone": None, "site": None},
            }
        )
    (run_dir / "contratos_analisados.json").write_text(
        json.dumps({"contratos": contracts}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "git_sha": "old",
                "evidence_commit_sha": "older",
                "params": {"universe_eligible_count": 3, "pagination": "keyset"},
                "source_mode": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    art = tmp_path / "artifacts"
    result = rebind_export(
        run_dir,
        as_of="2026-08-04",
        head_sha=fake_head,
        artifacts_dir=art,
    )
    assert result["still_unknown_with_proven"] == 0
    assert result["head_sha"] == fake_head
    assert result["n_contracts"] == 3
    assert result["official"] >= 1

    man = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert man["git_sha"] == fake_head
    assert man["evidence_commit_sha"] == fake_head
    assert man["params"]["rebind_export"] is True
    assert man["metrics"]["docs_processed_deep"] == result["deep"]
    assert man["funnel"]["docs_processed_deep"] == result["deep"]

    # No proven+14133 left as UNKNOWN
    reloaded = json.loads((run_dir / "contratos_analisados.json").read_text(encoding="utf-8"))
    for lead in reloaded["contratos"]:
        if lead.get("regime_proven") and lead.get("regime_legal") == REGIME_14133:
            assert lead.get("classificacao") != STATUS_LEGAL_REGIME_UNKNOWN

    # CSV/JSON coherence on classificacao
    import csv as _csv

    by_id = {}
    with (run_dir / "contratos_analisados.csv").open(encoding="utf-8", newline="") as f:
        for row in _csv.DictReader(f):
            by_id[row["contrato_id"]] = row
    for lead in reloaded["contratos"]:
        crow = by_id[str(lead["contrato_id"])]
        assert crow["classificacao"] == lead["classificacao"]
        assert crow["regime_legal"] == str(lead["regime_legal"])

    # Evidence timestamps inside window
    started, finished = man["started_at"], man["finished_at"]
    for line in (run_dir / "document_evidence.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("extraction_method") == "pncp_pdf_pypdf2":
            assert started <= e["consulted_at"] <= finished

    errs = validate_invariants(
        reloaded["contratos"],
        manifest=man,
        evidence_path=run_dir / "document_evidence.jsonl",
        head_sha=fake_head,
    )
    assert errs == []

    assert (art / "nacional_run_manifest.json").exists()


def test_validate_invariants_catches_proven_unknown():
    from scripts.commercial.reajuste_14133.rebind_export import validate_invariants

    leads = [
        {
            "contrato_id": "x",
            "regime_proven": True,
            "regime_legal": REGIME_14133,
            "classificacao": STATUS_LEGAL_REGIME_UNKNOWN,
            "doc_scan": {},
        }
    ]
    errs = validate_invariants(
        leads,
        manifest={"git_sha": "h", "evidence_commit_sha": "h"},
        evidence_path=Path("/nonexistent"),
        head_sha="h",
    )
    assert any("LEGAL_REGIME_UNKNOWN" in e for e in errs)

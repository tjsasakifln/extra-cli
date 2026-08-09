"""v3 gates: document link, exact data-base, sector FP, TECHNICALLY_VERIFIED_PENDING_TIAGO."""

from __future__ import annotations

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    DOCUMENT_REQUEST_CANDIDATE,
    OUTREACH_READY,
    REGIME_14133,
    TECHNICALLY_VERIFIED_PENDING_TIAGO,
    VALUE_PLAUSIBLE,
)
from scripts.commercial.reajuste_14133.domain.data_base_exact import (
    COMPETENCE_IN_BUDGET_SPREADSHEET,
    EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE,
    EXACT_DATE_IN_REAJUSTE_CLAUSE,
    GENERIC_RULE_WITHOUT_DATE,
    extract_exact_data_base,
    is_exact_data_base_state,
)
from scripts.commercial.reajuste_14133.domain.document_link import (
    DOCUMENT_LINK_CONFLICT,
    DOCUMENT_LINK_PARTIAL,
    DOCUMENT_LINK_VERIFIED,
    invalidate_signals_on_conflict,
    verify_document_link,
)
from scripts.commercial.reajuste_14133.domain.obra_classifier import classify_construction
from scripts.commercial.reajuste_14133.domain.outreach import evaluate_outreach
from scripts.commercial.reajuste_14133.export.tiago_review import write_tiago_review_package
from scripts.commercial.reajuste_14133.io.documents import (
    DOC_TYPES_SOUGHT,
    try_extract_pdf_via_process_documents,
)


def test_lisdexanfetamina_document_conflicts_with_construction_contract():
    """Strata-style pharma PDF must not bind to engineering supplier contract."""
    link = verify_document_link(
        contract_orgao_cnpj="12345678000199",
        contract_ano=2024,
        contract_sequencial=1,
        contract_object="Execução de obras de pavimentação asfáltica e drenagem urbana",
        contract_fornecedor="STRATA ENGENHARIA LTDA",
        contract_fornecedor_cnpj="99888777000166",
        doc_orgao_cnpj="12345678000199",
        doc_ano=2024,
        doc_sequencial=1,
        doc_object_or_title="Aquisição de lisdexanfetamina 70mg",
        doc_text=(
            "Pregão para aquisição de medicamento lisdexanfetamina dimesilato 70mg "
            "cápsulas de liberação prolongada, registro ANVISA, princípio ativo controlado."
        ),
    )
    assert link.status == DOCUMENT_LINK_CONFLICT
    assert link.signals_usable is False
    assert any("pharma" in r for r in link.reasons)

    scan = {
        "regime_14133_mention": True,
        "reajuste_clause_mention": True,
        "index_in_clause": ["IPCA"],
        "data_base_mention": True,
        "docs_accessible": True,
        "text_extracted": True,
        "official_text_extracted": True,
        "evidences": [{"field_found": "clausula_reajuste", "excerpt": "reajuste IPCA"}],
        "limitations": [],
    }
    wiped = invalidate_signals_on_conflict(scan, link)
    assert wiped["signals_usable"] is False
    assert wiped["regime_14133_mention"] is False
    assert wiped["reajuste_clause_mention"] is False
    assert wiped["index_in_clause"] == []
    assert wiped["invalidated_by_document_link_conflict"] is True


def test_betha_sistemas_not_construction_eligible():
    """Betha Sistemas software must not enter construction Top candidates."""
    r = classify_construction(
        "Licenciamento de software de gestão pública municipal e implantação de sistema",
        razao_social="BETHA SISTEMAS LTDA",
        cnae="6201501 - Desenvolvimento de programas de computador sob encomenda",
    )
    assert r.is_construction is False
    assert any(
        "betha" in c or "software" in c or "cnae" in c or "negative" in c or "sector" in c
        for c in r.reason_codes + r.negative_hits
    )


def test_localiza_veiculos_not_candidate():
    """Localiza Veículos Especiais is vehicle rental, not obra execution."""
    r = classify_construction(
        "Locação de veículos especiais para transporte de passageiros e frota dedicada",
        razao_social="LOCALIZA VEICULOS ESPECIAIS S.A.",
        cnae="7711000 - Locação de automóveis sem condutor",
    )
    assert r.is_construction is False
    assert any(
        "localiza" in c or "vehicle" in c or "locacao" in c or "negative" in c or "cnae" in c
        for c in r.reason_codes + r.negative_hits + [r.category]
    )


def test_company_name_alone_never_proves_sector():
    r = classify_construction(
        "Fornecimento de materiais de escritório",
        razao_social="CONSTRUTORA GENÉRICA DO SUL LTDA",
    )
    assert r.is_construction is False


def test_document_link_verified_on_matching_keys():
    link = verify_document_link(
        contract_numero_controle_pncp_compra="12345678000199-1-000010/2024",
        contract_orgao_cnpj="12345678000199",
        contract_ano=2024,
        contract_sequencial=10,
        contract_object="Execução de obras de pavimentação asfáltica na rodovia SC-401",
        contract_fornecedor="PLANATERRA TERRAPLENAGEM E PAVIMENTACAO LTDA",
        contract_fornecedor_cnpj="82743832000162",
        doc_numero_controle_pncp_compra="12345678000199-1-000010/2024",
        doc_orgao_cnpj="12345678000199",
        doc_ano=2024,
        doc_sequencial=10,
        doc_object_or_title="Edital — pavimentação asfáltica SC-401",
        doc_text=(
            "Contrato de execução de obras de pavimentação asfáltica na rodovia SC-401 "
            "com a contratada PLANATERRA TERRAPLENAGEM E PAVIMENTACAO LTDA CNPJ 82.743.832/0001-62. "
            "Empreitada por preço global. Lei 14.133/2021."
        ),
    )
    assert link.status in {DOCUMENT_LINK_VERIFIED, DOCUMENT_LINK_PARTIAL}
    assert link.signals_usable is True


def test_compra_linked_docs_not_conflicted_by_contract_sequential():
    """Compra sequencial ≠ contract sequencial is expected — must not hard-conflict when compra matches."""
    link = verify_document_link(
        contract_numero_controle_pncp_compra="04892707000100-1-000200/2024",
        contract_orgao_cnpj="04892707000100",
        # intentionally same as compra (pipeline passes compra identity on both sides)
        contract_ano=2024,
        contract_sequencial=200,
        contract_object="Execução dos serviços emergenciais na rodovia BR-116/RS",
        contract_fornecedor="PLANATERRA-TERRAPLENAGEM E PAVIMENTACAO LTDA",
        doc_numero_controle_pncp_compra="04892707000100-1-000200/2024",
        doc_orgao_cnpj="04892707000100",
        doc_ano=2024,
        doc_sequencial=200,
        doc_object_or_title="Minuta de Contrato — Situação de Emergência",
        doc_text=(
            "EXECUÇÃO DOS SERVIÇOS EMERGENCIAIS NA RODOVIA BR-116/RS "
            "CLÁUSULA DE REAJUSTE. Lei 14.133/2021. data-base 15/03/2024. índice SICRO."
        ),
    )
    assert link.status != DOCUMENT_LINK_CONFLICT
    assert link.signals_usable is True


def test_exact_data_base_full_date_in_clause():
    text = (
        "CLÁUSULA DE REAJUSTE. O preço será reajustado anualmente pelo SINAPI, "
        "tendo como data-base 15/03/2024, correspondente ao orçamento estimado."
    )
    res = extract_exact_data_base(text, document="contrato.pdf", page_hint="12")
    assert res.data_base_exata_localizada is True
    assert res.state == EXACT_DATE_IN_REAJUSTE_CLAUSE
    assert res.primary is not None
    assert res.primary.value_date is not None
    assert res.primary.value_date.isoformat() == "2024-03-15"
    assert is_exact_data_base_state(res.state)


def test_generic_data_base_mention_is_not_exact():
    text = (
        "CLÁUSULA DE REAJUSTE. Os preços serão reajustáveis contados da data-base "
        "do orçamento estimado, conforme legislação."
    )
    res = extract_exact_data_base(text, document="minuta.pdf")
    assert res.data_base_exata_localizada is False
    assert res.state in {GENERIC_RULE_WITHOUT_DATE, "NOT_LOCATED"}
    assert not is_exact_data_base_state(res.state)


def test_signature_not_used_as_exact_data_base():
    text = (
        "Data da assinatura do contrato: 10/01/2024. "
        "CLÁUSULA DE REAJUSTE. Haverá reajuste anual sem data-base numérica aqui."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is False


def test_protocol_assinado_date_is_not_exact_data_base():
    """Skeptic: 'Documento assinado… em: 29/10/2024' must not become data-base."""
    text = (
        "CLÁUSULA DE REAJUSTE. Os preços serão reajustáveis anualmente. "
        "Documento assinado nos termos do Art. 38 do Decreto ao protocolo "
        "22.086.618-1 por: Suellen Azevedo Costa em: 29/10/2024 14:39."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is False
    assert res.primary is None or res.primary.value != "2024-10-29"


def test_timestamp_upload_not_preferred_over_mes_base():
    """Skeptic: 30/12/2024 00:02:53 ANEXAR DOCUMENTOS must not beat MÊS-BASE Abril/2024."""
    text = (
        "QUADRO RESUMO\n"
        "MÊS-BASE: Abril / 2024 - SEM DESONERAÇÃO\n"
        "30/12/2024 00:02:53 DAER/ACI/4347510 ANEXAR DOCUMENTOS 9112\n"
        "CLÁUSULA DE REAJUSTE. Reajuste anual conforme data-base do orçamento."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is True
    assert res.primary is not None
    assert res.primary.value_month == 4
    assert res.primary.value_year == 2024
    assert res.primary.value != "2024-12-30"


def test_instrucao_normativa_calendar_not_competence():
    """Skeptic: 'IN … de 24 de janeiro de 2023' is not data-base competence."""
    text = (
        "CLÁUSULA DE REAJUSTE. O índice será o SICRO XXXXX//202X. "
        "Aplicação de acordo com a Instrução Normativa nº 01/DNIT SEDE, "
        "de 24 de janeiro de 2023, disponibilizada no site do DNIT."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is False
    if res.primary is not None:
        assert res.primary.value not in {"2023-01", "2023-01-24", "2023-01-01"}


def test_ipca_in_atualizacao_monetaria_not_reajuste_index():
    """Skeptic: IPCA under atualização monetária (late payment) ≠ reajuste index."""
    from scripts.commercial.reajuste_14133.io.documents import extract_from_text

    text = (
        "5.13. Pagamento em 30 dias da protocolização da nota fiscal.\n"
        "ATUALIZAÇÃO MONETÁRIA. Em caso de atraso o valor será atualizado pelo IPCA.\n"
        "CLÁUSULA DE REAJUSTE. O reajuste será pelo SICRO com data-base do orçamento."
    )
    scan = extract_from_text(text, doc_type="contrato", url=None, is_official_document=True)
    assert scan.reajuste_clause_mention is True
    assert any("SICRO" in x for x in scan.index_in_clause)
    assert not any(x == "IPCA" or x.startswith("IPCA") for x in scan.index_in_clause)


def test_cartography_lidar_not_construction():
    """Skeptic: cartographic LiDAR/photogrammetry is not material civil obra."""
    obj = (
        "Contratação de empresa especializada para execução de serviços de "
        "engenharia cartográfica incluindo o aerolevantamento fotogramétrico "
        "de alta resolução, perfilamento a LASER aerotransportado e elaboração "
        "de base cartográfica"
    )
    r = classify_construction(obj, razao_social="CONSÓRCIO PARANAMAP")
    assert r.is_construction is False
    assert any("cartograph" in c or "aerolevantamento" in c or "sector" in c for c in r.reason_codes + r.negative_hits)


def test_data_base_sicro_abril_is_exact_competence():
    """Legitimate DATA BASE SICRO: ABRIL 2024 must still pass."""
    text = (
        "DATA BASE SICRO: ABRIL 2024\n"
        "Prazo de Execução: 28 meses\n"
        "CLÁUSULA DE REAJUSTE. Preços reajustáveis no prazo de um ano "
        "contado da data do orçamento estimado."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is True
    assert res.primary is not None
    assert res.primary.value_month == 4
    assert res.primary.value_year == 2024


def test_sinapi_competence_in_clause():
    text = (
        "Cláusula de reajuste: o índice será o SINAPI competência 06/2023 "
        "aplicado após o interregno de 12 meses da data-base."
    )
    res = extract_exact_data_base(text)
    assert res.data_base_exata_localizada is True
    assert res.state in {
        EXACT_COMPETENCE_IN_REAJUSTE_CLAUSE,
        EXACT_DATE_IN_REAJUSTE_CLAUSE,
        COMPETENCE_IN_BUDGET_SPREADSHEET,
    }


def test_technically_verified_pending_tiago_without_human():
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
        human_review_done=False,  # Tiago not yet
        has_valor_potencial=True,
        docs_text_extracted=True,
        document_link_validated=True,
        document_link_status="DOCUMENT_LINK_VERIFIED",
    )
    assert r.status == TECHNICALLY_VERIFIED_PENDING_TIAGO
    assert r.status != OUTREACH_READY
    assert r.gates["revisao_humana_concluida"] is False


def test_outreach_ready_still_requires_human():
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
        has_valor_potencial=True,
        docs_text_extracted=True,
        document_link_validated=True,
        document_link_status="DOCUMENT_LINK_VERIFIED",
    )
    assert r.status == OUTREACH_READY


def test_conflict_blocks_document_link_gate():
    r = evaluate_outreach(
        eligibility_status="STRONG_CANDIDATE",
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
        document_link_validated=False,
        document_link_status="DOCUMENT_LINK_CONFLICT",
    )
    assert r.status != OUTREACH_READY
    assert r.status != TECHNICALLY_VERIFIED_PENDING_TIAGO
    assert r.gates["documento_vinculo_validado"] is False


def test_pdf_extractor_accepts_unlimited_pages_param():
    """Priority path must allow max_pages=None (no 50-page hard stop)."""
    # empty/non-pdf returns None without enforcing 50
    text, n = try_extract_pdf_via_process_documents(b"not-a-pdf", max_pages=None)
    assert text is None
    assert n == 0


def test_doc_types_sought_inventory_covers_required():
    required = {
        "edital",
        "contrato_ou_minuta",
        "orcamento_estimado",
        "planilha_orcamentaria",
        "termo_referencia_ou_projeto_basico",
        "cronograma",
        "apostilas",
        "termos_aditivos",
        "publicacoes_reajuste",
        "medicoes_ou_pagamentos",
    }
    assert required.issubset(set(DOC_TYPES_SOUGHT))


def test_tiago_package_never_forges_outreach_ready(tmp_path):
    portfolios = [
        {
            "cnpj": "82743832000162",
            "razao_social": "PLANATERRA LTDA",
            "sede_uf": "SC",
            "score_fornecedor": 50,
            "outreach_status": DOCUMENT_REQUEST_CANDIDATE,
            "melhor_oportunidade": {
                "contrato_id": "04892707000100-2-000542/2024",
                "objeto": "Pavimentação BR-116",
                "orgao_contratante": "DNIT",
                "valor_original": 100_000_000,
            },
            "contatos": {},
            "contratos": [],
        }
    ]
    deepen = [
        {
            "cnpj": "82743832000162",
            "razao_social": "PLANATERRA LTDA",
            "contrato_id": "04892707000100-2-000542/2024",
            "outreach_status": TECHNICALLY_VERIFIED_PENDING_TIAGO,
            "document_link_status": "DOCUMENT_LINK_VERIFIED",
            "exact_data_base": {
                "state": "EXACT_DATE_IN_REAJUSTE_CLAUSE",
                "primary": {
                    "value": "2024-03-15",
                    "page_or_cell": "12",
                    "excerpt": "data-base 15/03/2024",
                    "document": "contrato.pdf",
                    "state": "EXACT_DATE_IN_REAJUSTE_CLAUSE",
                },
            },
            "index_formula": {"indices": ["SINAPI"], "page": "12", "bound_to_reajuste_clause": True},
            "contact_verifiable": True,
            "email": "contato@planaterra.example",
            "contato_fonte": "site_oficial",
            "human_review_done": False,
        }
    ]
    meta = write_tiago_review_package(
        tmp_path,
        portfolios=portfolios,
        deepen_results=deepen,
        false_positives=[
            {
                "empresa": "BETHA SISTEMAS LTDA",
                "cnpj": "00000000000191",
                "reason": "software",
                "objeto": "licenciamento de software",
                "document_link_status": "DOCUMENT_LINK_CONFLICT",
                "sector_flags": "software",
            }
        ],
        link_conflicts=[
            {
                "empresa": "STRATA",
                "cnpj": "111",
                "contrato_id": "x",
                "document": "lisdex.pdf",
                "status": "DOCUMENT_LINK_CONFLICT",
                "reasons": "pharma",
                "excerpt": "lisdexanfetamina",
            }
        ],
    )
    assert meta["outreach_ready"] == 0
    assert meta["technically_verified_pending_tiago"] >= 1
    assert (tmp_path / "tiago_review_queue.json").exists()
    assert (tmp_path / "technically_verified_pending_tiago.csv").exists()
    assert (tmp_path / "false_positives_removed.csv").exists()
    assert (tmp_path / "document_link_conflicts.csv").exists()
    assert (tmp_path / "checksums.sha256").exists()
    assert (tmp_path / "FINAL-REPORT.md").exists()
    assert (tmp_path / "HEAD.txt").exists()
    payload = (tmp_path / "tiago_review_queue.json").read_text(encoding="utf-8")
    assert "human_review_done_forged" in payload
    assert '"human_review_done_forged": false' in payload.replace("False", "false")
    for row in __import__("json").loads(payload)["rows"]:
        assert row.get("tiago_decision") == ""
        assert row.get("outreach_status") != OUTREACH_READY

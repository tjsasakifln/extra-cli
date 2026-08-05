"""Tests for reajuste 14.133 commercial capability — pure domain + entry points."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.commercial.reajuste_14133 import (
    DATA_BASE_CONFIRMED,
    DATA_BASE_MISSING,
    DATA_BASE_PROXY,
    REGIME_8666,
    REGIME_14133,
    REGIME_UNKNOWN,
    STATUS_ALREADY_ADJUSTED,
    STATUS_CLOSED,
    STATUS_HOT_VERIFIED,
    STATUS_LEGAL_REGIME_UNKNOWN,
    STATUS_NOT_ELIGIBLE,
    UPPER_BOUND_LABEL,
)
from scripts.commercial.reajuste_14133.desk_review import (
    automated_object_triage,
    write_automated_triage,
)
from scripts.commercial.reajuste_14133.domain.dates import (
    add_years,
    consolidate_dates,
    interregno_days,
)
from scripts.commercial.reajuste_14133.domain.eligibility import evaluate_eligibility
from scripts.commercial.reajuste_14133.domain.finance import estimate_reajuste
from scripts.commercial.reajuste_14133.domain.obra_classifier import classify_construction
from scripts.commercial.reajuste_14133.domain.regime import classify_legal_regime
from scripts.commercial.reajuste_14133.domain.scoring import rank_leads, score_lead
from scripts.commercial.reajuste_14133.io.documents import extract_from_text, pncp_contract_url
from scripts.commercial.reajuste_14133.io.source import (
    build_prefilter_query,
    build_prefilter_sql,
    mask_dsn,
)
from scripts.commercial.reajuste_14133.pipeline import classify_row, dedupe_key, is_private_supplier

AS_OF = date(2026, 8, 4)


def _obra_ok():
    return classify_construction(
        "Execução de obra de pavimentação asfáltica e drenagem urbana com empreitada"
    )


def _dates(**kwargs):
    return consolidate_dates(as_of=AS_OF, **kwargs)


def _fin(**kwargs):
    return estimate_reajuste(**kwargs)


# --- Construction classifier ---


def test_construction_true_without_literal_obra():
    r = classify_construction(
        "Contratação de empresa para pavimentação asfáltica e rede de drenagem pluvial"
    )
    assert r.is_construction
    assert r.category in {"pavimentacao_rodoviaria", "drenagem_urbanizacao", "obras_engenharia_geral"}


def test_construction_false_fornecimento_com_palavra_construcao():
    r = classify_construction(
        "Fornecimento de materiais de construção civil: cimento, areia e brita"
    )
    assert not r.is_construction
    assert "negative_vocabulary" in r.reason_codes or "materials" in " ".join(r.reason_codes)


def test_construction_false_weak_token_alone():
    r = classify_construction("Contratação de serviços diversos de manutenção")
    assert not r.is_construction


def test_construction_empty():
    r = classify_construction("")
    assert not r.is_construction
    assert "empty_object" in r.reason_codes


# --- Regime ---


def test_regime_8666_from_document():
    r = classify_legal_regime(document_texts=["Contrato regido pela Lei nº 8.666/1993"])
    assert r.regime == REGIME_8666
    assert r.proven


def test_regime_14133_proven_from_document():
    r = classify_legal_regime(document_texts=["Nos termos da Lei nº 14.133/2021, art. 92"])
    assert r.regime == REGIME_14133
    assert r.proven


def test_regime_unknown_despite_signature_after_2021():
    r = classify_legal_regime(signature_year=2023, published_on_pncp=True)
    assert r.regime == REGIME_UNKNOWN
    assert not r.proven


def test_regime_structured_field():
    r = classify_legal_regime(structured_regime="LEI_14133_2021")
    assert r.proven and r.regime == REGIME_14133


# --- Dates / interregno ---


def test_interregno_less_than_12_months():
    d = _dates(
        orcamento_estimado=date(2025, 10, 1),
        orcamento_source="edital",
        orcamento_confidence="high",
    )
    assert d.data_base_status == DATA_BASE_CONFIRMED
    assert not d.interregno_completo
    assert d.dias_desde_reajuste_aplicavel is not None
    assert d.dias_desde_reajuste_aplicavel < 0


def test_interregno_exactly_12_months():
    base = date(2025, 8, 4)
    d = _dates(
        orcamento_estimado=base,
        orcamento_source="contrato",
        orcamento_confidence="high",
    )
    assert d.interregno_completo
    assert interregno_days(base, AS_OF) == 365  # 2025 not leap for this span? 2025-08-04 to 2026-08-04 = 365


def test_data_base_not_silently_signature():
    d = _dates(data_assinatura=date(2023, 1, 15), inicio_vigencia=date(2023, 2, 1))
    assert d.data_base_status == DATA_BASE_PROXY
    assert d.data_base_effective.source.startswith("proxy:")
    assert d.orcamento_estimado.value is None


def test_data_base_missing_without_proxy():
    d = _dates(allow_proxy_for_prospection=False)
    assert d.data_base_status == DATA_BASE_MISSING


def test_add_years_leap():
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)


# --- Finance ---


def test_finance_no_invented_index():
    f = estimate_reajuste(valor_original=1_000_000, valor_atualizado=1_000_000)
    assert f.indice_contratual is None
    assert f.percentual_acumulado is None
    assert f.valor_potencial is None
    assert any("indice" in x for x in f.limitations)


def test_finance_upper_bound_label_without_saldo():
    f = estimate_reajuste(
        valor_original=2_000_000,
        indice_contratual="INCC-DI",
        indice_base_value=100,
        indice_final_value=110,
    )
    assert f.base_label == UPPER_BOUND_LABEL
    assert f.teto_label == UPPER_BOUND_LABEL
    assert f.valor_potencial is None
    assert f.teto_teorico == Decimal("200000.00")


def test_finance_with_saldo_and_index():
    f = estimate_reajuste(
        valor_original=2_000_000,
        saldo_contratual=500_000,
        indice_contratual="INCC-DI",
        indice_base_value="100",
        indice_final_value="112",
    )
    assert f.base_label == "SALDO_CONTRATUAL"
    assert f.valor_potencial == Decimal("60000.00")
    assert f.percentual_acumulado == Decimal("0.120000")


def test_finance_negative_deflation():
    f = estimate_reajuste(
        valor_original=1_000_000,
        saldo_contratual=1_000_000,
        indice_contratual="IPCA",
        indice_base_value=110,
        indice_final_value=100,
    )
    assert f.percentual_acumulado is not None and f.percentual_acumulado < 0
    assert any("deflacao" in x or "negativo" in x for x in f.limitations)


# --- Eligibility / HOT gates ---


def test_hot_impossible_from_table_dates_only():
    obra = _obra_ok()
    regime = classify_legal_regime(document_texts=["Lei 14.133/2021"], signature_year=2022)
    # Even if regime proven from docs, only_table_dates forces HOT false
    dates = _dates(
        orcamento_estimado=date(2023, 1, 1),
        orcamento_source="edital",
        orcamento_confidence="high",
        data_assinatura=date(2023, 2, 1),
        fim_vigencia=date(2027, 1, 1),
    )
    finance = estimate_reajuste(
        valor_original=5_000_000,
        saldo_contratual=2_000_000,
        indice_contratual="INCC",
        indice_base_value=100,
        indice_final_value=115,
    )
    # Pretend docs not accessible / only table
    elig = evaluate_eligibility(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        docs_accessible=False,
        index_found=True,
        only_table_dates=True,
        has_private_supplier=True,
    )
    assert elig.status != STATUS_HOT_VERIFIED


def test_hot_verified_requires_all_gates():
    obra = _obra_ok()
    regime = classify_legal_regime(document_texts=["Contrato sob a Lei nº 14.133/2021"])
    dates = _dates(
        orcamento_estimado=date(2023, 1, 10),
        orcamento_source="planilha_orcamentaria_edital",
        orcamento_confidence="high",
        fim_vigencia=date(2028, 1, 1),
    )
    finance = estimate_reajuste(
        valor_original=8_000_000,
        saldo_contratual=3_000_000,
        indice_contratual="INCC-DI",
        indice_base_value=100,
        indice_final_value=120,
    )
    elig = evaluate_eligibility(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        docs_accessible=True,
        index_found=True,
        only_table_dates=False,
        already_adjusted=False,
        has_private_supplier=True,
    )
    assert elig.status == STATUS_HOT_VERIFIED
    assert elig.hot_gates_passed == 10
    assert all(elig.hot_gates.values())


def test_already_adjusted():
    obra = _obra_ok()
    regime = classify_legal_regime(document_texts=["Lei 14.133/2021"])
    dates = _dates(
        orcamento_estimado=date(2022, 1, 1),
        orcamento_source="contrato",
        orcamento_confidence="high",
        fim_vigencia=date(2028, 1, 1),
    )
    finance = _fin(valor_original=1e6, saldo_contratual=5e5)
    elig = evaluate_eligibility(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        already_adjusted=True,
        has_private_supplier=True,
    )
    assert elig.status == STATUS_ALREADY_ADJUSTED


def test_closed_contract():
    obra = _obra_ok()
    regime = classify_legal_regime(structured_regime="LEI_14133_2021")
    dates = _dates(
        orcamento_estimado=date(2022, 1, 1),
        orcamento_source="x",
        orcamento_confidence="high",
        fim_vigencia=date(2025, 1, 1),
    )
    finance = _fin(valor_original=1e6, valor_medido=1e6, valor_atualizado=1e6)
    elig = evaluate_eligibility(
        obra=obra,
        regime=regime,
        dates=dates,
        finance=finance,
        is_closed=True,
        has_private_supplier=True,
    )
    assert elig.status == STATUS_CLOSED


def test_regime_8666_not_eligible():
    obra = _obra_ok()
    regime = classify_legal_regime(document_texts=["Lei 8.666/93"])
    dates = _dates(
        data_assinatura=date(2020, 1, 1),
        fim_vigencia=date(2028, 1, 1),
    )
    finance = _fin(valor_original=2e6)
    elig = evaluate_eligibility(
        obra=obra, regime=regime, dates=dates, finance=finance, has_private_supplier=True
    )
    assert elig.status == STATUS_NOT_ELIGIBLE


def test_legal_regime_unknown_path():
    obra = _obra_ok()
    regime = classify_legal_regime(signature_year=2023)
    dates = _dates(data_assinatura=date(2023, 1, 1), fim_vigencia=date(2028, 1, 1))
    finance = _fin(valor_original=3e6)
    elig = evaluate_eligibility(
        obra=obra, regime=regime, dates=dates, finance=finance, has_private_supplier=True
    )
    assert elig.status == STATUS_LEGAL_REGIME_UNKNOWN


# --- Scoring determinism ---


def test_ranking_deterministic():
    leads = [
        {"score_total": 50, "valor_potencial": 100, "contrato_id": "b", "uf": "SC"},
        {"score_total": 80, "valor_potencial": 50, "contrato_id": "a", "uf": "PR"},
        {"score_total": 80, "valor_potencial": 100, "contrato_id": "c", "uf": "RS"},
    ]
    r1 = rank_leads(leads)
    r2 = rank_leads(leads)
    assert [x["contrato_id"] for x in r1] == [x["contrato_id"] for x in r2]
    assert r1[0]["contrato_id"] == "c"


def test_score_decomposition_keys():
    obra = _obra_ok()
    regime = classify_legal_regime(signature_year=2023)
    dates = _dates(data_assinatura=date(2023, 1, 1), fim_vigencia=date(2028, 1, 1))
    finance = _fin(valor_original=5e6)
    elig = evaluate_eligibility(
        obra=obra, regime=regime, dates=dates, finance=finance, has_private_supplier=True
    )
    sc = score_lead(
        eligibility=elig, obra=obra, regime=regime, dates=dates, finance=finance, uf="SC"
    )
    assert set(sc.components) >= {
        "confianca_juridica_documental",
        "atratividade_financeira",
        "urgencia_temporal",
        "saldo_reajustavel_provavel",
        "aderencia_icp_confenge",
        "contatabilidade",
        "qualidade_fontes",
    }
    assert sc.ranking_bucket == "SUL_SC_PRIORITY"


# --- Dedup / private / SQL safety ---


def test_dedupe_same_contrato():
    a = {"contrato_id": "12345678000199-2-000001/2023"}
    b = {"contrato_id": "12345678000199-2-000001/2023"}
    assert dedupe_key(a) == dedupe_key(b)


def test_private_supplier_rejects_prefeitura_name():
    assert not is_private_supplier("12345678000199", "PREFEITURA MUNICIPAL DE X")


def test_private_supplier_accepts_ltda():
    assert is_private_supplier("12345678000199", "ACME CONSTRUTORA LTDA")


def test_sql_injection_uf_sanitized():
    sql = build_prefilter_sql(
        columns=["contrato_id", "valor_total"],
        as_of=AS_OF,
        min_contract_value=1e6,
        uf="SC'; DROP TABLE pncp_supplier_contracts;--",
    )
    assert "DROP" not in sql
    assert "upper(uf) = 'SC'" in sql
    # parameterized form never interpolates UF into SQL text
    q, params = build_prefilter_query(
        columns=["contrato_id", "valor_total"],
        as_of=AS_OF,
        min_contract_value=1e6,
        uf="SC'; DROP TABLE x;--",
    )
    assert "%s" in q
    assert "DROP" not in q
    assert "SC" in params


def test_automated_triage_flags_non_construction_and_is_machine_labeled():
    leads = [
        {
            "contrato_id": "x-1",
            "cnpj": "12345678000199",
            "score_total": 10,
            "classificacao": "LEGAL_REGIME_UNKNOWN",
            "data_base_status": "PROXY_PROSPECTION_ONLY",
            "regime_proven": False,
            "objeto": "PRESTAÇÃO DE SERVIÇOS ESPECIALIZADOS DE GESTÃO OPERACIONAL E DE APOIO À GESTÃO",
            "urls_oficiais": ["https://pncp.gov.br/app/contratos/x"],
        },
        {
            "contrato_id": "x-2",
            "cnpj": "98765432000199",
            "score_total": 12,
            "classificacao": "LEGAL_REGIME_UNKNOWN",
            "data_base_status": "PROXY_PROSPECTION_ONLY",
            "regime_proven": False,
            "objeto": "EXECUÇÃO DOS SERVIÇOS DE MANUTENÇÃO RODOVIÁRIA (CONSERVAÇÃO/RECUPERAÇÃO)",
            "urls_oficiais": ["https://pncp.gov.br/app/contratos/y"],
        },
    ]
    rows = automated_object_triage(leads)
    assert rows[0]["kind"] == "automated_object_triage"
    assert rows[0]["label"] == "MACHINE_ONLY_NOT_HUMAN_REVIEW"
    assert "possible_non_construction_object" in rows[0]["flags"]
    assert "possible_non_construction_object" not in rows[1]["flags"]


def test_automated_triage_does_not_overwrite_human_review(tmp_path):
    human = tmp_path / "human_desk_review_top30.md"
    human.write_text("# human hand-authored\nunique note about CASTILHO BR-235\n", encoding="utf-8")
    leads = [
        {
            "contrato_id": "c1",
            "cnpj": "11111111000191",
            "score_total": 1,
            "objeto": "pavimentação asfáltica",
            "classificacao": "LEGAL_REGIME_UNKNOWN",
            "data_base_status": "PROXY_PROSPECTION_ONLY",
            "regime_proven": False,
            "urls_oficiais": [],
        }
    ]
    meta = write_automated_triage(tmp_path, leads)
    assert (tmp_path / "automated_object_triage.json").exists()
    assert (tmp_path / "automated_precheck.json").exists()
    # human file must remain hand-authored
    assert "unique note about CASTILHO BR-235" in human.read_text(encoding="utf-8")
    assert meta["automated_object_triage_count"] == 1


def test_campaign_human_desk_review_artifact_has_unique_notes():
    """Static campaign artifact must exist with unique per-lead notes (not one template)."""

    root = Path("output/commercial/reajuste_14133/2026-08-04")
    path = root / "human_desk_review_top30.json"
    if not path.exists():
        # artifact is campaign output; skip only if campaign not generated in this env
        import pytest

        pytest.skip("campaign human desk review not present")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("kind") == "human_desk_review"
    reviews = data.get("reviews") or []
    assert len(reviews) == 30
    notesets = [" ".join(r.get("notes") or []) for r in reviews]
    assert len(set(notesets)) == 30, "each lead must have unique hand notes"
    assert data.get("false_positives", 0) >= 1
    assert any(r.get("decision") == "RECLASSIFICAR" for r in reviews)
    # no claim of template-generated operator
    assert "MACHINE" not in json.dumps(data.get("disclaimer"))


def test_mask_dsn_hides_password():
    m = mask_dsn("postgresql://user:s3cret@127.0.0.1:5432/db")
    assert "s3cret" not in m
    assert "***" in m


def test_pncp_url_builder():
    url = pncp_contract_url("12345678000199-2-000015/2024", "12345678000199")
    assert url == "https://pncp.gov.br/app/contratos/12345678000199/2024/15"


def test_extract_index_from_text():
    scan = extract_from_text(
        "O reajuste será pelo INCC-DI, data-base do orçamento estimado.",
        doc_type="contrato",
        url="https://example.invalid/c",
    )
    assert "INCC-DI" in scan.index_candidates or any("INCC" in x for x in scan.index_candidates)
    assert scan.reajuste_clause_mention
    assert scan.data_base_mention


def test_classify_row_never_hot_from_table():
    row = {
        "contrato_id": "11111111000191-2-000001/2023",
        "orgao_cnpj": "22222222000191",
        "orgao_nome": "PREFEITURA TESTE",
        "fornecedor_cnpj": "33333333000191",
        "fornecedor_nome": "CONSTRUTORA XYZ LTDA",
        "objeto_contrato": "Execução de obras de pavimentação e drenagem urbana",
        "valor_total": 5_000_000,
        "data_assinatura": "2023-01-10",
        "data_inicio": "2023-02-01",
        "data_fim": "2028-02-01",
        "data_publicacao": "2023-01-12",
        "uf": "SC",
        "municipio": "Florianópolis",
        "is_active": True,
    }
    lead = classify_row(row, as_of=AS_OF)
    assert lead["classificacao"] != STATUS_HOT_VERIFIED
    assert lead["data_base_status"] in {DATA_BASE_PROXY, DATA_BASE_MISSING}


def test_cli_help_and_dry_run():
    from scripts.commercial.reajuste_14133.cli import build_parser, main

    help_text = build_parser().format_help()
    assert "--as-of" in help_text
    assert "reajuste" in help_text.lower()
    code = main(["--dry-run", "--json", "--as-of", "2026-08-04"])
    assert code == 0


def test_cli_module_entrypoint_importable():
    import scripts.commercial.reajuste_14133.__main__ as m

    assert callable(m.main)


def test_export_no_secrets(tmp_path):
    from scripts.commercial.reajuste_14133.cli import export_run

    run = {
        "run_id": "test",
        "as_of": "2026-08-04",
        "module_version": "1.0.0",
        "campaign": "reajuste_14133",
        "source_mode": "csv",
        "source_dsn_masked": "postgresql://user:***@127.0.0.1/db",
        "funnel": {"examined_raw": 1, "construction": 1, "HOT_VERIFIED": 0, "STRONG_CANDIDATE": 1},
        "metrics": {"top_leads": 1},
        "language_policy": {},
        "top_leads": [
            {
                "ranking": 1,
                "classificacao": "STRONG_CANDIDATE",
                "score_total": 55,
                "score_decomposition": {"confianca_juridica_documental": 0.4},
                "score_penalties": {},
                "cnpj": "12345678000199",
                "razao_social": "TESTE LTDA",
                "contrato_id": "1-2-000001/2023",
                "objeto": "pavimentação asfáltica e drenagem",
                "classificacao_obra": "pavimentacao_rodoviaria",
                "valor_original": 2e6,
                "valor_atualizado": 2e6,
                "regime_legal": "UNKNOWN",
                "regime_proven": False,
                "data_base_status": "PROXY_PROSPECTION_ONLY",
                "urls_oficiais": ["https://pncp.gov.br/app/contratos/1"],
                "evidencias_favoraveis": ["x"],
                "lacunas": ["y"],
                "riscos": ["z"],
                "argumento_comercial": "indícios",
                "canais_contato": {},
                "hot_gates_passed": 2,
                "timestamp_analise": "2026-08-04T00:00:00Z",
                "uf": "SC",
                "dates": {},
                "finance": {"limitations": []},
                "doc_scan": {"evidences": []},
                "module_version": "1.0.0",
                "ranking_bucket": "SUL_SC_PRIORITY",
                "proxima_acao_investigativa": "docs",
            }
        ],
        "nacional": [],
        "sul_sc_priority": [],
        "leads": [],
        "excluded": [{"contrato_id": "x", "reason": "test"}],
    }
    info = export_run(run, tmp_path, dossier_count=1, manual_review=True)
    assert not info["secret_hits"]
    assert (tmp_path / "leads_reajuste_14133.xlsx").exists()
    assert (tmp_path / "executive_brief.md").exists()
    assert (tmp_path / "automated_object_triage.json").exists()
    assert (tmp_path / "automated_precheck.json").exists()
    assert list((tmp_path / "dossiers").glob("*.md"))


def test_checkpoint_resume_skips_raw_fetch(tmp_path):
    from scripts.commercial.reajuste_14133.checkpoint import load_raw_rows, save_raw_rows

    rows = [{"contrato_id": "a", "valor_total": 1}]
    save_raw_rows(tmp_path, rows)
    assert load_raw_rows(tmp_path) == rows


def test_apostila_duplicate_mentions_not_proof_of_absence():
    scan = extract_from_text(
        "Apostila de reajuste e apostila de reajuste do mesmo período.",
        doc_type="publicacao",
        url=None,
    )
    assert scan.apostila_mention
    # pipeline limitations always warn absence is not proof — checked in verify_contract_documents
    from scripts.commercial.reajuste_14133.io.documents import verify_contract_documents

    v = verify_contract_documents(
        contrato_id="1-2-1/2023",
        orgao_cnpj="12345678000199",
        orgao_nome="X",
        objeto="obra de engenharia",
        fetch_remote=False,
    )
    assert any("não prova" in x or "nao prova" in x.lower() for x in v.limitations)


def test_network_failure_documented(monkeypatch):
    from scripts.commercial.reajuste_14133.io import documents as docmod

    def boom(url, timeout=12.0, max_bytes=500_000):
        return None, "URLError: network down", "error"

    monkeypatch.setattr(docmod, "fetch_url_text", boom)
    v = docmod.verify_contract_documents(
        contrato_id="12345678000199-2-000001/2023",
        orgao_cnpj="12345678000199",
        orgao_nome="ORGAO",
        objeto="Execução de obra de engenharia para construção de escola",
        fetch_remote=True,
        max_fetches=1,
    )
    assert v.network_error
    assert any("fetch_error" in x for x in v.limitations)

"""#544 — persisted engineering class, adversarial false positives included."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.contracts.engineering_class import (
    ENGINEERING_CLASSES,
    classify_engineering_class,
)
from scripts.crawl.contracts_crawler import _transform_record
from scripts.testing.real_db_guard import canonical_dsn

ROOT = Path(__file__).resolve().parents[1]


def test_eight_named_classes_are_the_closed_set() -> None:
    assert ENGINEERING_CLASSES == (
        "OBRA_EXECUCAO",
        "OBRA_COM_PROJETO",
        "PROJETO_ENGENHARIA",
        "FISCALIZACAO_GERENCIAMENTO",
        "MANUTENCAO_PREDIAL_INFRA",
        "INSTALACOES",
        "FORNECIMENTO_COM_INSTALACAO",
        "NAO_ENGENHARIA",
    )


def test_secretaria_saneamento_in_orgao_name_is_not_engineering() -> None:
    result = classify_engineering_class(
        objeto="Secretaria Municipal de Saude e Saneamento - aquisicao de generos alimenticios"
    )
    assert result.engineering_class == "NAO_ENGENHARIA"
    assert result.confidence >= 0.7


def test_publicidade_is_not_fiscalizacao() -> None:
    result = classify_engineering_class(
        objeto="Fiscalizacao de campanha de publicidade e propaganda institucional"
    )
    assert result.engineering_class == "NAO_ENGENHARIA"


def test_fundacao_de_pesquisa_is_not_projeto() -> None:
    result = classify_engineering_class(
        objeto="Projeto de pesquisa aplicada em ciencias sociais",
        fornecedor_nome="Fundacao de Amparo a Pesquisa do Estado",
    )
    assert result.engineering_class == "NAO_ENGENHARIA"


def test_equipamento_medico_is_not_manutencao_predial() -> None:
    result = classify_engineering_class(
        objeto="Manutencao de equipamentos medicos e respiradores hospitalares"
    )
    assert result.engineering_class == "NAO_ENGENHARIA"


def test_fiscalizacao_requires_obra_context() -> None:
    ok = classify_engineering_class(
        objeto="Fiscalizacao de obra de pavimentacao asfaltica urbana"
    )
    assert ok.engineering_class == "FISCALIZACAO_GERENCIAMENTO"
    assert ok.confidence >= 0.75
    bare = classify_engineering_class(objeto="Servico de fiscalizacao de contratos administrativos")
    assert bare.engineering_class == "NAO_ENGENHARIA"


def test_projeto_engenharia_is_first_class() -> None:
    result = classify_engineering_class(
        objeto="Elaboracao de projeto executivo de engenharia para escola municipal"
    )
    assert result.engineering_class == "PROJETO_ENGENHARIA"
    assert result.confidence >= 0.75
    assert result.rule_version
    assert result.computed_at


def test_integrado_without_keyword_in_objeto_uses_regime() -> None:
    result = classify_engineering_class(
        objeto="Construcao de unidade de saude com 12 salas",
        regime_execucao_nome="Contratacao integrada",
        categoria_processo_nome="Obras",
    )
    assert result.engineering_class == "OBRA_COM_PROJETO"
    assert "regime_sem_keyword_objeto" in result.evidence
    assert result.confidence >= 0.75


def test_empenho_srp_does_not_inflate_obra_from_empty_object() -> None:
    result = classify_engineering_class(
        objeto="Registro de precos para material de expediente",
        tipo_contrato_nome="Empenho",
        srp=True,
    )
    assert result.engineering_class == "NAO_ENGENHARIA"


def test_obra_execucao_and_instalacoes() -> None:
    obra = classify_engineering_class(objeto="Execucao de obra de pavimentacao asfaltica")
    assert obra.engineering_class == "OBRA_EXECUCAO"
    instal = classify_engineering_class(objeto="Instalacoes hidraulicas e eletricas prediais")
    assert instal.engineering_class == "INSTALACOES"
    supply = classify_engineering_class(objeto="Fornecimento e instalacao de sistema de iluminacao publica")
    assert supply.engineering_class == "FORNECIMENTO_COM_INSTALACAO"


def test_transform_persists_class_fields_on_record() -> None:
    raw = {
        "numeroControlePNCP": "54400000000000000001",
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Prefeitura"},
        "unidadeOrgao": {"nomeUnidade": "Obras", "ufSigla": "SC", "municipioNome": "Florianopolis"},
        "niFornecedor": "11222333000181",
        "tipoPessoa": "PJ",
        "nomeRazaoSocialFornecedor": "Construtora Exemplo Ltda",
        "valorGlobal": 400000.0,
        "dataAssinatura": "2026-03-01",
        "dataPublicacaoPncp": "2026-03-02",
        "dataVigenciaInicio": "2026-03-10",
        "dataVigenciaFim": "2027-03-09",
        "objetoContrato": "Execucao de obra de drenagem urbana",
        "categoriaProcessoNome": "Obras",
    }
    record = _transform_record(raw)
    assert record["engineering_class"] == "OBRA_EXECUCAO"
    assert record["engineering_confidence"] >= 0.75
    assert record["engineering_rule_version"]


LABELED_SAMPLE: list[tuple[str, dict, str]] = [
    ("Execucao de obra de pavimentacao asfaltica", {}, "OBRA_EXECUCAO"),
    ("Elaboracao de projeto executivo de engenharia", {}, "PROJETO_ENGENHARIA"),
    ("Fiscalizacao de obra de drenagem urbana", {}, "FISCALIZACAO_GERENCIAMENTO"),
    ("Manutencao predial de edificio publico", {}, "MANUTENCAO_PREDIAL_INFRA"),
    ("Instalacoes hidraulicas prediais", {}, "INSTALACOES"),
    ("Fornecimento e instalacao de iluminacao publica", {}, "FORNECIMENTO_COM_INSTALACAO"),
    (
        "Construcao de escola municipal",
        {"regime_execucao_nome": "Contratacao integrada"},
        "OBRA_COM_PROJETO",
    ),
    ("Aquisicao de generos alimenticios", {}, "NAO_ENGENHARIA"),
    ("Secretaria de Saude e Saneamento - merenda escolar", {}, "NAO_ENGENHARIA"),
    ("Fiscalizacao de campanha de publicidade", {}, "NAO_ENGENHARIA"),
    (
        "Projeto de pesquisa em ciencias humanas",
        {"fornecedor_nome": "Fundacao de Amparo a Pesquisa"},
        "NAO_ENGENHARIA",
    ),
    ("Manutencao de equipamentos medicos", {}, "NAO_ENGENHARIA"),
]


def test_reproducible_labeled_sample_precision_at_075() -> None:
    high = []
    for objeto, extra, expected in LABELED_SAMPLE:
        result = classify_engineering_class(objeto=objeto, **extra)
        if result.confidence >= 0.75:
            high.append((result.engineering_class, expected, objeto))
    assert high
    correct = sum(1 for predicted, expected, _ in high if predicted == expected)
    precision = correct / len(high)
    assert precision >= 0.90, (precision, high)


def test_migration_is_versioned_and_auditable() -> None:
    sql = (ROOT / "db/migrations/110_contract_engineering_class.sql").read_text(encoding="utf-8")
    for name in ENGINEERING_CLASSES:
        assert name in sql
    assert "confidence" in sql
    assert "rule_version" in sql
    assert "computed_at" in sql
    assert "apply_contract_engineering_class" in sql


@pytest.mark.real_db
def test_class_round_trip_persists_all_audit_fields() -> None:
    import psycopg2
    import psycopg2.extras

    from scripts.contracts.engineering_class import attach_engineering_class, stamp_engineering_class_labels

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or canonical_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    record = {
        "contrato_id": "eng-class-544",
        "orgao_cnpj": "12345678000199",
        "objeto_contrato": "Elaboracao de projeto estrutural de edificacao",
        "fornecedor_nome": "Escritorio de Projetos Ltda",
        "data_publicacao": "2026-03-01",
        "source": "pncp",
        "source_id": "eng-class-544",
        "supplier_id_type": "UNKNOWN",
    }
    attach_engineering_class(record)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'contract_engineering_class'"
            )
            if cur.fetchone() is None:
                pytest.fail("migration 110 not applied")
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (json.dumps([record], default=str),),
            )
        stamped = stamp_engineering_class_labels(conn, [record])
        assert stamped == 1
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT engineering_class, confidence, evidence, rule_version, computed_at
                FROM contract_engineering_class WHERE contrato_id = %s
                """,
                (record["contrato_id"],),
            )
            row = cur.fetchone()
            assert row["engineering_class"] == "PROJETO_ENGENHARIA"
            assert float(row["confidence"]) >= 0.75
            assert row["rule_version"]
            assert row["computed_at"] is not None
            assert row["evidence"]
        conn.commit()
    finally:
        conn.close()

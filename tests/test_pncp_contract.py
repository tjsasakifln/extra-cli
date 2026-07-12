from __future__ import annotations

from datetime import date

import pytest

from scripts.crawl.pncp_contract import (
    DEFAULT_MODALIDADES,
    ModalidadePNCP,
    PNCPTargetError,
    build_pncp_public_link,
    format_pncp_date,
    parse_target,
)
from scripts.crawl.pncp_engineering import classify_engineering
from scripts.crawl.pncp_geo import GeographyResolver


def test_modalidades_oficiais_catalogadas():
    assert ModalidadePNCP.DISPENSA.value == 8
    assert ModalidadePNCP.INEXIGIBILIDADE.value == 9
    assert ModalidadePNCP.CREDENCIAMENTO.value == 12
    assert ModalidadePNCP.LEILAO_PRESENCIAL.value == 13
    assert len(DEFAULT_MODALIDADES) == 19


def test_formato_oficial_data_pncp():
    assert format_pncp_date(date(2026, 5, 14)) == "20260514"


def test_parse_target_suportado():
    assert parse_target("sc").kind == "sc"
    assert parse_target("within_200km").kind == "within_200km"
    assert parse_target("municipio:4205407").value == "4205407"
    assert parse_target("municipio_nome:Palhoça").value == "Palhoça"
    assert parse_target("cnpj:82.892.282/0001-43").value == "82892282000143"
    assert parse_target("engineering").kind == "engineering"


def test_parse_target_invalido():
    with pytest.raises(PNCPTargetError):
        parse_target("municipio:123")
    with pytest.raises(PNCPTargetError):
        parse_target("xpto")


def test_link_pncp_separado_do_sistema_origem():
    assert build_pncp_public_link(orgao_cnpj="12345678000199", ano_compra=2026, sequencial_compra=225) == (
        "https://pncp.gov.br/app/editais/12345678000199/2026/225"
    )
    assert build_pncp_public_link(orgao_cnpj=None, ano_compra=2026, sequencial_compra=225) is None


def test_classificacao_positiva_engenharia():
    result = classify_engineering(
        {
            "objeto_compra": "Contratação de empresa para reforma e instalações elétricas de escola municipal",
            "informacao_complementar": "com fornecimento de material e mão de obra",
            "modalidade_nome": "Concorrência - Eletrônica",
            "valor_total_estimado": 800000,
        },
        items=[{"descricao": "reforma geral e instalação elétrica"}],
        documents=[{"titulo": "projeto executivo"}],
    )
    assert result.score >= 80
    assert result.is_engineering is True
    assert "REFORMA" in result.categories


def test_classificacao_negativa_falso_positivo():
    result = classify_engineering(
        {
            "objeto_compra": "Licença de software de engenharia de dados",
            "modalidade_nome": "Pregão - Eletrônico",
            "valor_total_estimado": 50000,
        }
    )
    assert result.is_engineering is False
    assert result.exclusion_reason == "software_only"


def test_distancia_e_prioridade_geografica():
    resolver = GeographyResolver(
        [
            {
                "cnpj_8": "12345678",
                "municipio": "Florianópolis",
                "codigo_ibge": "4205407",
                "latitude": -27.5954,
                "longitude": -48.5480,
            },
            {
                "cnpj_8": "87654321",
                "municipio": "Chapecó",
                "codigo_ibge": "4204202",
                "latitude": -27.1004,
                "longitude": -52.6152,
            },
        ]
    )
    fln = resolver.resolve({"uf": "SC", "codigo_municipio_ibge": "4205407"})
    xap = resolver.resolve({"uf": "SC", "codigo_municipio_ibge": "4204202"})
    assert fln.within_200km is True
    assert fln.geographic_priority == "PRIORIDADE_1"
    assert xap.within_200km is False
    assert xap.geographic_priority == "PRIORIDADE_2"

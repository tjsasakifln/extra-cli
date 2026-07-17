"""Tests for UF helpers on contracts_crawler (SC filter from unidade)."""

from __future__ import annotations

from scripts.crawl import contracts_crawler as cc


def test_uf_from_unidade():
    assert cc.uf_from_unidade({"unidadeOrgao": {"ufSigla": "sc"}}) == "SC"
    assert cc.uf_from_unidade({"unidadeOrgao": {"ufSigla": ""}}) is None
    assert cc.uf_from_unidade({}) is None


def test_filter_raw_by_uf():
    records = [
        {
            "numeroControlePNCP": "a",
            "unidadeOrgao": {"ufSigla": "SC"},
            "niFornecedor": "12345678000199",
            "nomeRazaoSocialFornecedor": "F1",
            "objetoContrato": "x",
            "valorGlobal": 10,
            "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "O"},
        },
        {
            "numeroControlePNCP": "b",
            "unidadeOrgao": {"ufSigla": "PR"},
            "niFornecedor": "12345678000199",
            "nomeRazaoSocialFornecedor": "F2",
            "objetoContrato": "y",
            "valorGlobal": 20,
            "orgaoEntidade": {"cnpj": "00000000000191", "razaoSocial": "O"},
        },
    ]
    sc_only = cc.filter_raw_by_uf(records, "SC")
    assert len(sc_only) == 1
    assert sc_only[0]["numeroControlePNCP"] == "a"

    transformed = cc.transform_with_uf_filter(records, uf="SC")
    assert len(transformed) == 1
    assert transformed[0].get("uf") == "SC"

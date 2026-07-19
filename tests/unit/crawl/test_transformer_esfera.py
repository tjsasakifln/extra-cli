from scripts.crawl.transformer import transform_pncp_item

def _item(esfera):
    return {
        "numeroControlePNCP": "12345678000199-1-000001/2026",
        "objetoCompra": "x",
        "valorTotalEstimado": 1,
        "situacaoCompraNome": "Divulgada",
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "TESTE", "esferaId": esfera},
        "unidadeOrgao": {"ufSigla": "SC", "municipioNome": "Florianopolis", "codigoMunicipioIbge": "4205407"},
        "dataPublicacaoPncp": "2026-07-01T00:00:00Z",
    }

def test_esfera_letter_m_to_3():
    assert transform_pncp_item(_item("M"))["esfera_id"] == "3"

def test_esfera_letter_e_to_2():
    assert transform_pncp_item(_item("E"))["esfera_id"] == "2"

def test_esfera_letter_f_to_1():
    assert transform_pncp_item(_item("F"))["esfera_id"] == "1"

def test_esfera_n_becomes_null():
    assert transform_pncp_item(_item("N"))["esfera_id"] is None

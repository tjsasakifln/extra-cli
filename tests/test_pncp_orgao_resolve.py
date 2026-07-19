from scripts.entity_identity.pncp_orgao_resolve import normalize_name, pick_match, digits


def test_normalize_strips_accents():
    assert "SAO JOSE" in normalize_name("São José")


def test_pick_prefers_cnpj8_prefix():
    hits = [
        {"cnpj": "99999999000199", "razaoSocial": "OUTRO"},
        {"cnpj": "12345678000190", "razaoSocial": "MUNICIPIO DE TESTE"},
    ]
    m = pick_match("12345678", "MUNICIPIO DE TESTE", hits)
    assert m is not None
    assert m[0] == "12345678000190"
    assert m[1] == "cnpj8_prefix"


def test_digits():
    assert digits("12.345.678/0001-90") == "12345678000190"

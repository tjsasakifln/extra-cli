"""Unit tests for CNPJ-14 matriz resolution (check digits + soft name)."""
from scripts.ops.resolve_cnpj14_matriz import cnpj14_matriz, soft_name_match, cnpj_check_digits


def test_known_public_entity_comcap():
    assert cnpj14_matriz("82511825") == "82511825000135"


def test_check_digits_length():
    assert len(cnpj_check_digits("825118250001")) == 2


def test_soft_name_match_prefeitura():
    assert soft_name_match("MUNICIPIO DE BLUMENAU", "PREFEITURA MUNICIPAL DE BLUMENAU")


def test_soft_name_empty_api_allows():
    assert soft_name_match("FUNDO X", "")

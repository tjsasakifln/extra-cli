"""Identity safety for PNCP orgao resolve — never cross CNPJ roots."""
from scripts.entity_identity.pncp_orgao_resolve import pick_match


def test_prefers_same_cnpj8_prefix():
    hits = [
        {"cnpj": "10570099000110", "razaoSocial": "FUNDO MUNICIPAL DE SAUDE DE LAGUNA"},
        {"cnpj": "48865663000199", "razaoSocial": "ABRIGO INSTITUCIONAL ANA"},
    ]
    cnpj, method, _ = pick_match("48865663", "ABRIGO INSTITUCIONAL ANA ANTONINA", hits)
    assert cnpj.startswith("48865663")
    assert method == "cnpj8_prefix"


def test_rejects_cross_root_name_exact():
    hits = [{"cnpj": "11111111000111", "razaoSocial": "PREFEITURA MUNICIPAL DE BLUMENAU"}]
    assert pick_match("82669037", "PREFEITURA MUNICIPAL DE BLUMENAU", hits) is None


def test_rejects_cross_root_token_containment():
    hits = [{"cnpj": "10570099000110", "razaoSocial": "FUNDO MUNICIPAL DE SAUDE DE LAGUNA CARAPA"}]
    assert pick_match("48865663", "ABRIGO INSTITUCIONAL ANA ANTONINA ANTONIO", hits) is None

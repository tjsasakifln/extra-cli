"""AC6/AC7/AC8 — identidade de empresa por VETOR FIXO, nunca ``hash == hash``.

Risco aberto #1 da story: se o consumidor mudar o salt, o separador ou o
truncamento de ``hashCnpj``, TODO lookup quebra silenciosamente (404 em massa,
sem excecao em lugar nenhum). A unica mitigacao possivel e vetor fixo + a
proveniencia congelada em ``docs/contracts/confenge-live-intelligence-v1.md``.

Os digests esperados abaixo sao a reimplementacao independente da funcao do
consumidor (``scripts/conversion/cnpj.cjs`` @ blob ``8b88a894e``):
``sha256("confenge-conversion|" + cnpj14).hexdigest()[:16]``, calculada aqui a
partir da DEFINICAO, nao de ``identity.py``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pytest

from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence.fit import evaluate_fit
from scripts.confenge_live_intelligence.identity import (
    CNPJ_DIGEST_LENGTH,
    CNPJ_DIGEST_SALT,
    COMPANY_REF_PREFIX,
    cnpj_digest,
    company_ref_from_root8,
    only_digits,
)

UTC_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _reference_digest(cnpj14: str) -> str:
    """Reimplementacao do ``hashCnpj`` do consumidor, a partir da definicao."""
    return hashlib.sha256(f"confenge-conversion|{cnpj14}".encode()).hexdigest()[:16]


# Vetores FIXOS: valor literal, nao derivado no momento do teste. Se alguem mudar
# a formula, estes numeros mudam e a mudanca aparece no diff.
FIXED_VECTORS: tuple[tuple[str, str], ...] = (
    ("11222333000181", "b1e38ce6b408a119"),
    ("11222333000262", "e3a9c746f2818389"),
    ("12345678000195", "d67fda759f405f42"),
)


@pytest.mark.parametrize(("cnpj", "expected"), FIXED_VECTORS)
def test_cnpj_digest_matches_frozen_vector(cnpj: str, expected: str) -> None:
    assert cnpj_digest(cnpj) == expected
    # Cinto e suspensorio: o vetor congelado tambem bate com a reimplementacao
    # independente da definicao do consumidor.
    assert _reference_digest(cnpj) == expected


def test_cnpj_digest_formula_components_are_the_consumer_ones() -> None:
    assert CNPJ_DIGEST_SALT == "confenge-conversion"
    assert CNPJ_DIGEST_LENGTH == 16
    assert cnpj_digest("11222333000181") == hashlib.sha256(b"confenge-conversion|11222333000181").hexdigest()[:16]


def test_cnpj_digest_accepts_punctuation_like_the_consumer() -> None:
    """``onlyDigits`` do consumidor reduz a ``raw.replace(/\\D/g,"")``."""
    assert cnpj_digest("11.222.333/0001-81") == cnpj_digest("11222333000181")
    assert only_digits("11.222.333/0001-81") == "11222333000181"


@pytest.mark.parametrize("bad", ["", "123", "123456", "112223330001812", None, "abcdefghijklmn"])
def test_cnpj_digest_returns_none_never_empty_string(bad: str | None) -> None:
    """AC6 — ``buyer_digest: ""`` e descarte silencioso, proibido por construcao."""
    result = cnpj_digest(bad)
    assert result is None
    assert result != ""


def test_buyer_digest_uses_the_same_function_as_company_digest() -> None:
    """AC6 — nenhum SEGUNDO esquema de identidade."""
    cnpj = "12345678000195"
    assert cnpj_digest(cnpj) == _reference_digest(cnpj)


# --- company_ref (§B.2 / AC8) ----------------------------------------------


def test_company_ref_matches_the_migration_105_check() -> None:
    ref = company_ref_from_root8("11222333")
    assert ref.startswith(COMPANY_REF_PREFIX)
    import re

    assert re.fullmatch(r"^cref1:[0-9a-f]{32}$", ref), ref
    expected = "cref1:" + hashlib.sha256(b"confenge-live-intelligence|company_ref|v1|11222333").hexdigest()[:32]
    assert ref == expected


def test_company_ref_is_frozen_vector() -> None:
    assert company_ref_from_root8("11222333") == "cref1:8def98a00f44b26b792fa3dcd75f10bb"


@pytest.mark.parametrize("bad", ["", "1122233", "112223334", "abcdefgh"])
def test_company_ref_refuses_invalid_root(bad: str) -> None:
    with pytest.raises(ValueError):
        company_ref_from_root8(bad)


def test_n_establishment_digests_map_to_one_company_ref() -> None:
    """AC7/AC8 — N digests publicos, UM pseudonimo interno."""
    company = li_schema.LiveCompany(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_establishment_cnpjs=("11222333000181", "11222333000262"),
        most_recent_contracting_date=date(2026, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    digests = {cnpj_digest(c) for c in company.observed_establishment_cnpjs}
    assert len(digests) == 2
    assert None not in digests
    assert company.company_ref() == company_ref_from_root8("11222333")


def test_company_ref_is_a_method_not_a_payload_field() -> None:
    """§B.2 — como campo entraria em ``COMPANY_PAYLOAD_KEYS`` e em ``portfolio_hash()``."""
    assert "company_ref" not in li_schema.COMPANY_PAYLOAD_KEYS
    assert callable(li_schema.LiveCompany.company_ref)


def test_establishment_column_is_in_the_payload_keyset() -> None:
    """§B.3 — e o que justifica o bump de ``SCHEMA_VERSION`` para 1.1 (AC11)."""
    assert "observed_establishment_cnpjs" in li_schema.COMPANY_PAYLOAD_KEYS
    assert li_schema.SCHEMA_VERSION == "confenge-live-intelligence-schema/1.1"
    assert li_schema.ENGINE_VERSION == "1.1"


# --- nao-regressao de fit (AC6) --------------------------------------------


def _opportunity(orgao_cnpj: str | None) -> li_schema.LiveOpportunity:
    return li_schema.LiveOpportunity(
        opportunity_id="LI-TEST-FIT-1",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de escola municipal com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        valor_state=li_schema.OBSERVED,
        modalidade="Pregao",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj=orgao_cnpj,
        orgao_state=li_schema.OBSERVED if orgao_cnpj else li_schema.UNKNOWN,
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
        reason_codes=() if orgao_cnpj else (li_schema.REASON_ORGAO_MISSING,),
    )


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_objects=("Reforma de escola municipal com estrutura metalica",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000195",),
        observed_establishment_cnpjs=("11222333000181",),
        most_recent_contracting_date=date(2026, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


def test_dim_comparable_buyer_reads_the_internal_field_not_the_public_projection() -> None:
    """AC6 — a mudanca de ``compradores`` e FOLHA: nenhum resultado de fit muda.

    ``fit.py`` compara ``opportunity.orgao_cnpj in company.observed_buyer_cnpjs``,
    o campo INTERNO, a montante da projecao publica.
    """
    as_of = date(2026, 9, 2)
    match = evaluate_fit(_company(), _opportunity("12345678000195"), as_of=as_of)
    assert match.dim_comparable_buyer == li_schema.MATCH

    no_match = evaluate_fit(_company(), _opportunity("99888777000166"), as_of=as_of)
    assert no_match.dim_comparable_buyer == li_schema.NO_MATCH

    unknown_portfolio = evaluate_fit(_company(observed_buyer_cnpjs=()), _opportunity("12345678000195"), as_of=as_of)
    assert unknown_portfolio.dim_comparable_buyer == li_schema.UNKNOWN

    unknown_opportunity = evaluate_fit(_company(), _opportunity(None), as_of=as_of)
    assert unknown_opportunity.dim_comparable_buyer == li_schema.UNKNOWN


def test_establishment_column_does_not_change_fit_results() -> None:
    """``observed_establishment_cnpjs`` nao participa de nenhuma dimensao de fit."""
    as_of = date(2026, 9, 2)
    without = evaluate_fit(_company(observed_establishment_cnpjs=()), _opportunity("12345678000195"), as_of=as_of)
    with_many = evaluate_fit(
        _company(observed_establishment_cnpjs=("11222333000181", "11222333000262")),
        _opportunity("12345678000195"),
        as_of=as_of,
    )
    assert without.fit_hash() == with_many.fit_hash()
    assert without.fit_state == with_many.fit_state

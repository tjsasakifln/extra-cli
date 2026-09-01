"""AC 8 / AC 15 — the named regression of the naive lexical detector.

A regex over the rendered copy has a measured 100% false-positive rate (43/43)
because vigência vocabulary lives inside the *quoted contract object*, not in an
assertion. These leads are real production copy from release
``run-adb0097e32b02188``: their ``why_now`` contains "em execução", and they must
classify ``SAFE_NO_CURRENT_CLAIM``.
"""

from __future__ import annotations

import re
from datetime import date

import pytest

from scripts.confenge_claim_safety.claim_surface import claim_surface, detect_temporal_claim
from scripts.confenge_claim_safety.classify import classify_lead
from scripts.confenge_claim_safety.policy import SAFE_NO_CURRENT_CLAIM
from tests.confenge_claim_safety.conftest import PORTFOLIO_REVIEW_TEXT, contract, lead

TODAY = date(2026, 9, 1)

NAIVE_DETECTOR = re.compile(r"vigente|em execu[çc][ãa]o|em andamento|ativo", re.IGNORECASE)

# Verbatim objects from the production release whose text carries execution words.
PRODUCTION_OBJECTS = [
    (
        "Contratação de empresa especializada em execução de obras de EMPREENDIMENTOS "
        "HABITACIONAIS para construção de 50 (cinquenta) unidades habitacionais no "
        "Município de Encantado - RS."
    ),
    (
        "Contratacao de empresa para prestacao de servicos em execucao global para "
        "construcao de quadra poliesportiva na E.M.F 15 de Novembro localizada no "
        "Municipio de Ijui - RS."
    ),
    (
        "Contratação de empresa especializada em execução de obras e serviços de "
        "engenharia para execução da Reforma parcial do canteiro central da Avenida "
        "Principal de Chupinguaia - RO."
    ),
]


def _portfolio_lead(objeto: str, *, code: str = "PORTFOLIO_REVIEW") -> dict:
    linked = contract(contract_id="c-fp", objeto=objeto, end_date="2027-01-21")
    return lead(
        cnpj14="12345678000195",
        why_now_code=code,
        why_now=PORTFOLIO_REVIEW_TEXT.format(objeto=objeto[:140], orgao=linked["agency"], uf=linked["uf"]),
        contracts=[linked],
    )


@pytest.mark.parametrize("objeto", PRODUCTION_OBJECTS)
@pytest.mark.parametrize("code", ["PORTFOLIO_REVIEW", "INSUFFICIENT_FACTS"])
def test_ac8_objeto_with_execution_words_is_not_a_present_claim(objeto: str, code: str) -> None:
    payload = _portfolio_lead(objeto, code=code)
    # The naive detector fires on the rendered copy — that is the bug being pinned.
    assert NAIVE_DETECTOR.search(payload["messaging_context"]["why_now"])
    # Classification is by template plus evidence-stripped surface, so it does not.
    assert classify_lead(payload, today=TODAY).safety_class == SAFE_NO_CURRENT_CLAIM


@pytest.mark.parametrize("objeto", PRODUCTION_OBJECTS)
def test_ac8_execution_words_do_not_survive_evidence_stripping(objeto: str) -> None:
    surface = claim_surface(_portfolio_lead(objeto))
    assert not NAIVE_DETECTOR.search(surface), f"evidence leaked into the assertion surface: {surface!r}"
    assert detect_temporal_claim(surface) == "NONE"


def test_ac8_shared_boilerplate_prefix_does_not_truncate_the_stripped_span() -> None:
    """Two contracts opening identically must not leave half an object standing.

    This is the exact defect the first production dry-run exposed: removing the
    shorter shared prefix of a *different* contract left "em execução …" in the
    surface and produced five false ``UNSAFE_PRESENT_CLAIM`` leads.
    """
    quoted = PRODUCTION_OBJECTS[0]
    sibling = "Contratação de empresa especializada em serviços de limpeza urbana."
    payload = lead(
        cnpj14="12345678000195",
        why_now_code="PORTFOLIO_REVIEW",
        why_now=PORTFOLIO_REVIEW_TEXT.format(objeto=quoted[:140], orgao="MUNICIPIO DE ENCANTADO", uf="RS"),
        contracts=[
            contract(contract_id="c-sibling", objeto=sibling, end_date="2027-01-21"),
            contract(contract_id="c-quoted", objeto=quoted, end_date="2027-01-21"),
        ],
    )
    surface = claim_surface(payload)
    assert "execução" not in surface, surface
    assert classify_lead(payload, today=TODAY).safety_class == SAFE_NO_CURRENT_CLAIM

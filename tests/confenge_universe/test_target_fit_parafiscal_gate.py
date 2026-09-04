"""ACs 21-24 — the parafiscal gate reaches the path that governs the outbound.

Iteration 1 of this story placed the parafiscal exclusion in
`identity.resolve_identity`, which `classify_target_fit` never calls (its only
call site is `aggregate.py:336`). Measured in production, 3 of the 4 Sistema S
roots stayed TARGET_CONFIRMED. These tests exercise the gate on the layer that
actually feeds the outbound: `classify_target_fit`.

Supplier names below are REAL production `fornecedor_nome` variants of the 4
roots (contract objects are abbreviated; the names are not — the whole point of
the C4 surface is that name variance is what makes the gate deterministic).
"""

from __future__ import annotations

import pytest

from scripts.confenge_universe.parafiscal import (
    PARAFISCAL_INSTITUTIONAL_MARKERS,
    match_parafiscal_institutional,
)
from scripts.confenge_universe.target_fit import (
    TARGET_CONFIRMED,
    TARGET_OUT_OF_SCOPE,
    classify_target_fit,
)

PARAFISCAL_REASON = "parafiscal_institutional_hard_out"

EXECUTION_OBJECT = (
    "EXECUCAO DE OBRA DE REFORMA E AMPLIACAO DA UNIDADE, "
    "COM FUNDACAO EM SAPATA CORRIDA E ESTRUTURA EM CONCRETO ARMADO"
)


def _contract(nome: str, objeto: str = EXECUTION_OBJECT, idx: int = 0) -> dict[str, object]:
    return {
        "contrato_id": f"ct-{idx}",
        "fornecedor_nome": nome,
        "objeto_contrato": objeto,
        "orgao_nome": "ORGAO TESTE",
        "valor_total": 1_000_000.0,
    }


# --------------------------------------------------------------------------
# AC 21 — the 4 real Sistema S roots leave TARGET_CONFIRMED
# --------------------------------------------------------------------------

# (cnpj_raiz, entity, razao_social as the loader would pick it, n execution contracts
#  measured in production for the post-change classifier)
REAL_SISTEMA_S_ROOTS = [
    pytest.param(
        "03575238",
        "SESC - ADMINISTRACAO REGIONAL NO ESTADO DO RIO GRANDE DO SUL",
        6,
        id="03575238-sesc-rs",
    ),
    pytest.param(
        "03709814",
        "SERVICO NACIONAL DE APRENDIZAGEM COMERCIAL",
        3,
        id="03709814-senac",
    ),
    pytest.param(
        "03776284",
        "SERVICO NACIONAL DE APRENDIZAGEM INDUSTRIAL",
        3,
        id="03776284-senai",
    ),
    pytest.param(
        "16589137",
        "SERVICO DE APOIO AS MICRO E PEQUENAS EMPRESAS DE MINAS GERAIS",
        0,
        id="16589137-sebrae-mg",
    ),
    pytest.param(
        "27080530",
        "SEBRAE ES SERVICO DE APOIO AS MICRO E PEQUENAS EMPRESAS DO ESPIRITO SANTO",
        3,
        id="27080530-sebrae-es",
    ),
]


@pytest.mark.parametrize(("raiz", "razao_social", "n_exec_real"), REAL_SISTEMA_S_ROOTS)
def test_real_sistema_s_roots_leave_target_confirmed(
    raiz: str, razao_social: str, n_exec_real: int
) -> None:
    """AC 21 — the 4 roots that survived iteration 1 now return OUT_OF_SCOPE.

    The portfolios reproduce the production-measured `n_exec` (6/3/3/0): the
    SEBRAE/MG fixture carries ZERO execution contracts, as measured, instead of
    a synthetic minimum of one.
    """
    contracts = [_contract(razao_social, idx=i) for i in range(n_exec_real)]
    # Non-execution ballast, so every portfolio is non-empty and the C4 surface
    # is exercised even when n_exec == 0 (the real SEBRAE/MG case).
    contracts += [
        _contract(razao_social, "INSCRICAO EM SEMINARIO DE GESTAO", idx=900 + i)
        for i in range(2)
    ]
    decision = classify_target_fit(
        razao_social=razao_social,
        nome_fantasia=None,
        contracts=contracts,
        cnae_principal=None,
        sector_fit="CONSTRUCTION_CONFIRMED",
        activity_class="CONSTRUCTION",
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE, raiz
    assert PARAFISCAL_REASON in decision.target_fit_reason_codes
    # AC 21 — the production-measured n_exec (6/3/3/0) stays auditable.
    assert decision.relevant_execution_contract_count == n_exec_real, raiz


def test_gate_preserves_the_real_execution_contract_count() -> None:
    """AC 21 — the suppressed result keeps the evidence that motivated it.

    A suppressor that zeroes the evidence is not contestable. Production
    measurement for SESC-RS is n_exec=6 over 858 contracts.
    """
    contracts = [
        _contract("SERVICO SOCIAL DO COMERCIO", idx=i) for i in range(6)
    ] + [
        _contract(
            "SERVICO SOCIAL DO COMERCIO",
            "AQUISICAO DE MATERIAL DE EXPEDIENTE",
            idx=100 + i,
        )
        for i in range(3)
    ]
    decision = classify_target_fit(
        razao_social="SERVICO SOCIAL DO COMERCIO",
        contracts=contracts,
        sector_fit="CONSTRUCTION_CONFIRMED",
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE
    assert decision.relevant_execution_contract_count == 6
    # NOT merely "evidence is non-empty": the gate always appends its own
    # PARAFISCAL_NAME entry, so a non-empty check would pass even if every
    # execution record had been wiped. Assert the execution evidence itself.
    execution_evidence = [
        e for e in decision.target_fit_evidence if e.get("type") == "CONTRACT_EXECUTION"
    ]
    assert len(execution_evidence) == 6
    assert any(e.get("type") == "PARAFISCAL_NAME" for e in decision.target_fit_evidence)


# --------------------------------------------------------------------------
# AC 22 — unconditional and deterministic over the C4 name surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "razao_social",
    ["SESCRS", "SESCRS - ADM REG RS", "SEBRAEMG", "SERVICO DE APOIO AS MICRO E PEQUENAS EM"],
)
def test_non_matching_razao_social_is_saved_by_a_matching_supplier_name(
    razao_social: str,
) -> None:
    """AC 22 — real production variants that match NO marker on their own.

    `loader._load_contracts` picks `razao_social` as the first non-null
    `fornecedor_nome` of a query without ORDER BY, so which variant wins is
    non-deterministic. The gate must not depend on that draw.
    """
    assert match_parafiscal_institutional(razao_social) is None, (
        "fixture invalid: this name is supposed NOT to match on its own"
    )
    decision = classify_target_fit(
        razao_social=razao_social,
        contracts=[
            _contract(razao_social, idx=0),
            _contract("SERVICO SOCIAL DO COMERCIO - ADMINISTRACAO REGIONAL", idx=1),
        ],
        sector_fit="CONSTRUCTION_CONFIRMED",
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE
    assert PARAFISCAL_REASON in decision.target_fit_reason_codes


def test_gate_has_no_n_exec_zero_clause() -> None:
    """AC 22 — a parafiscal entity with >= 3 execution contracts is still OUT.

    This is the exact defect of the pre-existing `_name_hard_out`, which is
    gated on `n_exec == 0` and therefore did not fire for SESC/SENAC/SENAI.
    """
    contracts = [_contract("SENAI DEPARTAMENTO REGIONAL", idx=i) for i in range(5)]
    decision = classify_target_fit(
        razao_social="SENAI DEPARTAMENTO REGIONAL",
        contracts=contracts,
        cnae_principal="4120400",
        sector_fit="CONSTRUCTION_CONFIRMED",
        activity_class="CONSTRUCTION",
    )
    assert decision.relevant_execution_contract_count >= 3
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE


def test_gate_reports_which_marker_matched() -> None:
    decision = classify_target_fit(
        razao_social="MITRA DIOCESANA DE SAO JOSE",
        contracts=[_contract("MITRA DIOCESANA DE SAO JOSE")],
    )
    assert "parafiscal_marker:mitra diocesana" in decision.target_fit_reason_codes


def test_nome_fantasia_is_part_of_the_surface() -> None:
    decision = classify_target_fit(
        razao_social="ADMINISTRACAO REGIONAL DO ESTADO",
        nome_fantasia="SESC",
        contracts=[_contract("ADMINISTRACAO REGIONAL DO ESTADO")],
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE


# --------------------------------------------------------------------------
# AC 24 — blast-radius non-regression, measured on the layer that decides
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "razao_social",
    ["FUNDACAO ENGENHARIA E CONSTRUCOES LTDA", "CONSTRUTORA ALFA ENGENHARIA LTDA"],
)
def test_legitimate_construction_targets_are_not_suppressed(razao_social: str) -> None:
    """AC 24(a) — the only place this taxonomy could bite a legitimate target.

    Until iteration 2 these names were only protected at the `resolve_identity`
    layer (AC 12), which the outbound path does not consult.
    """
    decision = classify_target_fit(
        razao_social=razao_social,
        contracts=[_contract(razao_social, idx=i) for i in range(3)],
        sector_fit="CONSTRUCTION_CONFIRMED",
        activity_class="CONSTRUCTION",
    )
    assert PARAFISCAL_REASON not in decision.target_fit_reason_codes
    assert decision.target_fit_class == TARGET_CONFIRMED


@pytest.mark.parametrize(
    ("raiz", "razao_social"),
    [
        ("82895327", "FUNDACAO DE ENSINO E ENGENHARIA DE SANTA CATARINA"),
        ("18025536", "FUNDACAO DE PESQUISA E ASSESSORAMENTO A INDUSTRIA"),
    ],
)
def test_declared_borderline_suppressions(raiz: str, razao_social: str) -> None:
    """AC 24(b) — FEESC and FUPAI are DECLARED, conscious suppressions.

    Both carry engineering evidence in the name and are support foundations,
    not works executors. Making the decision explicit here so it is auditable
    rather than an implicit side effect of the taxonomy.
    """
    decision = classify_target_fit(
        razao_social=razao_social,
        contracts=[_contract(razao_social, idx=i) for i in range(3)],
        sector_fit="CONSTRUCTION_CONFIRMED",
    )
    assert decision.target_fit_class == TARGET_OUT_OF_SCOPE, raiz
    assert PARAFISCAL_REASON in decision.target_fit_reason_codes


def test_generic_public_foundations_are_not_parafiscal() -> None:
    """The taxonomy was NOT widened in iteration 2 — guard against drift.

    Generic public foundations stay PUBLIC_ORGAN on the identity path and must
    not carry a parafiscal marker (this is what keeps the measured blast radius
    of 68 confirmed roots valid).
    """
    for name in (
        "FUNDACAO MUNICIPAL DE CULTURA",
        "FUNDACAO ESTADUAL DE SAUDE",
        "FUNDACAO HOSPITALAR",
        "FUNDACAO NACIONAL DE ARTES",
    ):
        assert match_parafiscal_institutional(name) is None, name


def test_marker_matching_is_whole_token_not_substring() -> None:
    """"SESC" must not fire on "SESCOOPERATIVA"; widening to substring would
    silently change the measured blast radius of 68/568 roots."""
    assert match_parafiscal_institutional("SESCOOPERATIVA DO SUL LTDA") is None
    assert match_parafiscal_institutional("CONSTRUTORA SENAIA LTDA") is None
    assert match_parafiscal_institutional("SESC DE SAO PAULO") == "sesc"


def test_taxonomy_has_no_hardcoded_cnpj_or_company_identity() -> None:
    """AC 19 alignment — class markers only, never a specific entity."""
    for marker in PARAFISCAL_INSTITUTIONAL_MARKERS:
        assert not any(ch.isdigit() for ch in marker), marker

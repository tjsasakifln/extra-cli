"""AC6 / AC7 — FIT tri-estado, sem score, com UNKNOWN que nunca colapsa."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from scripts.confenge_account_intelligence.message_spine import is_hollow_fact
from scripts.confenge_live_intelligence import fit as li_fit
from scripts.confenge_live_intelligence import schema as li_schema

AS_OF = date(2026, 9, 2)
UTC_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _opportunity(**overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id="LI-TEST-OP",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de unidade basica de saude com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000199",
        orgao_state=li_schema.OBSERVED,
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_objects=("Reforma de escola municipal com estrutura metalica pesada",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000199",),
        most_recent_contracting_date=date(2025, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


# --- AC7 -------------------------------------------------------------------


def test_hollow_object_resolves_to_unknown_never_no_match() -> None:
    hollow = "sem dor concreta"
    assert is_hollow_fact(hollow) is True
    fit = li_fit.evaluate_fit(_company(), _opportunity(objeto=hollow), as_of=AS_OF)
    assert fit.dim_object == li_schema.UNKNOWN
    assert fit.dim_object != li_schema.NO_MATCH
    assert li_fit.REASON_OBJECT_HOLLOW in fit.reason_codes
    assert "dim_object" in fit.unknown_dimensions


def test_short_object_text_is_hollow_and_unknown() -> None:
    short = "obra"  # < 24 chars ⇒ hollow por message_spine.is_hollow_fact
    assert is_hollow_fact(short) is True
    fit = li_fit.evaluate_fit(_company(), _opportunity(objeto=short), as_of=AS_OF)
    assert fit.dim_object == li_schema.UNKNOWN


def test_missing_object_state_is_unknown_not_no_match() -> None:
    opportunity = _opportunity(
        objeto=None, objeto_state=li_schema.UNKNOWN, reason_codes=(li_schema.REASON_OBJECT_MISSING,)
    )
    fit = li_fit.evaluate_fit(_company(), opportunity, as_of=AS_OF)
    assert fit.dim_object == li_schema.UNKNOWN


def test_empty_observed_portfolio_is_unknown_not_no_match() -> None:
    fit = li_fit.evaluate_fit(_company(observed_objects=()), _opportunity(), as_of=AS_OF)
    assert fit.dim_object == li_schema.UNKNOWN
    assert li_fit.REASON_OBJECT_PORTFOLIO_EMPTY in fit.reason_codes


def test_observed_evidence_on_both_sides_can_be_no_match() -> None:
    """NO_MATCH exige evidencia dos DOIS lados — nunca ausencia."""
    fit = li_fit.evaluate_fit(
        _company(observed_objects=("Locacao de veiculos leves para transporte escolar",)),
        _opportunity(),
        as_of=AS_OF,
    )
    assert fit.dim_object == li_schema.NO_MATCH


# --- AC6 -------------------------------------------------------------------


def test_every_dimension_resolves_to_exactly_one_tri_state() -> None:
    fit = li_fit.evaluate_fit(_company(), _opportunity(), as_of=AS_OF)
    for name in li_fit.PRIORIDADE_DIMENSOES:
        assert getattr(fit, name) in li_schema.DIMENSION_STATES


def test_priority_tuple_covers_all_five_dimensions() -> None:
    assert set(li_fit.PRIORIDADE_DIMENSOES) == set(li_schema.DIMENSION_NAMES)
    assert len(li_fit.PRIORIDADE_DIMENSOES) == 5
    assert set(li_fit.DIMENSOES_REQUERIDAS) | set(li_fit.DIMENSOES_OPCIONAIS) | {"dim_recency"} == set(
        li_fit.PRIORIDADE_DIMENSOES
    )


def test_ordering_key_is_lexicographic_tuple_of_labels() -> None:
    strong = li_fit.evaluate_fit(_company(), _opportunity(), as_of=AS_OF)
    weak = li_fit.evaluate_fit(
        _company(observed_objects=("Locacao de veiculos leves",), observed_ufs=("PR",)),
        _opportunity(),
        as_of=AS_OF,
    )
    key = li_fit.ordering_key(strong)
    assert all(isinstance(part, str) for part in key)
    assert li_fit.sort_fits([weak, strong])[0] is strong


def test_fit_state_derivation_matches_migration_check() -> None:
    assert li_fit.derive_fit_state(dict.fromkeys(li_fit.PRIORIDADE_DIMENSOES, li_schema.NO_MATCH)) == li_schema.FIT_NONE
    assert (
        li_fit.derive_fit_state(dict.fromkeys(li_fit.PRIORIDADE_DIMENSOES, li_schema.UNKNOWN))
        == li_schema.FIT_INSUFFICIENT
    )
    mixed = dict.fromkeys(li_fit.PRIORIDADE_DIMENSOES, li_schema.NO_MATCH)
    mixed["dim_geography"] = li_schema.MATCH
    assert li_fit.derive_fit_state(mixed) == li_schema.FIT_OBSERVED
    unknown_only = dict.fromkeys(li_fit.PRIORIDADE_DIMENSOES, li_schema.NO_MATCH)
    unknown_only["dim_object"] = li_schema.UNKNOWN
    assert li_fit.derive_fit_state(unknown_only) == li_schema.FIT_INSUFFICIENT


def test_unknown_in_optional_dimension_does_not_exclude_row() -> None:
    opportunity = _opportunity(
        valor_estimado_brl=None,
        valor_state=li_schema.UNKNOWN,
        valor_band=None,
        orgao_cnpj=None,
        orgao_state=li_schema.UNKNOWN,
        reason_codes=(li_schema.REASON_VALUE_MISSING, li_schema.REASON_ORGAO_MISSING),
    )
    fit = li_fit.evaluate_fit(_company(), opportunity, as_of=AS_OF)
    assert fit.dim_value_band == li_schema.UNKNOWN
    assert fit.dim_comparable_buyer == li_schema.UNKNOWN
    assert li_fit.required_dimension_unknown(fit) == ()


def test_unknown_in_required_dimension_excludes_row() -> None:
    opportunity = _opportunity(uf=None, geo_state=li_schema.UNKNOWN, reason_codes=(li_schema.REASON_GEO_MISSING,))
    fit = li_fit.evaluate_fit(_company(), opportunity, as_of=AS_OF)
    assert "dim_geography" in li_fit.required_dimension_unknown(fit)


def test_recency_unknown_when_contracting_date_unresolved() -> None:
    company = _company(
        most_recent_contracting_date=None,
        contracting_date_state=li_schema.UNKNOWN,
        row_completeness_state=li_schema.ROW_EXCLUDED_UNRESOLVED_DATE,
        exclusion_reason_codes=(li_schema.REASON_CONTRACTING_DATE_UNRESOLVED,),
        reason_codes=(li_schema.REASON_CONTRACTING_DATE_UNRESOLVED,),
    )
    fit = li_fit.evaluate_fit(company, _opportunity(), as_of=AS_OF)
    assert fit.dim_recency == li_schema.UNKNOWN
    assert li_fit.REASON_RECENCY_UNRESOLVED in fit.reason_codes


def test_stale_portfolio_is_no_match_not_unknown() -> None:
    company = _company(most_recent_contracting_date=date(2010, 1, 1))
    fit = li_fit.evaluate_fit(company, _opportunity(), as_of=AS_OF)
    assert fit.dim_recency == li_schema.NO_MATCH

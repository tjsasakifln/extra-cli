"""LI-5 — FIT tri-estado por dimensao (Decisao 4).

Contrato inegociavel desta camada:

* Cinco dimensoes, cada uma resolvendo para EXATAMENTE um de
  ``MATCH`` / ``NO_MATCH`` / ``UNKNOWN``.
* ZERO score numerico (R6). Nao existe ``fit_score``, ``matched_count``,
  percentual nem qualquer campo numerico no output. A ordenacao e uma TUPLA
  LEXICOGRAFICA de rotulos sobre ``PRIORIDADE_DIMENSOES`` — nao um ranking
  aritmetico disfarcado.
* ``UNKNOWN`` nunca colapsa em ``NO_MATCH`` (R7 / AC7). Evidencia ausente e
  ``UNKNOWN`` com ``reason_code``; ``NO_MATCH`` exige evidencia dos dois lados.
* Nenhum import de ``opportunity_intel.scoring`` / ``opportunity_intel.ranking``.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Final

from scripts.confenge_account_intelligence.message_spine import is_hollow_fact
from scripts.confenge_live_intelligence.schema import (
    FIT_INSUFFICIENT,
    FIT_NONE,
    FIT_OBSERVED,
    MATCH,
    NO_MATCH,
    OBSERVED,
    UNKNOWN,
    LiveCompany,
    LiveCompanyOpportunityFit,
    LiveOpportunity,
)

# Ordem de prioridade das dimensoes na tupla lexicografica de ordenacao.
PRIORIDADE_DIMENSOES: Final[tuple[str, ...]] = (
    "dim_object",
    "dim_geography",
    "dim_recency",
    "dim_value_band",
    "dim_comparable_buyer",
)

# Dimensoes REQUERIDAS: UNKNOWN em qualquer uma exclui a linha do universo
# consumivel (§7.2). As demais sao OPCIONAIS — UNKNOWN nelas mantem READY.
DIMENSOES_REQUERIDAS: Final[tuple[str, ...]] = ("dim_object", "dim_geography")
DIMENSOES_OPCIONAIS: Final[tuple[str, ...]] = ("dim_value_band", "dim_comparable_buyer")

# Janela de recencia do ato de contratacao observado (dia civil).
RECENCY_WINDOW_DAYS: Final[int] = 1095  # 3 anos

# Rotulos de ordenacao. Deliberadamente NAO numericos: a chave de ordenacao e
# uma tupla de strings, para que nenhum score aritmetico possa reaparecer.
_ORDER_LABEL: Final[dict[str, str]] = {MATCH: "A_MATCH", UNKNOWN: "B_UNKNOWN", NO_MATCH: "C_NO_MATCH"}

REASON_OBJECT_HOLLOW = "dim_object_unknown_hollow_opportunity_text"
REASON_OBJECT_PORTFOLIO_EMPTY = "dim_object_unknown_empty_observed_portfolio"
REASON_VALUE_UNKNOWN_OPPORTUNITY = "dim_value_band_unknown_opportunity_value"
REASON_VALUE_UNKNOWN_PORTFOLIO = "dim_value_band_unknown_portfolio_bands"
REASON_GEO_UNKNOWN_OPPORTUNITY = "dim_geography_unknown_opportunity_uf"
REASON_GEO_UNKNOWN_PORTFOLIO = "dim_geography_unknown_portfolio_ufs"
REASON_BUYER_UNKNOWN_OPPORTUNITY = "dim_comparable_buyer_unknown_opportunity_buyer"
REASON_BUYER_UNKNOWN_PORTFOLIO = "dim_comparable_buyer_unknown_portfolio_buyers"
REASON_RECENCY_UNRESOLVED = "dim_recency_unknown_contracting_date_unresolved"

_TOKEN_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "para",
        "com",
        "em",
        "no",
        "na",
        "nos",
        "nas",
        "por",
        "ao",
        "aos",
        "a",
        "o",
        "os",
        "as",
        "um",
        "uma",
        "servico",
        "servicos",
        "contratacao",
        "prestacao",
        "empresa",
        "objeto",
        "aquisicao",
        "fornecimento",
    }
)
_TOKEN_MIN_LEN: Final[int] = 4


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


def normalize_tokens(text: str | None) -> frozenset[str]:
    """Tokens normalizados e deterministicos de um texto de objeto contratual."""
    if not text:
        return frozenset()
    lowered = _strip_accents(str(text)).lower()
    raw = re.split(r"[^a-z0-9]+", lowered)
    return frozenset(t for t in raw if len(t) >= _TOKEN_MIN_LEN and t not in _TOKEN_STOPWORDS)


def _dim_object(company: LiveCompany, opportunity: LiveOpportunity) -> tuple[str, list[str]]:
    # AC7: objeto hollow ⇒ UNKNOWN, jamais NO_MATCH.
    if opportunity.objeto_state != OBSERVED or is_hollow_fact(opportunity.objeto):
        return UNKNOWN, [REASON_OBJECT_HOLLOW]
    portfolio_tokens: set[str] = set()
    for observed in company.observed_objects:
        if is_hollow_fact(observed):
            continue
        portfolio_tokens |= normalize_tokens(observed)
    if not portfolio_tokens:
        return UNKNOWN, [REASON_OBJECT_PORTFOLIO_EMPTY]
    if normalize_tokens(opportunity.objeto) & portfolio_tokens:
        return MATCH, []
    return NO_MATCH, []


def _dim_value_band(company: LiveCompany, opportunity: LiveOpportunity) -> tuple[str, list[str]]:
    if opportunity.valor_state != OBSERVED or opportunity.valor_band is None:
        return UNKNOWN, [REASON_VALUE_UNKNOWN_OPPORTUNITY]
    if not company.observed_value_bands:
        return UNKNOWN, [REASON_VALUE_UNKNOWN_PORTFOLIO]
    if opportunity.valor_band in company.observed_value_bands:
        return MATCH, []
    return NO_MATCH, []


def _dim_geography(company: LiveCompany, opportunity: LiveOpportunity) -> tuple[str, list[str]]:
    if opportunity.geo_state != OBSERVED or not opportunity.uf:
        return UNKNOWN, [REASON_GEO_UNKNOWN_OPPORTUNITY]
    if not company.observed_ufs:
        return UNKNOWN, [REASON_GEO_UNKNOWN_PORTFOLIO]
    if opportunity.uf in company.observed_ufs:
        return MATCH, []
    return NO_MATCH, []


def _dim_comparable_buyer(company: LiveCompany, opportunity: LiveOpportunity) -> tuple[str, list[str]]:
    if opportunity.orgao_state != OBSERVED or not opportunity.orgao_cnpj:
        return UNKNOWN, [REASON_BUYER_UNKNOWN_OPPORTUNITY]
    if not company.observed_buyer_cnpjs:
        return UNKNOWN, [REASON_BUYER_UNKNOWN_PORTFOLIO]
    if opportunity.orgao_cnpj in company.observed_buyer_cnpjs:
        return MATCH, []
    return NO_MATCH, []


def _dim_recency(company: LiveCompany, as_of: date) -> tuple[str, list[str]]:
    if company.contracting_date_state != OBSERVED or company.most_recent_contracting_date is None:
        return UNKNOWN, [REASON_RECENCY_UNRESOLVED]
    delta = (as_of - company.most_recent_contracting_date).days
    if 0 <= delta <= RECENCY_WINDOW_DAYS:
        return MATCH, []
    return NO_MATCH, []


def derive_fit_state(dimensions: dict[str, str]) -> str:
    """Derivacao deterministica (§4.2). Espelha o CHECK estrutural da 104."""
    values = [dimensions[name] for name in PRIORIDADE_DIMENSOES]
    if MATCH in values:
        return FIT_OBSERVED
    if UNKNOWN in values:
        return FIT_INSUFFICIENT
    return FIT_NONE


def evaluate_fit(
    company: LiveCompany,
    opportunity: LiveOpportunity,
    *,
    as_of: date,
) -> LiveCompanyOpportunityFit:
    """Avalia as 5 dimensoes e devolve o FIT tri-estado, sem score."""
    reason_codes: list[str] = []
    dimensions: dict[str, str] = {}

    for name, resolver in (
        ("dim_object", lambda: _dim_object(company, opportunity)),
        ("dim_value_band", lambda: _dim_value_band(company, opportunity)),
        ("dim_geography", lambda: _dim_geography(company, opportunity)),
        ("dim_comparable_buyer", lambda: _dim_comparable_buyer(company, opportunity)),
        ("dim_recency", lambda: _dim_recency(company, as_of)),
    ):
        state, reasons = resolver()
        dimensions[name] = state
        reason_codes.extend(reasons)

    matched = tuple(name for name in PRIORIDADE_DIMENSOES if dimensions[name] == MATCH)
    unknown = tuple(name for name in PRIORIDADE_DIMENSOES if dimensions[name] == UNKNOWN)

    return LiveCompanyOpportunityFit(
        company_root8=company.company_root8,
        opportunity_id=opportunity.opportunity_id,
        dim_object=dimensions["dim_object"],
        dim_value_band=dimensions["dim_value_band"],
        dim_geography=dimensions["dim_geography"],
        dim_comparable_buyer=dimensions["dim_comparable_buyer"],
        dim_recency=dimensions["dim_recency"],
        fit_state=derive_fit_state(dimensions),
        matched_dimensions=matched,
        unknown_dimensions=unknown,
        reason_codes=tuple(sorted(set(reason_codes))),
        evidence_refs={
            "opportunity_source": opportunity.source,
            "date_resolver_version": company.date_resolver_version,
        },
    )


def ordering_key(fit: LiveCompanyOpportunityFit) -> tuple[str, ...]:
    """Chave de ordenacao LEXICOGRAFICA (Decisao 4). Nenhum numero envolvido."""
    return tuple(_ORDER_LABEL[getattr(fit, name)] for name in PRIORIDADE_DIMENSOES) + (
        fit.company_root8,
        fit.opportunity_id,
    )


def sort_fits(fits: list[LiveCompanyOpportunityFit]) -> list[LiveCompanyOpportunityFit]:
    return sorted(fits, key=ordering_key)


def required_dimension_unknown(fit: LiveCompanyOpportunityFit) -> tuple[str, ...]:
    """Dimensoes REQUERIDAS resolvidas como UNKNOWN (criterio de exclusao)."""
    return tuple(name for name in DIMENSOES_REQUERIDAS if getattr(fit, name) == UNKNOWN)

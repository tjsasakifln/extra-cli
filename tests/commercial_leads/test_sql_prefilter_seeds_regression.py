"""AC 14 — the SQL prefilter must never shrink.

`pipeline._segment_sql_prefilter` used POSITIONAL slices of STRONG_PHRASES[:12]
and STRONG_TOKENS[:10]. Removing the bare "fundacao" token from those tuples and
appending the new structural phrases at the end would have pushed "fundacao" past
the cut, silently dropping `ILIKE '%fundacao%'` from the scan over the ~4M
contract table — killing recall for legitimate deep-foundation works BEFORE the
Python precision layer ever saw them.

The BASELINE list below is the literal clause set captured from the pre-change
implementation. The new list must be equal to it or a strict superset.
"""

from __future__ import annotations

from typing import Any

from scripts.commercial_leads.contract_relevance import SQL_PREFILTER_SEEDS
from scripts.commercial_leads.pipeline import _segment_sql_prefilter

# Captured from the pre-change implementation (STRONG_PHRASES[:12] +
# STRONG_TOKENS[:10], de-duped, no profile keywords) before any edit.
BASELINE_PREFILTER_TERMS: tuple[str, ...] = (
    "obra de engenharia",
    "execucao de obra",
    "execucao de obras",
    "construcao civil",
    "pavimentacao",
    "pavimentacao asfaltica",
    "drenagem",
    "drenagem urbana",
    "saneamento",
    "terraplenagem",
    "fundacao",
    "edificacao",
    "geotecnia",
    "topografia",
    "topografico",
    "empreitada",
)


class _StubProfile:
    """Minimal stand-in for CommercialProfile (only `.data` is read)."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


def _terms(profile: _StubProfile) -> list[str]:
    sql, params = _segment_sql_prefilter(profile)  # type: ignore[arg-type]
    assert sql.count("objeto_contrato ILIKE %s") == len(params)
    return [p.strip("%") for p in params]


def test_empty_profile_prefilter_is_superset_of_baseline() -> None:
    terms = _terms(_StubProfile({"segments": []}))
    missing = [t for t in BASELINE_PREFILTER_TERMS if t not in terms]
    assert missing == [], f"prefilter shrank; lost clauses: {missing}"


def test_bare_fundacao_survives_the_30_term_cut() -> None:
    """Task 3 second bullet — `ordered[:30]` must still emit ILIKE '%fundacao%'."""
    profile = _StubProfile(
        {
            "segments": [
                {
                    "object_keywords": [
                        "obras", "reforma predial", "ponte", "viaduto",
                        "escola", "creche", "posto de saude", "quadra",
                        "ginasio", "praca", "calcamento", "recapeamento",
                    ]
                }
            ]
        }
    )
    terms = _terms(profile)
    assert "fundacao" in terms
    assert len(terms) <= 30


def test_realistic_profile_prefilter_is_superset_of_baseline() -> None:
    profile = _StubProfile(
        {
            "segments": [
                {"object_keywords": ["obras", "projeto", "consultoria", "ponte"]},
                {"object_keywords": ["saneamento", "drenagem"]},
            ]
        }
    )
    terms = _terms(profile)
    missing = [t for t in BASELINE_PREFILTER_TERMS if t not in terms]
    assert missing == [], f"prefilter shrank; lost clauses: {missing}"


def test_seeds_constant_is_decoupled_from_strong_tuple_ordering() -> None:
    """The seeds must be an explicit constant, not a positional slice."""
    from scripts.commercial_leads import contract_relevance as cr

    assert "fundacao" in SQL_PREFILTER_SEEDS
    # bare "fundacao" was intentionally removed from the precision layers
    assert "fundacao" not in cr.STRONG_PHRASES
    assert "fundacao" not in cr.STRONG_TOKENS
    assert "fundacao" not in cr.POSITIVE_CONTEXT
    assert set(BASELINE_PREFILTER_TERMS).issubset(set(SQL_PREFILTER_SEEDS))

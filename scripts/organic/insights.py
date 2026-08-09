"""Reusable data-insight records from pSEO export / datalake aggregates.

Each insight carries provenance so pages can cite:

  “Analisamos X contratos públicos de obras no recorte Y e encontramos Z.”
"""

from __future__ import annotations

from datetime import date
from typing import Any


def insight_from_market(market: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    """Build a data-insight from a market aggregate row."""
    contract_count = int(market.get("contract_count") or 0)
    buyer_count = int(market.get("buyer_count") or 0)
    supplier_count = int(market.get("supplier_count") or 0)
    median = market.get("median_value")
    region = market.get("region") or market.get("region_label") or ""
    segment = market.get("segment") or market.get("archetype_id") or ""
    mid = str(market.get("id") or market.get("slug") or "market")
    as_of = as_of or str(market.get("period_end") or date.today().isoformat())

    result = {
        "contract_count": contract_count,
        "buyer_count": buyer_count,
        "supplier_count": supplier_count,
        "median_value": median,
        "p25_value": market.get("p25_value"),
        "p75_value": market.get("p75_value"),
        "open_opportunity_count": market.get("open_opportunity_count"),
        "region": region,
        "segment": segment,
        "interpretation_hooks": list(market.get("interpretation_hooks") or []),
    }

    conf = 0.85 if contract_count >= 15 and buyer_count >= 3 else 0.55 if contract_count >= 8 else 0.3

    return {
        "insight_id": f"insight-{mid}",
        "kind": "market_benchmark",
        "dataset": "pncp_supplier_contracts",
        "data_as_of": as_of,
        "period_start": market.get("period_start"),
        "period_end": market.get("period_end"),
        "filters": {
            "archetype_id": market.get("archetype_id"),
            "region": region,
            "segment": segment,
        },
        "record_count": contract_count,
        "methodology": (
            "Agregação de contratos com valor_total > 0 e arquétipo AEC primário "
            "confirmado/probable no export pSEO; mediana e percentis no recorte."
        ),
        "limitations": list(market.get("limitations") or [])
        + [
            "Não afirma irregularidade, crédito devido ou erro de órgão/fornecedor.",
            "Valores nominais; objetos heterogêneos — mediana não é preço unitário.",
        ],
        "sources": list(market.get("sources") or ["pncp_supplier_contracts"]),
        "calculation": "median/p25/p75 over contract valor_total in filtered set",
        "result": result,
        "confidence": conf,
        "updated_at": as_of,
        "pages_using": [],
        "headline": _market_headline(result, region, segment),
    }


def insight_from_problem_service(ps: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    """Insight linking observed problem pattern to a Confenge service."""
    evidence = int(ps.get("evidence_count") or 0)
    as_of = as_of or date.today().isoformat()
    slug = str(ps.get("slug") or ps.get("id") or "problem")
    return {
        "insight_id": f"insight-prob-{slug}",
        "kind": "problem_service_pattern",
        "dataset": ",".join(ps.get("sources") or ["pncp_supplier_contracts", "site-confenge-guides"]),
        "data_as_of": as_of,
        "filters": {
            "theme": ps.get("theme"),
            "related_archetypes": ps.get("related_archetypes") or [],
        },
        "record_count": evidence,
        "methodology": (
            "Padrão editorial-normativo ancorado em contagem de evidências e "
            "arquétipos recorrentes no datalake; não é ranking comercial."
        ),
        "limitations": list(ps.get("limitations") or []),
        "sources": list(ps.get("sources") or []),
        "calculation": "evidence_count + observed_pattern narrative",
        "result": {
            "problem_label": ps.get("problem_label") or ps.get("problem"),
            "service_slug": ps.get("confenge_service_slug") or ps.get("service"),
            "observed_pattern": ps.get("observed_pattern"),
            "evidence_kind": ps.get("evidence_kind"),
            "technical_guide_paths": ps.get("technical_guide_paths") or [],
        },
        "confidence": 0.7 if evidence >= 20 else 0.45,
        "updated_at": as_of,
        "pages_using": list(ps.get("technical_guide_paths") or []),
        "headline": str(ps.get("problem_label") or ps.get("problem") or slug),
    }


def _market_headline(result: dict[str, Any], region: str, segment: str) -> str:
    n = result.get("contract_count") or 0
    med = result.get("median_value")
    med_s = f" mediana R$ {med:,.0f}".replace(",", ".") if isinstance(med, (int, float)) else ""
    reg = f" em {region}" if region else ""
    seg = f" ({segment})" if segment else ""
    return f"Analisamos {n} contratos públicos de obras{reg}{seg}{med_s}."

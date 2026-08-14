"""Coverage calculator module — metricas de cobertura de monitoramento.

Fornece funcoes para calcular e exibir a cobertura de monitoramento
de entidades publicas por fonte de dados.
"""

from __future__ import annotations

from typing import Any

from config.logging_config import get_logger
from scripts.coverage.covered_entity import (
    COVERED_ENTITY_FORMULA,
    compute_coverage_kpis,
    load_coverage_state_rows,
    published_coverage_kpis,
)

logger = get_logger(__name__)


def report_coverage(conn: Any) -> dict[str, Any]:
    """Generate coverage report from the single covered-entity formula.

    Published ``total_covered`` is ``compute_coverage_kpis`` — never
    ``entity_coverage.is_covered``.
    """
    rows = load_coverage_state_rows(conn)
    kpis = compute_coverage_kpis(rows)
    by_source_map: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        source = str(row.get("source") or "unknown")
        by_source_map.setdefault(source, []).append(row)
    by_source = []
    for source in sorted(by_source_map):
        source_kpis = compute_coverage_kpis(by_source_map[source])
        by_source.append(
            {
                "source": source,
                "entities": source_kpis.total_entities,
                "covered": source_kpis.covered_count,
            }
        )
    result: dict[str, Any] = {
        "groups": [
            {
                "within_200km": True,
                "total": kpis.total_entities,
                "covered": kpis.covered_count,
                "uncovered": len(kpis.excluded_entity_ids),
                "pct": (
                    round(kpis.covered_count / kpis.total_entities * 100, 1) if kpis.total_entities else 0
                ),
            }
        ]
        if kpis.total_entities
        else [],
        "total_entities": kpis.total_entities,
        "total_covered": kpis.covered_count,
        "total_uncovered": len(kpis.excluded_entity_ids),
        "pct": round(kpis.covered_count / kpis.total_entities * 100, 1) if kpis.total_entities else 0,
        "by_source": by_source,
        "uncovered_entities_200km": [
            {"razao_social": entity_id, "cnpj_8": "", "municipio": "", "natureza": ""}
            for entity_id in sorted(kpis.excluded_entity_ids)
        ],
        "covered_entity_ids": sorted(kpis.covered_entity_ids),
        "covered_entity_formula": f"{COVERED_ENTITY_FORMULA.__module__}.{COVERED_ENTITY_FORMULA.__name__}",
        "published_via": published_coverage_kpis.__name__,
    }
    return result


def print_coverage_report(result: dict[str, Any]) -> None:
    """Log coverage report via structured logger.

    Args:
        result: Dict as returned by ``report_coverage()``.
    """
    logger.info("COBERTURA DE MONITORAMENTO — Extra Construtora")

    for g in result["groups"]:
        label = "Dentro do raio 200km" if g["within_200km"] else "Fora do raio 200km"
        logger.info(
            "Grupo %s — Total: %d, Cobertas: %d (%s%%), Descobertas: %d",
            label,
            g["total"],
            g["covered"],
            g["pct"],
            g["uncovered"],
        )

    logger.info(
        "TOTAL: %d entidades | %d cobertas (%s%%) | %d descobertas",
        result["total_entities"],
        result["total_covered"],
        result["pct"],
        result["total_uncovered"],
    )

    logger.info("Por fonte (raio 200km):")
    for s in result["by_source"]:
        pct = round(s["covered"] / s["entities"] * 100, 1) if s["entities"] > 0 else 0
        logger.info(
            "Fonte %s: %d/%d (%s%%)",
            s["source"],
            s["covered"],
            s["entities"],
            pct,
        )

    uncovered = result.get("uncovered_entities_200km", [])
    if uncovered:
        logger.warning(
            "ENTIDADES SEM COBERTURA (raio 200km): %d",
            len(uncovered),
            extra={"extra_data": {"uncovered": uncovered[:20]}},
        )
        for e in uncovered[:20]:
            logger.info(
                "Sem cobertura: %s | %s",
                e["razao_social"][:50],
                e["municipio"] or "N/A",
            )
        if len(uncovered) > 20:
            logger.info("... e mais %d entidades", len(uncovered) - 20)

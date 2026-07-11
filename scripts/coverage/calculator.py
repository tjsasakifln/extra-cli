"""Coverage calculator module — metricas de cobertura de monitoramento.

Fornece funcoes para calcular e exibir a cobertura de monitoramento
de entidades publicas por fonte de dados.
"""

from __future__ import annotations

from typing import Any

from config.logging_config import get_logger

logger = get_logger(__name__)


def report_coverage(conn: Any) -> dict[str, Any]:
    """Generate coverage report for all entities across all sources.

    Args:
        conn: Database connection.

    Returns:
        Dict with keys ``groups`` (list per raio_200km group),
        ``total_entities``, ``total_covered``, ``total_uncovered``,
        ``pct`` (overall), ``by_source`` (per-source breakdown),
        ``uncovered_entities_200km`` (critical gaps list).
    """
    cur = conn.cursor()

    # Overall coverage
    cur.execute(
        """SELECT
            e.raio_200km,
            COUNT(DISTINCT e.id) AS total,
            COUNT(DISTINCT CASE WHEN ec.is_covered THEN e.id END) AS covered,
            COUNT(DISTINCT CASE WHEN NOT ec.is_covered OR ec.is_covered IS NULL THEN e.id END) AS uncovered
         FROM sc_public_entities e
         LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
         WHERE e.is_active = TRUE
         GROUP BY e.raio_200km
         ORDER BY e.raio_200km DESC"""
    )
    rows = cur.fetchall()

    result: dict[str, Any] = {"groups": [], "total_entities": 0, "total_covered": 0, "total_uncovered": 0}
    for raio, total, covered, uncovered in rows:
        group = {
            "within_200km": raio,
            "total": total,
            "covered": covered or 0,
            "uncovered": uncovered or 0,
            "pct": round((covered or 0) / total * 100, 1) if total > 0 else 0,
        }
        result["groups"].append(group)
        result["total_entities"] += total
        result["total_covered"] += (covered or 0)
        result["total_uncovered"] += (uncovered or 0)

    result["pct"] = round(
        result["total_covered"] / result["total_entities"] * 100, 1
    ) if result["total_entities"] > 0 else 0

    # Per-source breakdown
    cur.execute(
        """SELECT source, COUNT(*) AS entity_count, COUNT(*) FILTER (WHERE is_covered) AS covered
           FROM entity_coverage
           WHERE within_200km = TRUE
           GROUP BY source
           ORDER BY source"""
    )
    result["by_source"] = [
        {"source": r[0], "entities": r[1], "covered": r[2]} for r in cur.fetchall()
    ]

    # Uncovered entities within 200km (critical gap)
    cur.execute(
        """SELECT e.razao_social, e.cnpj_8, e.municipio, e.natureza_juridica
           FROM sc_public_entities e
           WHERE e.is_active = TRUE
             AND e.raio_200km = TRUE
             AND e.id NOT IN (
                 SELECT entity_id FROM entity_coverage WHERE is_covered = TRUE
             )
           ORDER BY e.municipio, e.razao_social"""
    )
    result["uncovered_entities_200km"] = [
        {"razao_social": r[0], "cnpj_8": r[1], "municipio": r[2], "natureza": r[3]}
        for r in cur.fetchall()
    ]

    cur.close()
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
            label, g["total"], g["covered"], g["pct"], g["uncovered"],
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
            s["source"], s["covered"], s["entities"], pct,
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
                e["razao_social"][:50], e["municipio"] or "N/A",
            )
        if len(uncovered) > 20:
            logger.info("... e mais %d entidades", len(uncovered) - 20)

"""Service distribution + SERVICE_MONOCULTURE diagnostic.

Does not invent artificial mix percentages. When one service dominates in a way
incompatible with multi-service evidence (e.g. ≥95% reajuste), emit an explicit
causal diagnosis required before outreach release.
"""

from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

REAJUSTE_ID = "estruturacao_pleito_reajuste"
MONOCULTURE_SHARE_THRESHOLD = 0.95


def build_service_distribution(
    rows: list[dict[str, Any]],
    *,
    service_key: str = "service_id",
    confidence_key: str = "confidence",
) -> dict[str, Any]:
    """Aggregate service_id → count / % / median_confidence from company rows."""
    counts: Counter[str] = Counter()
    confs: dict[str, list[float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(
            row.get(service_key)
            or (row.get("primary_service") or {}).get("service_id")
            or ""
        ).strip()
        if not sid:
            sid = "unknown"
        counts[sid] += 1
        conf_raw = row.get(confidence_key)
        if conf_raw is None and isinstance(row.get("primary_service"), dict):
            conf_raw = row["primary_service"].get("confidence")
        try:
            conf = float(conf_raw) if conf_raw is not None else None
        except (TypeError, ValueError):
            conf = None
        if conf is not None:
            confs.setdefault(sid, []).append(conf)

    total = sum(counts.values()) or 0
    distribution: list[dict[str, Any]] = []
    for sid, n in counts.most_common():
        c_list = confs.get(sid) or []
        distribution.append(
            {
                "service_id": sid,
                "company_count": int(n),
                "pct": (float(n) / float(total) * 100.0) if total else 0.0,
                "median_confidence": float(median(c_list)) if c_list else None,
            }
        )

    mono = diagnose_service_monoculture(distribution, total=total)
    return {
        "schema": "confenge.service_distribution.v1",
        "total_companies": total,
        "distinct_services": len(distribution),
        "distribution": distribution,
        "SERVICE_MONOCULTURE": mono,
    }


def diagnose_service_monoculture(
    distribution: list[dict[str, Any]],
    *,
    total: int,
    threshold: float = MONOCULTURE_SHARE_THRESHOLD,
) -> dict[str, Any]:
    """Flag monoculture when one service dominates above threshold."""
    if total <= 0 or not distribution:
        return {
            "flagged": False,
            "dominant_service_id": None,
            "dominant_share": 0.0,
            "threshold": threshold,
            "blocks_outreach_release": False,
            "causal_diagnosis_required": False,
            "causal_diagnosis": None,
        }

    top = distribution[0]
    share = float(top.get("pct") or 0.0) / 100.0
    sid = str(top.get("service_id") or "")
    flagged = share + 1e-12 >= threshold and total >= 10
    diagnosis = None
    if flagged and sid == REAJUSTE_ID:
        diagnosis = (
            "REAJUSTE_MONOCULTURE: ≥95% of routed companies selected "
            "estruturacao_pleito_reajuste. Required causal check before outreach: "
            "(1) confirm portfolio bags are multi-contract when datalake has multi "
            "contracts; (2) confirm specialty signals (aditivo/glosa/licitação/BDI) "
            "are extracted from objects; (3) confirm mature_no_reajuste does not fire "
            "on publication-date-only ages; (4) if evidence is truly thin mature books "
            "only, document as DATA_TRUE_THIN_BOOK_VERIFICATION not router default."
        )
    elif flagged:
        diagnosis = (
            f"SERVICE_MONOCULTURE: {sid} share={share:.1%} exceeds {threshold:.0%}. "
            "Require causal diagnosis before outreach release."
        )

    return {
        "flagged": flagged,
        "dominant_service_id": sid if flagged else None,
        "dominant_share": share,
        "threshold": threshold,
        "blocks_outreach_release": flagged,
        "causal_diagnosis_required": flagged,
        "causal_diagnosis": diagnosis,
    }

"""Simple baseline rankings for comparison (not superiority claims)."""

from __future__ import annotations

from typing import Any

from scripts.commercial_leads.scoring import LeadScore


def baseline_by_value(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(candidates, key=lambda r: (-float(r.get("total_value") or 0), r.get("cnpj14") or ""))
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "total_value_contracted",
                "metric_value": r.get("total_value"),
            }
        )
    return out


def baseline_by_recency(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(
        candidates,
        key=lambda r: (r.get("last_publication") or "", r.get("cnpj14") or ""),
        reverse=True,
    )
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "last_publication",
                "metric_value": r.get("last_publication"),
            }
        )
    return out


def baseline_by_quantity(candidates: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    rows = sorted(
        candidates,
        key=lambda r: (-int(r.get("contract_count") or 0), r.get("cnpj14") or ""),
    )
    out = []
    for i, r in enumerate(rows[:limit], start=1):
        out.append(
            {
                "rank": i,
                "cnpj14": r.get("cnpj14"),
                "razao_social": r.get("razao_social"),
                "metric": "contract_count",
                "metric_value": r.get("contract_count"),
            }
        )
    return out


def compare_to_baselines(
    ranked: list[LeadScore],
    candidates: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> dict[str, Any]:
    proposed = [L.cnpj14 for L in ranked]
    b_val = baseline_by_value(candidates, limit=limit)
    b_rec = baseline_by_recency(candidates, limit=limit)
    b_qty = baseline_by_quantity(candidates, limit=limit)

    def overlap(base: list[dict[str, Any]]) -> dict[str, Any]:
        s = {r["cnpj14"] for r in base}
        inter = [c for c in proposed if c in s]
        only_prop = [c for c in proposed if c not in s]
        only_base = [r["cnpj14"] for r in base if r["cnpj14"] not in set(proposed)]
        return {
            "overlap_count": len(inter),
            "overlap_cnpjs": inter,
            "only_proposed": only_prop,
            "only_baseline": only_base,
            "jaccard": (len(inter) / len(set(proposed) | s)) if (proposed or s) else 0.0,
        }

    return {
        "language_note": (
            "Comparação descritiva apenas. Não declara superioridade sem revisão humana suficiente."
        ),
        "proposed_count": len(proposed),
        "proposed_cnpjs": proposed,
        "baselines": {
            "by_value": b_val,
            "by_recency": b_rec,
            "by_quantity": b_qty,
        },
        "comparison": {
            "vs_value": overlap(b_val),
            "vs_recency": overlap(b_rec),
            "vs_quantity": overlap(b_qty),
        },
        "hypotheses": [
            "Ranking por sinais deve divergir de valor puro quando crescimento/expiração/diversidade dominam.",
            "Sobreposição alta com valor não prova qualidade comercial — apenas correlação parcial.",
        ],
    }

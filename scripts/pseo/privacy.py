"""Small-cell privacy suppression for public aggregates."""

from __future__ import annotations

from typing import Any

DEFAULT_MIN_CELL = 5


def suppress_small_cells(
    cells: list[dict[str, Any]],
    *,
    count_key: str = "contract_count",
    min_cell: int = DEFAULT_MIN_CELL,
    label_key: str = "name",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Suppress or bucket cells below min_cell_count.

    Returns (public_cells, policy_meta).
    """
    kept: list[dict[str, Any]] = []
    suppressed_n = 0
    suppressed_count = 0
    for cell in cells:
        n = int(cell.get(count_key) or 0)
        if n < min_cell:
            suppressed_n += 1
            suppressed_count += n
            continue
        kept.append(dict(cell))
    if suppressed_n:
        kept.append(
            {
                label_key: "outros (células suprimidas)",
                count_key: suppressed_count,
                "suppressed": True,
                "original_cells": suppressed_n,
            }
        )
    meta = {
        "min_cell_count": min_cell,
        "suppressed_cells": suppressed_n,
        "suppressed_contract_count": suppressed_count,
        "policy": "cells with count < min_cell_count are bucketed as 'outros'",
    }
    return kept, meta


def apply_market_privacy(market: dict[str, Any], *, min_cell: int = DEFAULT_MIN_CELL) -> dict[str, Any]:
    out = dict(market)
    buyers = list(out.get("top_buyers") or [])
    public_buyers, meta = suppress_small_cells(buyers, count_key="contract_count", min_cell=min_cell)
    out["top_buyers"] = public_buyers
    # Never export supplier CNPJ14 / names from competition-like fields
    for key in ("top_suppliers", "supplier_ranking", "fornecedores"):
        out.pop(key, None)
    priv = dict(out.get("privacy") or {})
    priv["top_buyers"] = meta
    out["privacy"] = priv
    return out

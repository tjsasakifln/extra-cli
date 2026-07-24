"""Allowlisted SQL filter fragments for national_intel queries.

All dynamic WHERE composition uses only these constant fragments plus bound
parameters (%s). User input never becomes raw SQL text.
"""

from __future__ import annotations

from typing import Any

# Constant fragments only — never interpolate user strings into these.
F_ACTIVE = "c.is_active = TRUE"
F_KEYWORD = "c.objeto_contrato ILIKE %s"
F_UF = "upper(btrim(c.uf)) = upper(btrim(%s))"
F_VALOR_NOT_NULL = "c.valor_total IS NOT NULL"


def build_contract_filters(
    *,
    keyword: str | None = None,
    uf: str | None = None,
    require_valor: bool = False,
) -> tuple[str, list[Any]]:
    """Return (where_sql, params) from allowlisted fragments + bind params."""
    clauses: list[str] = [F_ACTIVE]
    params: list[Any] = []
    if require_valor:
        clauses.append(F_VALOR_NOT_NULL)
    if keyword is not None and str(keyword).strip() != "":
        clauses.append(F_KEYWORD)
        params.append(f"%{keyword}%")
    if uf is not None and str(uf).strip() != "":
        clauses.append(F_UF)
        params.append(uf)
    return " AND ".join(clauses), params
